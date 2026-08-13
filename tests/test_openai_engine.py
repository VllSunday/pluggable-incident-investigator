from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from incident_investigator.core.remediation import RemediationRequest
from incident_investigator.domain import (
    EvidenceItem,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    ReflectionDecision,
    ReflectionOutcome,
    RiskLevel,
)
from incident_investigator.engines.openai_engine import (
    ActionDecision,
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
                ),
                HypothesisBatch(
                    hypotheses=[
                        HypothesisCandidate(
                            statement="Still unsupported",
                            confidence=0.9,
                            supporting_evidence_ids=[other.evidence_id],
                            contradicting_evidence_ids=[],
                            required_checks=[],
                            verified=True,
                        )
                    ]
                ),
            ]
        )
    )

    with pytest.raises(ValueError, match="not supplied"):
        await engine.generate_hypotheses(incident(), [evidence])


@pytest.mark.asyncio
async def test_engine_rejects_ready_reflection_without_verified_hypothesis() -> None:
    evidence = EvidenceItem(kind="log", source_uri="memory://log", summary="failure")
    hypothesis = HypothesisCandidate(
        statement="Possible cause",
        confidence=0.99,
        supporting_evidence_ids=[evidence.evidence_id],
        contradicting_evidence_ids=[],
        required_checks=[],
        verified=False,
    )
    engine = OpenAIInvestigationEngine(
        FakeClient(
            [
                ReflectionDecision(
                    outcome=ReflectionOutcome.READY_FOR_ACTION,
                    critique="Cause is ready",
                )
            ]
        )
    )

    reflection = await engine.reflect(incident(), [evidence], [hypothesis])

    assert reflection.outcome is ReflectionOutcome.GATHER_MORE


@pytest.mark.asyncio
async def test_engine_verifies_high_confidence_ci_hypothesis_by_evidence_quorum() -> None:
    log = EvidenceItem(kind="ci_job_log", source_uri="memory://log", summary="failed")
    diff = EvidenceItem(kind="commit_diff", source_uri="memory://diff", summary="bug")
    engine = OpenAIInvestigationEngine(
        FakeClient(
            [
                HypothesisBatch(
                    hypotheses=[
                        HypothesisCandidate(
                            statement="Code expression causes the failing output",
                            confidence=0.99,
                            supporting_evidence_ids=[log.evidence_id, diff.evidence_id],
                            contradicting_evidence_ids=[],
                            required_checks=["run tests after patch"],
                            verified=False,
                        )
                    ]
                )
            ]
        )
    )

    hypotheses = await engine.generate_hypotheses(incident(), [log, diff])

    assert hypotheses[0].verified is True


@pytest.mark.asyncio
async def test_engine_maps_typed_remediation_arguments() -> None:
    current = incident().model_copy(
        update={
            "metadata": {
                "allowed_actions": ["prepare_draft_change"],
                "head_sha": "abc123",
                "target_branch": "main",
                "remediation_check_profiles": ["python"],
            }
        }
    )
    hypothesis = HypothesisCandidate(
        statement="Retry count is off by one",
        confidence=0.99,
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        required_checks=[],
        verified=True,
    )
    decision = ActionDecision(
        should_act=True,
        tool_name="prepare_draft_change",
        description="Correct the retry count",
        arguments=RemediationRequest(
            repository="acme/repo",
            source_revision="abc123",
            target_branch="main",
            branch_name="incident-fix/42",
            title="Fix retry count",
            description="Correct the off-by-one retry calculation.",
            unified_diff="--- a/retry.py\n+++ b/retry.py\n@@ -1 +1 @@\n-2\n+1\n",
            check_profile="python",
        ),
        risk=RiskLevel.LOW,
        rollback_plan="Close the draft PR",
        expected_outcome="Tests pass",
    )
    engine = OpenAIInvestigationEngine(FakeClient([decision]))

    proposal = await engine.propose_action(current, [], [hypothesis])

    assert proposal is not None
    assert proposal.arguments["repository"] == "acme/repo"
    assert proposal.arguments["check_profile"] == "python"


@pytest.mark.asyncio
async def test_engine_aligns_unique_diff_suffix_with_evidence_path() -> None:
    current = incident().model_copy(
        update={"metadata": {"allowed_actions": ["prepare_draft_change"]}}
    )
    evidence = EvidenceItem(
        kind="commit_diff",
        source_uri="memory://diff",
        summary="... [TRUNCATED] ...",
        attributes={"changed_files": ["src/retry_policy.py"]},
    )
    hypothesis = HypothesisCandidate(
        statement="Retry policy is incorrect",
        confidence=1,
        supporting_evidence_ids=[evidence.evidence_id],
        contradicting_evidence_ids=[],
        required_checks=[],
        verified=True,
    )
    decision = ActionDecision(
        should_act=True,
        tool_name="prepare_draft_change",
        description="Fix retry policy",
        arguments=RemediationRequest(
            repository="acme/repo",
            source_revision="abc123",
            target_branch="main",
            branch_name="incident-fix/42",
            title="Fix retry policy",
            description="Fix retry policy.",
            unified_diff="--- a/retry_policy.py\n+++ b/retry_policy.py\n@@ -1 +1 @@\n-old\n+new\n",
            check_profile="python",
        ),
        risk=RiskLevel.LOW,
        rollback_plan="Close the draft PR",
        expected_outcome="Tests pass",
    )
    engine = OpenAIInvestigationEngine(FakeClient([decision]))

    proposal = await engine.propose_action(current, [evidence], [hypothesis])

    assert proposal is not None
    assert "--- a/src/retry_policy.py" in proposal.arguments["unified_diff"]
    assert "+++ b/src/retry_policy.py" in proposal.arguments["unified_diff"]


@pytest.mark.asyncio
async def test_engine_reflects_once_on_noop_patch() -> None:
    current = incident().model_copy(
        update={"metadata": {"allowed_actions": ["prepare_draft_change"]}}
    )

    def decision(diff: str) -> ActionDecision:
        return ActionDecision(
            should_act=True,
            tool_name="prepare_draft_change",
            description="Fix retry policy",
            arguments=RemediationRequest(
                repository="acme/repo",
                source_revision="abc123",
                target_branch="main",
                branch_name="incident-fix/42",
                title="Fix retry policy",
                description="Fix retry policy.",
                unified_diff=diff,
                check_profile="python",
            ),
            risk=RiskLevel.LOW,
            rollback_plan="Close the draft PR",
            expected_outcome="Tests pass",
        )

    noop = (
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
        "-return 2 ** attempt\n+return 2**attempt\n"
    )
    fixed = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    engine = OpenAIInvestigationEngine(FakeClient([decision(noop), decision(fixed)]))

    proposal = await engine.propose_action(current, [], [
        HypothesisCandidate(
            statement="Bug is verified",
            confidence=1,
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            required_checks=[],
            verified=True,
        )
    ])

    assert proposal is not None
    assert "+new" in proposal.arguments["unified_diff"]
