from __future__ import annotations

import base64
from pathlib import Path

import httpx

from incident_investigator.core.scm import (
    ChangeRequestResult,
    ChangeRequestSpec,
    PreparedChangeSpec,
)
from incident_investigator.domain import IncidentSource

from .archive import extract_repository_zip


class GitHubSourceControlProvider:
    platform = IncidentSource.GITHUB_ACTIONS

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def create_branch(
        self, repository: str, *, from_revision: str, branch_name: str
    ) -> str:
        response = await self._client.post(
            f"/repos/{repository}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": from_revision},
        )
        response.raise_for_status()
        return str(response.json()["ref"]).removeprefix("refs/heads/")

    async def open_change_request(self, spec: ChangeRequestSpec) -> ChangeRequestResult:
        response = await self._client.post(
            f"/repos/{spec.repository}/pulls",
            json={
                "title": spec.title,
                "body": spec.description,
                "head": spec.branch_name,
                "base": spec.base_revision,
                "draft": spec.draft,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return ChangeRequestResult(
            platform=self.platform,
            external_id=str(payload["number"]),
            url=str(payload["html_url"]),
            branch_name=spec.branch_name,
        )

    async def materialize(
        self, repository: str, *, revision: str, destination: Path
    ) -> None:
        response = await self._client.get(
            f"/repos/{repository}/zipball/{revision}", follow_redirects=True
        )
        response.raise_for_status()
        extract_repository_zip(response.content, destination)

    async def publish_prepared_change(
        self, spec: PreparedChangeSpec
    ) -> ChangeRequestResult:
        commit_response = await self._client.get(
            f"/repos/{spec.repository}/git/commits/{spec.source_revision}"
        )
        commit_response.raise_for_status()
        base_tree = str(commit_response.json()["tree"]["sha"])
        entries: list[dict[str, str | None]] = []
        for change in spec.changes:
            if change.content is None:
                entries.append(
                    {"path": change.path, "mode": "100644", "type": "blob", "sha": None}
                )
                continue
            blob_response = await self._client.post(
                f"/repos/{spec.repository}/git/blobs",
                json={
                    "content": base64.b64encode(change.content.encode()).decode(),
                    "encoding": "base64",
                },
            )
            blob_response.raise_for_status()
            entries.append(
                {
                    "path": change.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": str(blob_response.json()["sha"]),
                }
            )
        tree_response = await self._client.post(
            f"/repos/{spec.repository}/git/trees",
            json={"base_tree": base_tree, "tree": entries},
        )
        tree_response.raise_for_status()
        new_commit = await self._client.post(
            f"/repos/{spec.repository}/git/commits",
            json={
                "message": spec.title,
                "tree": tree_response.json()["sha"],
                "parents": [spec.source_revision],
            },
        )
        new_commit.raise_for_status()
        await self.create_branch(
            spec.repository,
            from_revision=str(new_commit.json()["sha"]),
            branch_name=spec.branch_name,
        )
        return await self.open_change_request(
            ChangeRequestSpec(
                repository=spec.repository,
                base_revision=spec.target_branch,
                branch_name=spec.branch_name,
                title=spec.title,
                description=spec.description,
            )
        )
