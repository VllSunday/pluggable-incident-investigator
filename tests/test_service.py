from __future__ import annotations

from datetime import UTC, datetime

import pytest

from incident_investigator.application import IncidentStatus, InvestigationService
from incident_investigator.application.repository import SqliteIncidentRepository
from incident_investigator.domain import (
    IncidentEvent,
    IncidentKind,
    IncidentSource,
)


class EscalatingGraph:
    def __init__(self) -> None:
        self.configs = []

    async def ainvoke(self, value, config):
        del value
        self.configs.append(config)
        return {"status": "escalated", "evidence": [], "errors": []}


class BudgetExhaustedGraph:
    async def ainvoke(self, value, config):
        del value, config
        return {
            "status": "evidence_budget_exhausted",
            "evidence": [],
            "errors": ["budget:tool_call_budget_exhausted"],
        }


def event() -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.ALERTMANAGER,
        kind=IncidentKind.RUNTIME_ALERT,
        external_id="fp-1",
        service="payments",
        title="High error rate",
        started_at=datetime.now(UTC),
        correlation_id="alertmanager:fp-1",
    )


@pytest.mark.asyncio
async def test_service_processes_queued_incident(tmp_path) -> None:
    repository = SqliteIncidentRepository(tmp_path / "incidents.db")
    await repository.initialize()
    graph = EscalatingGraph()
    service = InvestigationService(repository, graph)
    await service.accept(event())

    assert await service.process_next() is True
    records = await service.list_incidents()

    assert len(records) == 1
    assert records[0].status is IncidentStatus.ESCALATED
    assert records[0].graph_status == "escalated"
    assert graph.configs[0]["tags"] == [
        "incident-investigator",
        "source:alertmanager",
        "kind:runtime_alert",
    ]
    assert graph.configs[0]["metadata"]["service"] == "payments"
    assert graph.configs[0]["metadata"]["incident_id"] == str(records[0].incident_id)


@pytest.mark.asyncio
async def test_service_escalates_when_evidence_budget_is_exhausted(tmp_path) -> None:
    repository = SqliteIncidentRepository(tmp_path / "incidents.db")
    await repository.initialize()
    service = InvestigationService(repository, BudgetExhaustedGraph())
    await service.accept(event().model_copy(update={"correlation_id": "budget:fp-1"}))

    assert await service.process_next() is True
    records = await service.list_incidents()

    assert records[0].status is IncidentStatus.ESCALATED
    assert records[0].graph_status == "evidence_budget_exhausted"
