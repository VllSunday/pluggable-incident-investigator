from datetime import UTC, datetime

import pytest

from incident_investigator.demo import RuntimeFixtureInvestigationEngine
from incident_investigator.domain import (
    EvidenceItem,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    ReflectionOutcome,
)


@pytest.mark.asyncio
async def test_runtime_fixture_requires_independent_evidence_before_action() -> None:
    engine = RuntimeFixtureInvestigationEngine()
    incident = IncidentEvent(
        source=IncidentSource.ALERTMANAGER,
        kind=IncidentKind.RUNTIME_ALERT,
        external_id="fixture-alert",
        service="runtime-demo",
        title="High error ratio",
        started_at=datetime.now(UTC),
        correlation_id="fixture-alert",
        metadata={"allowed_actions": ["rollback_runtime_config"]},
    )
    evidence = [
        EvidenceItem(
            kind="application_log",
            source_uri="fixture://logs",
            summary="runtime override is active",
        ),
        EvidenceItem(
            kind="metric_snapshot",
            source_uri="fixture://prometheus",
            summary="error ratio is 0.8",
        ),
    ]

    hypotheses = await engine.generate_hypotheses(incident, evidence)
    reflection = await engine.reflect(incident, evidence, hypotheses)
    action = await engine.propose_action(incident, evidence, hypotheses)

    assert hypotheses[0].verified is True
    assert set(hypotheses[0].supporting_evidence_ids) == {
        item.evidence_id for item in evidence
    }
    assert reflection.outcome is ReflectionOutcome.READY_FOR_ACTION
    assert action is not None
    assert action.tool_name == "rollback_runtime_config"
    assert action.arguments["target_error_fraction"] == 0.0
