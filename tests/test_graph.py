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
