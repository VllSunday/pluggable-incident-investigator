from __future__ import annotations

from datetime import UTC, datetime

import pytest

from incident_investigator.application import IncidentStatus
from incident_investigator.application.repository import SqliteIncidentRepository
from incident_investigator.domain import (
    IncidentEvent,
    IncidentKind,
    IncidentSource,
)


def event(correlation_id: str = "github:acme/repo:42") -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.GITHUB_ACTIONS,
        kind=IncidentKind.CI_FAILURE,
        external_id="42",
        service="acme/repo",
        title="CI failed",
        started_at=datetime.now(UTC),
        correlation_id=correlation_id,
    )


@pytest.mark.asyncio
async def test_repository_deduplicates_webhook_deliveries(tmp_path) -> None:
    repository = SqliteIncidentRepository(tmp_path / "incidents.db")
    await repository.initialize()

    first, first_created = await repository.enqueue(event())
    second, second_created = await repository.enqueue(event())

    assert first_created is True
    assert second_created is False
    assert first.incident_id == second.incident_id
    assert len(await repository.list()) == 1


@pytest.mark.asyncio
async def test_repository_claims_once_and_recovers_crashed_run(tmp_path) -> None:
    repository = SqliteIncidentRepository(tmp_path / "incidents.db")
    await repository.initialize()
    await repository.enqueue(event())

    claimed = await repository.claim_next()

    assert claimed is not None
    assert claimed.status is IncidentStatus.RUNNING
    assert await repository.claim_next() is None

    assert await repository.recover_interrupted_runs() == 1
    reclaimed = await repository.claim_next()
    assert reclaimed is not None
    assert reclaimed.incident_id == claimed.incident_id

