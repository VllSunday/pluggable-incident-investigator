from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from incident_investigator.adapters.scm import (
    GitHubSourceControlProvider,
    GitLabSourceControlProvider,
)
from incident_investigator.adapters.scm.archive import extract_repository_zip
from incident_investigator.core.scm import (
    ChangeRequestSpec,
    FileChange,
    PreparedChangeSpec,
)
from incident_investigator.domain import IncidentSource


@pytest.mark.asyncio
async def test_github_provider_uses_shared_change_request_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/fix/incident-42"})
        assert request.url.path.endswith("/pulls")
        return httpx.Response(
            201, json={"number": 12, "html_url": "https://github.example/pull/12"}
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.test", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitHubSourceControlProvider(client)
        branch = await provider.create_branch(
            "acme/repo", from_revision="abc", branch_name="fix/incident-42"
        )
        result = await provider.open_change_request(
            ChangeRequestSpec(
                repository="acme/repo",
                base_revision="main",
                branch_name=branch,
                title="Fix incident 42",
                description="Verified change",
            )
        )

    assert result.platform is IncidentSource.GITHUB_ACTIONS
    assert result.external_id == "12"


@pytest.mark.asyncio
async def test_gitlab_provider_uses_same_change_request_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repository/branches"):
            return httpx.Response(201, json={"name": "fix/incident-91"})
        assert request.url.path.endswith("/merge_requests")
        return httpx.Response(
            201, json={"iid": 13, "web_url": "https://gitlab.example/merge_requests/13"}
        )

    async with httpx.AsyncClient(
        base_url="https://gitlab.test/api/v4", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitLabSourceControlProvider(client)
        branch = await provider.create_branch(
            "acme/repo", from_revision="abc", branch_name="fix/incident-91"
        )
        result = await provider.open_change_request(
            ChangeRequestSpec(
                repository="acme/repo",
                base_revision="main",
                branch_name=branch,
                title="Fix incident 91",
                description="Verified change",
            )
        )

    assert result.platform is IncidentSource.GITLAB_CI
    assert result.external_id == "13"


@pytest.mark.asyncio
async def test_github_provider_publishes_one_commit_then_draft_pr() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if request.url.path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob-1"})
        if request.url.path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "tree-1"})
        if request.url.path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "commit-1"})
        if request.url.path.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/incident-fix/42"})
        return httpx.Response(
            201, json={"number": 42, "html_url": "https://github.test/pull/42"}
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.test", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitHubSourceControlProvider(client)
        result = await provider.publish_prepared_change(
            PreparedChangeSpec(
                repository="acme/repo",
                source_revision="bad-sha",
                target_branch="main",
                branch_name="incident-fix/42",
                title="Fix regression",
                description="Tested fix",
                changes=(
                    FileChange(path="app.py", content="FIXED = True\n", previous_exists=True),
                ),
            )
        )

    assert result.url.endswith("/pull/42")
    assert paths[-1].endswith("/pulls")


@pytest.mark.asyncio
async def test_gitlab_provider_publishes_atomic_commit_then_draft_mr() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/repository/commits"):
            return httpx.Response(201, json={"id": "commit-1"})
        return httpx.Response(
            201, json={"iid": 42, "web_url": "https://gitlab.test/merge_requests/42"}
        )

    async with httpx.AsyncClient(
        base_url="https://gitlab.test/api/v4", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitLabSourceControlProvider(client)
        result = await provider.publish_prepared_change(
            PreparedChangeSpec(
                repository="acme/repo",
                source_revision="bad-sha",
                target_branch="main",
                branch_name="incident-fix/42",
                title="Fix regression",
                description="Tested fix",
                changes=(
                    FileChange(path="app.py", content="FIXED = True\n", previous_exists=True),
                ),
            )
        )

    assert result.url.endswith("/merge_requests/42")
    assert requests[0].url.path.endswith("/repository/commits")
    assert requests[1].url.path.endswith("/merge_requests")


def test_repository_archive_rejects_path_traversal(tmp_path: Path) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("root/../../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        extract_repository_zip(payload.getvalue(), tmp_path / "workspace")

    assert not (tmp_path / "outside.txt").exists()
