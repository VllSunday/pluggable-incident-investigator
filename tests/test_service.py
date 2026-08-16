from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langgraph.types import Command

from incident_investigator.application import IncidentStatus, InvestigationService
from incident_investigator.application.operator_input import (
    OperatorEvidenceStore,
    OperatorEvidenceSubmission,
)
from incident_investigator.application.repository import SqliteIncidentRepository
from incident_investigator.domain import (
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    InformationRequest,
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


class InputInterruptGraph:
    def __init__(self, request: InformationRequest) -> None:
        self.request = request
        self.resume_payload = None

    async def ainvoke(self, value, config):
        del config
        if isinstance(value, Command):
            self.resume_payload = value.resume
            return {
                "status": "action_proposed",
                "information_request": None,
                "evidence": value.resume.get("evidence", []),
                "__interrupt__": [{"type": "action_approval"}],
            }
        return {
            "status": "input_required",
            "information_request": self.request.model_dump(mode="json"),
            "evidence": [],
            "errors": [],
            "__interrupt__": [{"type": "evidence_request"}],
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


@pytest.mark.asyncio
async def test_service_stores_operator_evidence_and_resumes_checkpoint(tmp_path) -> None:
    repository = SqliteIncidentRepository(tmp_path / "incidents.db")
    await repository.initialize()
    request = InformationRequest(
        question="Provide the application stack trace",
        evidence_gap="application stack trace",
        reason="Metrics cannot identify the failing code path",
    )
    graph = InputInterruptGraph(request)
    service = InvestigationService(
        repository,
        graph,
        operator_evidence_store=OperatorEvidenceStore(tmp_path / "evidence"),
    )
    current = event().model_copy(
        update={"incident_id": uuid4(), "correlation_id": "input:fp-1"}
    )
    await service.accept(current)
    await service.process_next()
    paused = (await service.list_incidents())[0]

    assert paused.status is IncidentStatus.AWAITING_INPUT

    resumed = await service.submit_evidence(
        paused.incident_id,
        OperatorEvidenceSubmission(
            request_id=request.request_id,
            text="ConnectionRefusedError from database client",
            source_name="stack.log",
        ),
    )

    assert resumed.status is IncidentStatus.AWAITING_APPROVAL
    assert graph.resume_payload["evidence"][0]["kind"] == "operator_evidence"
