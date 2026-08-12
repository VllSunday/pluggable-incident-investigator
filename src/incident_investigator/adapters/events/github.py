from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from incident_investigator.domain import IncidentEvent, IncidentKind, IncidentSource


class InvalidWebhookSignature(ValueError):
    pass


class GitHubActionsEventAdapter:
    name = "github_actions"

    def __init__(
        self, secret: str, *, remediation_profiles: tuple[str, ...] = ()
    ) -> None:
        if not secret:
            raise ValueError("GitHub webhook secret must not be empty")
        self._secret = secret.encode()
        self._remediation_profiles = remediation_profiles

    def verify(self, body: bytes, headers: Mapping[str, str]) -> None:
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidWebhookSignature("Invalid GitHub webhook signature")

    def normalize(self, payload: Mapping[str, Any]) -> list[IncidentEvent]:
        if payload.get("action") != "completed":
            return []

        run = payload.get("workflow_run")
        repository = payload.get("repository")
        if not isinstance(run, Mapping) or not isinstance(repository, Mapping):
            raise ValueError("GitHub payload is missing workflow_run or repository")
        if run.get("conclusion") != "failure":
            return []

        run_id = str(run["id"])
        repository_name = str(repository["full_name"])
        started_at = datetime.fromisoformat(str(run["run_started_at"]).replace("Z", "+00:00"))
        html_url = str(run.get("html_url", ""))

        return [
            IncidentEvent(
                source=IncidentSource.GITHUB_ACTIONS,
                kind=IncidentKind.CI_FAILURE,
                external_id=run_id,
                service=repository_name,
                title=f"Workflow failed: {run.get('name', 'unknown workflow')}",
                severity="high",
                started_at=started_at,
                correlation_id=f"github:{repository_name}:{run_id}",
                evidence_refs=(html_url,) if html_url else (),
                metadata={
                    "head_sha": run.get("head_sha"),
                    "head_branch": run.get("head_branch"),
                    "event": run.get("event"),
                    "run_attempt": run.get("run_attempt", 1),
                    "target_branch": repository.get("default_branch", "main"),
                    "allowed_actions": (
                        ["prepare_draft_change"] if self._remediation_profiles else []
                    ),
                    "remediation_check_profiles": list(self._remediation_profiles),
                },
            )
        ]
