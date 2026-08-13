from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from incident_investigator.core.scm import (
    ChangeRequestResult,
    ChangeRequestSpec,
    PreparedChangeSpec,
)
from incident_investigator.domain import IncidentSource

from .archive import extract_repository_zip


class GitLabSourceControlProvider:
    platform = IncidentSource.GITLAB_CI

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def create_branch(
        self, repository: str, *, from_revision: str, branch_name: str
    ) -> str:
        project = quote(repository, safe="")
        response = await self._client.post(
            f"/projects/{project}/repository/branches",
            params={"branch": branch_name, "ref": from_revision},
        )
        response.raise_for_status()
        return str(response.json()["name"])

    async def open_change_request(self, spec: ChangeRequestSpec) -> ChangeRequestResult:
        project = quote(spec.repository, safe="")
        title = spec.title
        if spec.draft and not title.lower().startswith(("draft:", "wip:")):
            title = f"Draft: {title}"
        response = await self._client.post(
            f"/projects/{project}/merge_requests",
            json={
                "source_branch": spec.branch_name,
                "target_branch": spec.base_revision,
                "title": title,
                "description": spec.description,
                "draft": spec.draft,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return ChangeRequestResult(
            platform=self.platform,
            external_id=str(payload["iid"]),
            url=str(payload["web_url"]),
            branch_name=spec.branch_name,
        )

    async def materialize(
        self, repository: str, *, revision: str, destination: Path
    ) -> None:
        project = quote(repository, safe="")
        response = await self._client.get(
            f"/projects/{project}/repository/archive.zip", params={"sha": revision}
        )
        response.raise_for_status()
        extract_repository_zip(response.content, destination)

    async def publish_prepared_change(
        self, spec: PreparedChangeSpec
    ) -> ChangeRequestResult:
        project = quote(spec.repository, safe="")
        actions = []
        for change in spec.changes:
            if change.content is None:
                action = "delete"
                payload = {"action": action, "file_path": change.path}
            else:
                action = "update" if change.previous_exists else "create"
                payload = {
                    "action": action,
                    "file_path": change.path,
                    "content": change.content,
                }
            actions.append(payload)
        response = await self._client.post(
            f"/projects/{project}/repository/commits",
            json={
                "branch": spec.branch_name,
                "start_sha": spec.source_revision,
                "commit_message": spec.title,
                "actions": actions,
            },
        )
        response.raise_for_status()
        return await self.open_change_request(
            ChangeRequestSpec(
                repository=spec.repository,
                base_revision=spec.target_branch,
                branch_name=spec.branch_name,
                title=spec.title,
                description=spec.description,
            )
        )
