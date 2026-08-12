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
    async def ainvoke(self, value, config):
        del value, config
        return {"status": "escalated", "evidence": [], "errors": []}


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
    service = InvestigationService(repository, EscalatingGraph())
    await service.accept(event())

    assert await service.process_next() is True
    records = await service.list_incidents()

    assert len(records) == 1
    assert records[0].status is IncidentStatus.ESCALATED
    assert records[0].graph_status == "escalated"

