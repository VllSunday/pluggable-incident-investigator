from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from incident_investigator.adapters.events import (
    AlertmanagerEventAdapter,
    GitHubActionsEventAdapter,
    GitLabCIEventAdapter,
)
from incident_investigator.adapters.events.alertmanager import InvalidWebhookToken
from incident_investigator.adapters.events.github import InvalidWebhookSignature
from incident_investigator.adapters.events.gitlab import InvalidGitLabWebhookToken
from incident_investigator.domain import IncidentKind, IncidentSource


def test_github_normalizes_failed_workflow() -> None:
    adapter = GitHubActionsEventAdapter("secret")
    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/payments"},
        "workflow_run": {
            "id": 42,
            "name": "CI",
            "conclusion": "failure",
            "run_started_at": "2026-08-12T10:00:00Z",
            "html_url": "https://github.example/runs/42",
            "head_sha": "abc123",
            "head_branch": "main",
            "event": "push",
        },
    }

    events = adapter.normalize(payload)

    assert len(events) == 1
    assert events[0].source is IncidentSource.GITHUB_ACTIONS
    assert events[0].kind is IncidentKind.CI_FAILURE
    assert events[0].service == "acme/payments"
    assert events[0].correlation_id == "github:acme/payments:42"


def test_github_ignores_successful_workflow() -> None:
    adapter = GitHubActionsEventAdapter("secret")
    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/payments"},
        "workflow_run": {"conclusion": "success"},
    }

    assert adapter.normalize(payload) == []


def test_github_verifies_signature() -> None:
    adapter = GitHubActionsEventAdapter("secret")
    body = json.dumps({"event": "test"}).encode()
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()

    adapter.verify(body, {"x-hub-signature-256": signature})
    with pytest.raises(InvalidWebhookSignature):
        adapter.verify(body, {"x-hub-signature-256": "sha256=wrong"})


def test_alertmanager_normalizes_firing_alerts() -> None:
    adapter = AlertmanagerEventAdapter("token")
    payload = {
        "status": "firing",
        "groupKey": "group-1",
        "alerts": [
            {
                "status": "firing",
                "fingerprint": "fp-123",
                "startsAt": "2026-08-12T10:00:00Z",
                "generatorURL": "http://prometheus/graph",
                "labels": {
                    "alertname": "HighErrorRate",
                    "service": "payments",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "Payments error rate is high",
                    "description": "HTTP 500 rate is above 5%",
                },
            }
        ],
    }

    events = adapter.normalize(payload)

    assert len(events) == 1
    assert events[0].source is IncidentSource.ALERTMANAGER
    assert events[0].kind is IncidentKind.RUNTIME_ALERT
    assert events[0].service == "payments"
    assert events[0].severity == "critical"


def test_alertmanager_rejects_bad_token() -> None:
    adapter = AlertmanagerEventAdapter("token")

    with pytest.raises(InvalidWebhookToken):
        adapter.verify(b"{}", {"x-incident-token": "wrong"})


def test_alertmanager_accepts_bearer_token() -> None:
    adapter = AlertmanagerEventAdapter("token")

    adapter.verify(b"{}", {"authorization": "Bearer token"})


def test_gitlab_normalizes_failed_pipeline() -> None:
    adapter = GitLabCIEventAdapter("secret")
    payload = {
        "object_kind": "pipeline",
        "project": {"id": 17, "path_with_namespace": "acme/payments"},
        "object_attributes": {
            "id": 91,
            "name": "Main pipeline",
            "ref": "main",
            "sha": "abc123",
            "status": "failed",
            "source": "push",
            "created_at": "2026-08-12T10:00:00Z",
            "url": "https://gitlab.example/acme/payments/-/pipelines/91",
            "stages": ["build", "test"],
        },
    }

    events = adapter.normalize(payload)

    assert len(events) == 1
    assert events[0].source is IncidentSource.GITLAB_CI
    assert events[0].kind is IncidentKind.CI_FAILURE
    assert events[0].service == "acme/payments"
    assert events[0].correlation_id == "gitlab:acme/payments:91"


def test_gitlab_rejects_bad_token() -> None:
    adapter = GitLabCIEventAdapter("secret")

    with pytest.raises(InvalidGitLabWebhookToken):
        adapter.verify(b"{}", {"x-gitlab-token": "wrong"})
