from __future__ import annotations

import asyncio
import json
from time import monotonic

import httpx

from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    EvidenceItem,
    IncidentEvent,
    IncidentSource,
)


class RuntimeLogEvidenceProvider:
    """Read-only adapter for a service exposing structured diagnostic logs."""

    name = "runtime_logs"
    capabilities = frozenset({"application_logs", "configuration"})
    sources = frozenset({IncidentSource.ALERTMANAGER})

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def collect(self, incident: IncidentEvent, request: str):
        del request
        if incident.source is not IncidentSource.ALERTMANAGER:
            return []
        response = await self._client.get(
            "/diagnostics/logs", params={"service": incident.service, "limit": 100}
        )
        response.raise_for_status()
        payload = response.json()
        return [
            EvidenceItem(
                kind="application_log",
                source_uri=f"runtime-logs://{incident.service}/incident-window",
                summary=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                attributes={
                    "provider": self.name,
                    "service": incident.service,
                    "record_count": len(payload.get("records", [])),
                },
            )
        ]


class RuntimeConfigRollbackExecutor:
    """Narrow executor: it can only restore one allowlisted service to a safe value."""

    name = "rollback_runtime_config"

    def __init__(
        self, client: httpx.AsyncClient, *, allowed_service: str = "runtime-demo"
    ) -> None:
        self._client = client
        self._allowed_service = allowed_service

    async def execute(self, proposal: ActionProposal) -> ActionResult:
        service = proposal.arguments.get("service")
        target = proposal.arguments.get("target_error_fraction")
        if service != self._allowed_service or target != 0.0:
            raise ValueError("Runtime rollback arguments are outside the executor allowlist")
        try:
            response = await self._client.post(
                "/admin/rollback",
                json={"service": service, "target_error_fraction": target},
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise TimeoutError("Runtime control endpoint timed out") from error
        except httpx.RequestError as error:
            raise ConnectionError("Runtime control endpoint is unavailable") from error
        payload = response.json()
        return ActionResult(
            action_id=proposal.action_id,
            success=True,
            summary=(
                f"Runtime configuration rolled back from error fraction "
                f"{payload['previous_error_fraction']} to {payload['current_error_fraction']}."
            ),
            external_reference="runtime-demo://configuration/runtime_override",
            details=payload,
        )


class RuntimeRecoveryVerifier:
    """Verify both service health and that Prometheus no longer reports a firing alert."""

    def __init__(
        self,
        runtime_client: httpx.AsyncClient,
        prometheus_client: httpx.AsyncClient,
        *,
        timeout_seconds: float = 45,
        poll_seconds: float = 2,
    ) -> None:
        self._runtime = runtime_client
        self._prometheus = prometheus_client
        self._timeout_seconds = timeout_seconds
        self._poll_seconds = poll_seconds

    async def verify(
        self, incident: IncidentEvent, action_result: ActionResult
    ) -> tuple[bool, str]:
        if not action_result.success:
            return False, "The action failed; recovery was not attempted."
        deadline = monotonic() + self._timeout_seconds
        last_health = "unavailable"
        last_alert = "unknown"
        while monotonic() < deadline:
            try:
                health = await self._runtime.get("/health")
                last_health = health.json().get("status", "unknown")
                alerts = await self._prometheus.get("/api/v1/alerts")
                alerts.raise_for_status()
                firing = [
                    item
                    for item in alerts.json().get("data", {}).get("alerts", [])
                    if item.get("state") == "firing"
                    and item.get("labels", {}).get("service") == incident.service
                ]
                last_alert = "firing" if firing else "resolved"
                if health.status_code == 200 and not firing:
                    return (
                        True,
                        "Service health is healthy and Prometheus reports no firing alert "
                        f"for {incident.service}.",
                    )
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(self._poll_seconds)
        return (
            False,
            f"Recovery timeout: service health={last_health}, alert={last_alert}.",
        )
