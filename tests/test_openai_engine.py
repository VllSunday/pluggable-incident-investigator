from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from incident_investigator.domain import (
    EvidenceItem,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    ReflectionDecision,
    ReflectionOutcome,
)
from incident_investigator.engines.openai_engine import (
    HypothesisBatch,
    HypothesisCandidate,
    OpenAIInvestigationEngine,
)


class FakeResponses:
    def __init__(self, outputs) -> None:
        self.outputs = iter(outputs)

    async def parse(self, **kwargs):
        del kwargs
        return SimpleNamespace(output_parsed=next(self.outputs))


class FakeClient:
    def __init__(self, outputs) -> None:
        self.responses = FakeResponses(outputs)


def incident() -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.GITHUB_ACTIONS,
        kind=IncidentKind.CI_FAILURE,
        external_id="42",
        service="acme/repo",
        title="CI failed",
        started_at=datetime.now(UTC),
        correlation_id="github:acme/repo:42",
        metadata={"allowed_actions": ["create_draft_pr"]},
    )


@pytest.mark.asyncio
async def test_engine_maps_structured_hypothesis_and_reflection() -> None:
    evidence = EvidenceItem(
        kind="ci_job_log", source_uri="memory://log", summary="AssertionError"
    )
    engine = OpenAIInvestigationEngine(
        FakeClient(
            [
                HypothesisBatch(
                    hypotheses=[
                        HypothesisCandidate(
                            statement="Test expectation is stale",
                            confidence=0.9,
                            supporting_evidence_ids=[evidence.evidence_id],
                            contradicting_evidence_ids=[],
                            required_checks=[],
                            verified=True,
                        )
                    ]
                ),
                ReflectionDecision(
                    outcome=ReflectionOutcome.READY_FOR_ACTION,
                    critique="The failing assertion directly identifies the mismatch",
                ),
            ]
        )
    )

    hypotheses = await engine.generate_hypotheses(incident(), [evidence])
    reflection = await engine.reflect(incident(), [evidence], hypotheses)

    assert hypotheses[0].verified is True
    assert hypotheses[0].supporting_evidence_ids == [evidence.evidence_id]
    assert reflection.outcome is ReflectionOutcome.READY_FOR_ACTION


@pytest.mark.asyncio
async def test_engine_rejects_unknown_evidence_citation() -> None:
    evidence = EvidenceItem(kind="log", source_uri="memory://log", summary="failure")
    other = EvidenceItem(kind="log", source_uri="memory://other", summary="other")
    engine = OpenAIInvestigationEngine(
        FakeClient(
            [
                HypothesisBatch(
                    hypotheses=[
                        HypothesisCandidate(
                            statement="Unsupported claim",
                            confidence=0.9,
                            supporting_evidence_ids=[other.evidence_id],
                            contradicting_evidence_ids=[],
                            required_checks=[],
                            verified=True,
                        )
                    ]
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="not supplied"):
        await engine.generate_hypotheses(incident(), [evidence])
