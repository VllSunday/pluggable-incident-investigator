from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from incident_investigator.adapters.events import (
    AlertmanagerEventAdapter,
    GitHubActionsEventAdapter,
    GitLabCIEventAdapter,
)
from incident_investigator.api import create_app
from incident_investigator.domain import IncidentEvent


class RecordingSink:
    def __init__(self) -> None:
        self.incidents: list[IncidentEvent] = []

    async def accept(self, incident: IncidentEvent) -> None:
        self.incidents.append(incident)

    async def list_incidents(self, limit: int = 100):
        del limit
        return []


def app_and_sink():
    sink = RecordingSink()
    app = create_app(
        github_adapter=GitHubActionsEventAdapter("github-secret"),
        gitlab_adapter=GitLabCIEventAdapter("gitlab-secret"),
        alertmanager_adapter=AlertmanagerEventAdapter("alert-token"),
        incident_sink=sink,
        control_plane=sink,
        admin_api_token="test-admin-token-long",
    )
    return app, sink


@pytest.mark.asyncio
async def test_health() -> None:
    app, _ = app_and_sink()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_github_webhook_is_verified_normalized_and_dispatched() -> None:
    app, sink = app_and_sink()
    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/payments"},
        "workflow_run": {
            "id": 42,
            "name": "CI",
            "conclusion": "failure",
            "run_started_at": "2026-08-12T10:00:00Z",
            "head_sha": "abc123",
            "head_branch": "main",
            "event": "push",
        },
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        b"github-secret", body, hashlib.sha256
    ).hexdigest()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/github",
            content=body,
            headers={"content-type": "application/json", "x-hub-signature-256": signature},
        )

    assert response.status_code == 202
    assert response.json()["accepted"] == 1
    assert len(sink.incidents) == 1
    assert sink.incidents[0].service == "acme/payments"


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_credentials() -> None:
    app, sink = app_and_sink()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/alertmanager",
            json={"status": "firing", "alerts": []},
            headers={"x-incident-token": "wrong"},
        )

    assert response.status_code == 401
    assert sink.incidents == []


@pytest.mark.asyncio
async def test_incident_api_requires_admin_token() -> None:
    app, _ = app_and_sink()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/api/incidents")
        authorized = await client.get(
            "/api/incidents",
            headers={"authorization": "Bearer test-admin-token-long"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
