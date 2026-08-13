from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.types import Command

from incident_investigator.core.graph import (
    GraphServices,
    build_investigation_graph,
    initial_state,
)
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.remediation import (
    CheckResult,
    RemediationBlockedError,
    RemediationPipeline,
    RemediationReview,
    _apply_patch,
)
from incident_investigator.core.runtime import SafeActionRunner
from incident_investigator.core.scm import ChangeRequestResult, PreparedChangeSpec
from incident_investigator.domain import (
    ActionProposal,
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    IncidentKind,
    IncidentSource,
    ReflectionDecision,
    ReflectionOutcome,
    RiskLevel,
)

PATCH = """--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-BROKEN = True
+BROKEN = False
"""


class FakeSourceControl:
    platform = IncidentSource.GITHUB_ACTIONS

    def __init__(self) -> None:
        self.published: PreparedChangeSpec | None = None

    async def materialize(
        self, repository: str, *, revision: str, destination: Path
    ) -> None:
        assert repository == "acme/repo"
        assert revision == "bad-sha"
        destination.mkdir(parents=True)
        (destination / "app.py").write_text("BROKEN = True\n", encoding="utf-8")

    async def publish_prepared_change(
        self, spec: PreparedChangeSpec
    ) -> ChangeRequestResult:
        self.published = spec
        return ChangeRequestResult(
            platform=self.platform,
            external_id="42",
            url="https://github.test/acme/repo/pull/42",
            branch_name=spec.branch_name,
        )


class FakeSandbox:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    async def run_profile(self, profile: str, workspace: Path):
        assert profile == "python"
        assert (workspace / "app.py").read_text(encoding="utf-8") == "BROKEN = False\n"
        return [
            CheckResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=self.exit_code,
                output="passed" if self.exit_code == 0 else "failed",
            )
        ]


class FakeReviewer:
    def __init__(self, *, approved: bool = True) -> None:
        self.approved = approved

    async def review(self, incident, request, changes, checks):
        del incident, request, changes, checks
        return RemediationReview(
            approved=self.approved,
            summary="Patch directly fixes the verified failure" if self.approved else "Unrelated",
        )


def incident() -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.GITHUB_ACTIONS,
        kind=IncidentKind.CI_FAILURE,
        external_id="123",
        service="acme/repo",
        title="Tests failed",
        severity="high",
        started_at=datetime.now(UTC),
        correlation_id="github:acme/repo:123",
    )


def proposal(patch: str = PATCH) -> ActionProposal:
    return ActionProposal(
        tool_name="prepare_draft_change",
        description="Prepare a tested fix",
        arguments={
            "repository": "acme/repo",
            "source_revision": "bad-sha",
            "target_branch": "main",
            "branch_name": "incident-fix/123",
            "title": "Fix failing tests",
            "description": "Fixes the verified regression.",
            "unified_diff": patch,
            "check_profile": "python",
        },
        risk=RiskLevel.LOW,
        idempotency_key="incident-123:remediation",
        rollback_plan="Close the draft PR",
        expected_outcome="CI passes on the draft branch",
    )


@pytest.mark.asyncio
async def test_pipeline_prepares_then_publishes_approved_report(tmp_path: Path) -> None:
    provider = FakeSourceControl()
    event = incident()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: provider},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )

    staged = await pipeline.stage(event, proposal())
    assert "unified_diff" not in staged.arguments
    report = await pipeline.prepare(event, staged)

    assert report.changes[0].path == "app.py"
    assert report.changes[0].operation == "update"
    assert len(report.changes[0].content_sha256) == 64
    assert report.review.approved is True

    result = await pipeline.publish(event, staged, report)

    assert result.external_reference == "https://github.test/acme/repo/pull/42"
    assert provider.published is not None
    assert "Automated safety report" in provider.published.description


@pytest.mark.asyncio
async def test_pipeline_normalizes_llm_hunk_counts_before_git_apply(
    tmp_path: Path,
) -> None:
    malformed = PATCH.replace("@@ -1 +1 @@", "@@ -1,9 +1,7 @@")
    event = incident()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: FakeSourceControl()},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )

    staged = await pipeline.stage(event, proposal(malformed))
    report = await pipeline.prepare(event, staged)

    assert report.changes[0].path == "app.py"
    assert report.checks[0].exit_code == 0


@pytest.mark.asyncio
async def test_patch_matching_tolerates_llm_spacing_in_old_line(tmp_path: Path) -> None:
    source = tmp_path / "retry_policy.py"
    source.write_text(
        "if attempt < 1:\n"
        "    raise ValueError(\"attempt must be at least 1\")\n"
        "return min(base * (2**attempt), maximum)\n",
        encoding="utf-8",
    )
    patch = """--- a/retry_policy.py
+++ b/retry_policy.py
@@ -1 +1 @@
-return min(base * (2 ** attempt), maximum)
+return min(base * (2 ** (attempt - 1)), maximum)
"""

    await _apply_patch(tmp_path, patch)

    assert source.read_text(encoding="utf-8") == (
        "if attempt < 1:\n"
        "    raise ValueError(\"attempt must be at least 1\")\n"
        "return min(base * (2 ** (attempt - 1)), maximum)\n"
    )


@pytest.mark.asyncio
async def test_pipeline_blocks_workspace_tampering_after_review(tmp_path: Path) -> None:
    event = incident()
    provider = FakeSourceControl()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: provider},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )
    staged = await pipeline.stage(event, proposal())
    report = await pipeline.prepare(event, staged)
    (tmp_path / str(event.incident_id) / "app.py").write_text(
        "MALICIOUS = True\n", encoding="utf-8"
    )

    with pytest.raises(RemediationBlockedError, match="changed after review"):
        await pipeline.publish(event, staged, report)

    assert provider.published is None


@pytest.mark.asyncio
async def test_pipeline_rejects_protected_path_before_materializing(tmp_path: Path) -> None:
    protected_patch = """--- a/.env
+++ b/.env
@@ -1 +1 @@
-TOKEN=old
+TOKEN=new
"""
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: FakeSourceControl()},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )

    with pytest.raises(RemediationBlockedError, match="protected path"):
        await pipeline.stage(incident(), proposal(protected_patch))


@pytest.mark.asyncio
async def test_pipeline_blocks_failed_sandbox_check_and_removes_workspace(
    tmp_path: Path,
) -> None:
    event = incident()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: FakeSourceControl()},
        FakeSandbox(exit_code=1),
        FakeReviewer(),
        tmp_path,
    )

    with pytest.raises(RemediationBlockedError, match="sandbox checks failed"):
        staged = await pipeline.stage(event, proposal())
        await pipeline.prepare(event, staged)

    assert not (tmp_path / str(event.incident_id)).exists()


class FakeEvidenceProvider:
    name = "fake"
    capabilities = frozenset({"logs"})
    sources = None

    async def collect(self, incident, request):
        del incident, request
        return [EvidenceItem(kind="log", source_uri="memory://1", summary="failure")]


class RemediationEngine:
    async def generate_hypotheses(self, incident, evidence):
        del incident
        return [
            Hypothesis(
                statement="Regression is verified",
                confidence=1,
                supporting_evidence_ids=[evidence[0].evidence_id],
                verified=True,
            )
        ]

    async def reflect(self, incident, evidence, hypotheses):
        del incident, evidence, hypotheses
        return ReflectionDecision(
            outcome=ReflectionOutcome.READY_FOR_ACTION,
            critique="Direct evidence confirms the regression",
        )

    async def propose_action(self, incident, evidence, hypotheses):
        del incident, evidence, hypotheses
        return proposal()


class NoopRecovery:
    async def verify(self, incident, action_result):
        del incident, action_result
        return False, "not used"


@pytest.mark.asyncio
async def test_graph_prepares_before_hitl_and_publishes_only_after_approval(
    tmp_path: Path,
) -> None:
    provider = FakeSourceControl()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: provider},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FakeEvidenceProvider(),),
            engine=RemediationEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=NoopRecovery(),
            remediation_pipeline=pipeline,
        )
    )
    config = {"configurable": {"thread_id": "remediation-graph"}}

    paused = await graph.ainvoke(initial_state(incident()), config=config)

    assert paused["status"] == "remediation_prepared"
    assert paused["remediation_report"]["checks"][0]["exit_code"] == 0
    assert "unified_diff" not in paused["proposed_action"]["arguments"]
    assert paused["__interrupt__"]
    assert provider.published is None

    completed = await graph.ainvoke(Command(resume={"approved": True}), config=config)

    assert completed["status"] == "draft_change_created"
    assert completed["action_result"]["external_reference"].endswith("/pull/42")
    assert provider.published is not None


@pytest.mark.asyncio
async def test_graph_rejection_discards_prepared_workspace(tmp_path: Path) -> None:
    event = incident()
    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: FakeSourceControl()},
        FakeSandbox(),
        FakeReviewer(),
        tmp_path,
    )
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FakeEvidenceProvider(),),
            engine=RemediationEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=NoopRecovery(),
            remediation_pipeline=pipeline,
        )
    )
    config = {"configurable": {"thread_id": "remediation-rejected"}}
    await graph.ainvoke(initial_state(event), config=config)

    rejected = await graph.ainvoke(Command(resume={"approved": False}), config=config)

    assert rejected["status"] == "action_rejected"
    assert not (tmp_path / str(event.incident_id)).exists()
    assert not (tmp_path / f"{event.incident_id}.patch").exists()
