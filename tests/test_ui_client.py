from __future__ import annotations

import httpx
import pytest

from incident_investigator.ui.client import DashboardAPIError, IncidentAPIClient


def test_client_lists_incidents(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*args, **kwargs):
        request = httpx.Request(args[0], args[1], headers=kwargs.get("headers"))
        return httpx.Response(200, request=request, json=[{"incident_id": "one"}])

    monkeypatch.setattr(httpx, "request", fake_request)
    client = IncidentAPIClient("http://core:8000", "a" * 16)

    assert client.list_incidents() == [{"incident_id": "one"}]


def test_client_reports_control_plane_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*args, **kwargs):
        request = httpx.Request(args[0], args[1])
        return httpx.Response(
            409, request=request, json={"detail": "Incident is no longer waiting"}
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    client = IncidentAPIClient("http://core:8000", "a" * 16)

    with pytest.raises(DashboardAPIError, match="no longer waiting"):
        client.decide_approval("one", approved=True)


def test_client_requires_a_real_admin_token() -> None:
    assert not IncidentAPIClient("http://core:8000", "short").configured
    assert IncidentAPIClient("http://core:8000", "a" * 16).configured
