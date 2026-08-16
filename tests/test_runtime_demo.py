from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from incident_investigator.adapters.runtime_demo import (
    RuntimeConfigRollbackExecutor,
    RuntimeLogEvidenceProvider,
    RuntimeRecoveryVerifier,
)
from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    RiskLevel,
)


def incident() -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.ALERTMANAGER,
        kind=IncidentKind.RUNTIME_ALERT,
        external_id="runtime-1",
        service="runtime-demo",
        title="High error rate",
        started_at=datetime.now(UTC),
        correlation_id="alertmanager:runtime-1",
    )


def proposal(**arguments: object) -> ActionProposal:
    return ActionProposal(
        tool_name="rollback_runtime_config",
        description="Rollback unsafe runtime override",
        arguments={"service": "runtime-demo", "target_error_fraction": 0.0, **arguments},
        risk=RiskLevel.HIGH,
        idempotency_key="runtime-1:rollback",
        rollback_plan="Restore the previous override",
        expected_outcome="Error rate returns to normal",
    )


@pytest.mark.asyncio
async def test_runtime_logs_are_collected_automatically() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/diagnostics/logs"
        return httpx.Response(
            200,
            json={
                "service": "runtime-demo",
                "records": [{"level": "ERROR", "configured_error_fraction": 0.8}],
            },
        )

    async with httpx.AsyncClient(
        base_url="http://runtime", transport=httpx.MockTransport(handler)
    ) as client:
        evidence = await RuntimeLogEvidenceProvider(client).collect(
            incident(), "inspect application logs"
        )

    assert evidence[0].kind == "application_log"
    assert evidence[0].attributes["record_count"] == 1
    assert "configured_error_fraction" in evidence[0].summary


@pytest.mark.asyncio
async def test_runtime_executor_enforces_allowlisted_arguments() -> None:
    async with httpx.AsyncClient(base_url="http://runtime") as client:
        executor = RuntimeConfigRollbackExecutor(client)
        with pytest.raises(ValueError, match="outside the executor allowlist"):
            await executor.execute(proposal(service="production"))


@pytest.mark.asyncio
async def test_runtime_executor_applies_narrow_rollback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/rollback"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "status": "applied",
                "service": "runtime-demo",
                "previous_error_fraction": 0.8,
                "current_error_fraction": 0.0,
            },
        )

    async with httpx.AsyncClient(
        base_url="http://runtime",
        headers={"Authorization": "Bearer secret"},
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await RuntimeConfigRollbackExecutor(client).execute(proposal())

    assert result.success is True
    assert result.details["current_error_fraction"] == 0.0


@pytest.mark.asyncio
async def test_recovery_requires_health_and_resolved_prometheus_alert() -> None:
    def runtime_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "healthy"})

    def prometheus_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "data": {"alerts": []}})

    async with (
        httpx.AsyncClient(
            base_url="http://runtime", transport=httpx.MockTransport(runtime_handler)
        ) as runtime_client,
        httpx.AsyncClient(
            base_url="http://prometheus",
            transport=httpx.MockTransport(prometheus_handler),
        ) as prometheus_client,
    ):
        verifier = RuntimeRecoveryVerifier(runtime_client, prometheus_client)
        verified, summary = await verifier.verify(
            incident(),
            ActionResult(action_id=proposal().action_id, success=True, summary="applied"),
        )

    assert verified is True
    assert "no firing alert" in summary
