from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from incident_investigator.adapters.evidence import (
    GitHubCIEvidenceProvider,
    GitLabCIEvidenceProvider,
)
from incident_investigator.domain import (
    IncidentEvent,
    IncidentKind,
    IncidentSource,
)


@pytest.mark.asyncio
async def test_github_provider_collects_failed_log_and_diff_and_redacts_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 7,
                            "name": "tests",
                            "conclusion": "failure",
                            "html_url": "https://github.example/jobs/7",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, text="API_KEY=super-secret-value\nAssertionError")
        return httpx.Response(
            200,
            json={
                "html_url": "https://github.example/commit/abc",
                "files": [{"filename": "app.py", "patch": "-old\n+new"}],
            },
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.test", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitHubCIEvidenceProvider(client)
        evidence = await provider.collect(
            IncidentEvent(
                source=IncidentSource.GITHUB_ACTIONS,
                kind=IncidentKind.CI_FAILURE,
                external_id="42",
                service="acme/repo",
                title="CI failed",
                started_at=datetime.now(UTC),
                correlation_id="github:acme/repo:42",
                metadata={"head_sha": "abc"},
            ),
            "collect evidence",
        )

    assert [item.kind for item in evidence] == ["ci_job_log", "commit_diff"]
    assert "super-secret-value" not in evidence[0].summary
    assert "[REDACTED]" in evidence[0].summary
    assert evidence[0].content_hash


@pytest.mark.asyncio
async def test_gitlab_provider_collects_failed_job_trace_and_diff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 8,
                        "name": "pytest",
                        "status": "failed",
                        "web_url": "https://gitlab.example/jobs/8",
                    }
                ],
            )
        if request.url.path.endswith("/trace"):
            return httpx.Response(200, text="FAILED tests/test_api.py")
        return httpx.Response(
            200, json=[{"new_path": "api.py", "diff": "-broken\n+fixed"}]
        )

    async with httpx.AsyncClient(
        base_url="https://gitlab.test/api/v4", transport=httpx.MockTransport(handler)
    ) as client:
        provider = GitLabCIEvidenceProvider(client)
        evidence = await provider.collect(
            IncidentEvent(
                source=IncidentSource.GITLAB_CI,
                kind=IncidentKind.CI_FAILURE,
                external_id="91",
                service="acme/repo",
                title="Pipeline failed",
                started_at=datetime.now(UTC),
                correlation_id="gitlab:acme/repo:91",
                metadata={"sha": "abc"},
            ),
            "collect evidence",
        )

    assert [item.kind for item in evidence] == ["ci_job_log", "commit_diff"]
    assert "FAILED" in evidence[0].summary
    assert evidence[1].attributes["platform"] == "gitlab"
