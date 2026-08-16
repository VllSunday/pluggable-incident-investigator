from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langgraph.types import Command

from incident_investigator.core.graph import GraphServices, build_investigation_graph, initial_state
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.runtime import SafeActionRunner
from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    ReflectionDecision,
    ReflectionOutcome,
    RiskLevel,
)


class FakeEvidenceProvider:
    name = "fake_logs"
    capabilities = frozenset({"logs"})
    sources = None

    async def collect(self, incident: IncidentEvent, request: str):
        del incident, request
        return [
            EvidenceItem(
                kind="log",
                source_uri="memory://logs/1",
                summary="Connection refused to database",
            )
        ]


class TrackingEvidenceProvider(FakeEvidenceProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def collect(self, incident: IncidentEvent, request: str):
        self.calls += 1
        return await super().collect(incident, request)


class FakeEngine:
    async def generate_hypotheses(self, incident: IncidentEvent, evidence):
        del incident
        return [
            Hypothesis(
                statement="Database is unavailable",
                confidence=0.95,
                supporting_evidence_ids=[evidence[0].evidence_id],
                verified=True,
            )
        ]

    async def reflect(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence, hypotheses
        return ReflectionDecision(
            outcome=ReflectionOutcome.READY_FOR_ACTION,
            critique="Root cause is supported by direct connection error evidence",
        )

    async def propose_action(self, incident: IncidentEvent, evidence, hypotheses):
        del evidence, hypotheses
        return ActionProposal(
            tool_name="restart_demo_database",
            description="Restart the demo database container",
            risk=RiskLevel.HIGH,
            idempotency_key=f"{incident.incident_id}:restart-database",
            rollback_plan="Stop the container and escalate",
            expected_outcome="Database target and application health checks become healthy",
        )


class GatheringEngine(FakeEngine):
    async def reflect(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence, hypotheses
        return ReflectionDecision(
            outcome=ReflectionOutcome.GATHER_MORE,
            critique="More evidence is required",
            additional_evidence_requests=("request one", "request two"),
        )


class OperatorInputEngine(FakeEngine):
    async def generate_hypotheses(self, incident: IncidentEvent, evidence):
        del incident
        operator_items = [item for item in evidence if item.kind == "operator_evidence"]
        return [
            Hypothesis(
                statement=(
                    "Operator logs confirm the database refusal"
                    if operator_items
                    else "A database refusal is possible"
                ),
                confidence=0.98 if operator_items else 0.55,
                supporting_evidence_ids=[item.evidence_id for item in operator_items],
                required_checks=(
                    [] if operator_items else ["Provide the application stack trace"]
                ),
                verified=bool(operator_items),
            )
        ]

    async def reflect(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence
        if hypotheses[0].verified:
            return ReflectionDecision(
                outcome=ReflectionOutcome.READY_FOR_ACTION,
                critique="The operator evidence directly confirms the cause",
            )
        return ReflectionDecision(
            outcome=ReflectionOutcome.GATHER_MORE,
            critique="The application stack trace is required to verify the cause",
            additional_evidence_requests=("Provide the application stack trace",),
        )

class FakeExecutor:
    name = "restart_demo_database"

    async def execute(self, proposal: ActionProposal):
        return ActionResult(
            action_id=proposal.action_id,
            success=True,
            summary="Demo database restarted",
        )


class FakeRecoveryVerifier:
    async def verify(self, incident: IncidentEvent, action_result: ActionResult):
        del incident, action_result
        return True, "Health check passed"


def incident() -> IncidentEvent:
    return IncidentEvent(
        incident_id=uuid4(),
        source=IncidentSource.ALERTMANAGER,
        kind=IncidentKind.RUNTIME_ALERT,
        external_id="fp-1",
        service="payments",
        title="High error rate",
        severity="critical",
        started_at=datetime.now(UTC),
        correlation_id="alertmanager:fp-1",
    )


@pytest.mark.asyncio
async def test_graph_pauses_before_high_risk_action_and_resumes() -> None:
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FakeEvidenceProvider(),),
            engine=FakeEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner(
                {"restart_demo_database": FakeExecutor()}
            ),
            recovery_verifier=FakeRecoveryVerifier(),
        )
    )
    config = {"configurable": {"thread_id": "incident-test-1"}}

    paused = await graph.ainvoke(initial_state(incident()), config=config)

    assert paused["status"] == "action_proposed"
    assert paused["__interrupt__"]
    assert paused["action_result"] is None

    completed = await graph.ainvoke(Command(resume={"approved": True}), config=config)

    assert completed["status"] == "recovered"
    assert completed["action_result"]["success"] is True
    assert completed["recovery_verified"] is True


@pytest.mark.asyncio
async def test_graph_exits_before_starting_calls_when_tool_budget_is_exhausted() -> None:
    provider = TrackingEvidenceProvider()
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(provider,),
            engine=FakeEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=FakeRecoveryVerifier(),
            max_tool_calls=0,
        )
    )

    completed = await graph.ainvoke(
        initial_state(incident()),
        config={"configurable": {"thread_id": "incident-budget-test"}},
    )

    assert completed["status"] == "evidence_budget_exhausted"
    assert completed["errors"] == ["budget:tool_call_budget_exhausted"]
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_graph_uses_remaining_budget_then_requests_operator_input() -> None:
    provider = TrackingEvidenceProvider()
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(provider,),
            engine=GatheringEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=FakeRecoveryVerifier(),
            max_tool_calls=2,
        )
    )

    paused = await graph.ainvoke(
        initial_state(incident(), max_iterations=2),
        config={"configurable": {"thread_id": "incident-partial-budget-test"}},
    )

    assert paused["status"] == "input_required"
    assert paused["__interrupt__"][0].value["type"] == "evidence_request"
    assert paused["errors"] == ["budget:tool_call_budget_truncated"]
    assert paused["tool_calls_used"] == 2
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_graph_resumes_same_thread_with_operator_evidence() -> None:
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FakeEvidenceProvider(),),
            engine=OperatorInputEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner(
                {"restart_demo_database": FakeExecutor()}
            ),
            recovery_verifier=FakeRecoveryVerifier(),
        )
    )
    config = {"configurable": {"thread_id": "operator-input-flow"}}

    paused = await graph.ainvoke(
        initial_state(incident(), max_iterations=1), config=config
    )
    request_id = paused["information_request"]["request_id"]
    submitted = EvidenceItem(
        kind="operator_evidence",
        source_uri=f"operator://incident/{request_id}/stack.log",
        summary="ConnectionRefusedError: database refused the connection",
        attributes={"request_id": request_id, "provider": "operator"},
    )

    action_paused = await graph.ainvoke(
        Command(resume={"evidence": [submitted.model_dump(mode="json")]}),
        config=config,
    )

    assert action_paused["status"] == "action_proposed"
    assert action_paused["human_input_rounds"] == 1
    assert any(item["kind"] == "operator_evidence" for item in action_paused["evidence"])
    assert action_paused["__interrupt__"][0].value["type"] == "action_approval"

    completed = await graph.ainvoke(
        Command(resume={"approved": True}), config=config
    )
    assert completed["status"] == "recovered"


@pytest.mark.asyncio
async def test_graph_escalates_when_operator_cannot_supply_evidence() -> None:
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FakeEvidenceProvider(),),
            engine=OperatorInputEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=FakeRecoveryVerifier(),
        )
    )
    config = {"configurable": {"thread_id": "operator-decline-flow"}}
    await graph.ainvoke(initial_state(incident(), max_iterations=1), config=config)

    completed = await graph.ainvoke(
        Command(resume={"unable": True}), config=config
    )

    assert completed["status"] == "operator_escalated"
