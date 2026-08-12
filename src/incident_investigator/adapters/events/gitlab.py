from __future__ import annotations

import hmac
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from incident_investigator.domain import IncidentEvent, IncidentKind, IncidentSource


class InvalidGitLabWebhookToken(ValueError):
    pass


class GitLabCIEventAdapter:
    """Normalizes GitLab Pipeline Hook failures into the shared incident model."""

    name = "gitlab_ci"

    def __init__(
        self, secret_token: str, *, remediation_profiles: tuple[str, ...] = ()
    ) -> None:
        if not secret_token:
            raise ValueError("GitLab webhook secret token must not be empty")
        self._secret_token = secret_token
        self._remediation_profiles = remediation_profiles

    def verify(self, body: bytes, headers: Mapping[str, str]) -> None:
        del body
        supplied = headers.get("x-gitlab-token", "")
        if not hmac.compare_digest(supplied, self._secret_token):
            raise InvalidGitLabWebhookToken("Invalid GitLab webhook token")

    def normalize(self, payload: Mapping[str, Any]) -> list[IncidentEvent]:
        if payload.get("object_kind") != "pipeline":
            return []

        pipeline = payload.get("object_attributes")
        project = payload.get("project")
        if not isinstance(pipeline, Mapping) or not isinstance(project, Mapping):
            raise ValueError("GitLab payload is missing object_attributes or project")
        if pipeline.get("status") != "failed":
            return []

        pipeline_id = str(pipeline["id"])
        project_path = str(project.get("path_with_namespace") or project.get("name") or "")
        if not project_path:
            raise ValueError("GitLab project path is required")
        started_at_value = pipeline.get("created_at") or pipeline.get("finished_at")
        if not started_at_value:
            raise ValueError("GitLab pipeline timestamp is required")
        started_at = datetime.fromisoformat(str(started_at_value).replace("Z", "+00:00"))
        pipeline_url = str(pipeline.get("url", ""))

        return [
            IncidentEvent(
                source=IncidentSource.GITLAB_CI,
                kind=IncidentKind.CI_FAILURE,
                external_id=pipeline_id,
                service=project_path,
                title=f"Pipeline failed: {pipeline.get('name') or pipeline.get('ref', 'unknown')}",
                severity="high",
                started_at=started_at,
                correlation_id=f"gitlab:{project_path}:{pipeline_id}",
                evidence_refs=(pipeline_url,) if pipeline_url else (),
                metadata={
                    "project_id": project.get("id"),
                    "sha": pipeline.get("sha"),
                    "ref": pipeline.get("ref"),
                    "source": pipeline.get("source"),
                    "stages": pipeline.get("stages", []),
                    "target_branch": project.get("default_branch", "main"),
                    "allowed_actions": (
                        ["prepare_draft_change"] if self._remediation_profiles else []
                    ),
                    "remediation_check_profiles": list(self._remediation_profiles),
                },
            )
        ]
