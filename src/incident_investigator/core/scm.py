from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from incident_investigator.domain import IncidentSource


class ChangeRequestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    base_revision: str
    branch_name: str
    title: str
    description: str
    draft: bool = True


class FileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    content: str | None
    previous_exists: bool


class PreparedChangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    source_revision: str
    target_branch: str
    branch_name: str
    title: str
    description: str
    changes: tuple[FileChange, ...]


class ChangeRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: IncidentSource
    external_id: str
    url: str
    branch_name: str


class SourceControlProvider(Protocol):
    """Common GitHub PR / GitLab MR vocabulary used outside the core graph."""

    platform: IncidentSource

    async def create_branch(
        self, repository: str, *, from_revision: str, branch_name: str
    ) -> str: ...

    async def open_change_request(self, spec: ChangeRequestSpec) -> ChangeRequestResult: ...

    async def materialize(
        self, repository: str, *, revision: str, destination: Path
    ) -> None: ...

    async def publish_prepared_change(
        self, spec: PreparedChangeSpec
    ) -> ChangeRequestResult: ...
