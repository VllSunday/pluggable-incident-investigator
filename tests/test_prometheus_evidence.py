from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from incident_investigator.adapters.evidence import PrometheusEvidenceProvider
from incident_investigator.domain import (
    IncidentEvent,
    IncidentKind,
    IncidentSource,
)


@pytest.mark.asyncio
async def test_prometheus_provider_collects_service_metric_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == 'up{job="payments"}'
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"job": "payments"},
                            "value": [1_786_531_200, "0"],
                        }
                    ],
                },
            },
        )

    async with httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(handler)
    ) as client:
        evidence = await PrometheusEvidenceProvider(client).collect(
            IncidentEvent(
                source=IncidentSource.ALERTMANAGER,
                kind=IncidentKind.RUNTIME_ALERT,
                external_id="fp-1",
                service="payments",
                title="Target down",
                started_at=datetime.now(UTC),
                correlation_id="alertmanager:fp-1",
            ),
            "collect metrics",
        )

    assert len(evidence) == 1
    assert evidence[0].kind == "metric_snapshot"
    assert evidence[0].attributes["query"] == 'up{job="payments"}'
