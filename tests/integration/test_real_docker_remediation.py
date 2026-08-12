from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.types import Command

from incident_investigator.adapters.remediation import DockerSandboxRunner
from incident_investigator.core.graph import (
    GraphServices,
    build_investigation_graph,
    initial_state,
)
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.remediation import (
    DeterministicRemediationReviewer,
    RemediationPipeline,
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

pytestmark = pytest.mark.docker

IMAGE = "incident-investigator-remediation-demo:local"
PATCH = """--- a/src/retry_policy.py
+++ b/src/retry_policy.py
@@ -1,6 +1,6 @@
 def retry_delay(attempt: int, *, base: int = 1, maximum: int = 30) -> int:
     \"\"\"Return an exponential retry delay capped at ``maximum`` seconds.\"\"\"
     if attempt < 1:
         raise ValueError(\"attempt must be at least 1\")
-    return min(base * (2**attempt), maximum)
+    return min(base * (2 ** (attempt - 1)), maximum)
 
"""


class FixtureSourceControl:
    platform = IncidentSource.GITHUB_ACTIONS

    def __init__(self, fixture: Path) -> None:
        self.fixture = fixture
        self.published: PreparedChangeSpec | None = None

    async def materialize(
        self, repository: str, *, revision: str, destination: Path
    ) -> None:
        assert repository == "demo/retry-service"
        assert revision == "broken-sha"
        shutil.copytree(self.fixture, destination)

    async def publish_prepared_change(
        self, spec: PreparedChangeSpec
    ) -> ChangeRequestResult:
        self.published = spec
        return ChangeRequestResult(
            platform=self.platform,
            external_id="demo-1",
            url="https://github.example/demo/retry-service/pull/demo-1",
            branch_name=spec.branch_name,
        )


class FixtureEvidence:
    name = "fixture_ci"
    capabilities = frozenset({"ci_logs", "commit_diff"})
    sources = frozenset({IncidentSource.GITHUB_ACTIONS})

    async def collect(self, incident, request):
        del incident, request
        return [
            EvidenceItem(
                kind="ci_job_log",
                source_uri="fixture://pytest",
                summary="attempt=1 expected delay 1 but received 2",
            )
        ]


class FixtureEngine:
    async def generate_hypotheses(self, incident, evidence):
        del incident
        return [
            Hypothesis(
                statement="The exponent is off by one",
                confidence=0.99,
                supporting_evidence_ids=[evidence[0].evidence_id],
                verified=True,
            )
        ]

    async def reflect(self, incident, evidence, hypotheses):
        del incident, evidence, hypotheses
        return ReflectionDecision(
            outcome=ReflectionOutcome.READY_FOR_ACTION,
            critique="The failing boundary example directly confirms an off-by-one error",
        )

    async def propose_action(self, incident, evidence, hypotheses):
        del evidence, hypotheses
        return ActionProposal(
            tool_name="prepare_draft_change",
            description="Correct retry exponent and validate the full fixture suite",
            arguments={
                "repository": incident.service,
                "source_revision": "broken-sha",
                "target_branch": "main",
                "branch_name": f"incident-fix/{incident.external_id}",
                "title": "Fix retry delay off-by-one error",
                "description": "Uses attempt one as the exponential base case.",
                "unified_diff": PATCH,
                "check_profile": "python",
            },
            risk=RiskLevel.LOW,
            idempotency_key=f"{incident.incident_id}:draft-change",
            rollback_plan="Close the draft PR",
            expected_outcome="All retry policy tests and lint checks pass",
        )


class UnusedRecoveryVerifier:
    async def verify(self, incident, action_result):
        del incident, action_result
        return False, "Draft changes do not claim runtime recovery"


def _docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"], capture_output=True, check=False, timeout=10
    )
    return result.returncode == 0


@pytest.mark.asyncio
async def test_real_docker_sandbox_then_hitl_then_draft_pr(
    tmp_path: Path,
) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon is not available")
    repository_root = Path(__file__).parents[2]
    fixture = repository_root / "demo" / "ci-python-app"
    provider = FixtureSourceControl(fixture)
    sandbox = DockerSandboxRunner(
        {
            "python": [
                ["python", "-m", "pytest", "-q"],
                ["ruff", "check", "."],
            ]
        },
        image=IMAGE,
    )
    baseline = tmp_path / "baseline"
    shutil.copytree(fixture, baseline)
    baseline_results = await sandbox.run_profile("python", baseline)
    assert baseline_results[0].exit_code != 0
    print("[1/4] Broken baseline reproduced in an isolated Docker sandbox")

    pipeline = RemediationPipeline(
        {IncidentSource.GITHUB_ACTIONS.value: provider},
        sandbox,
        DeterministicRemediationReviewer(),
        tmp_path / "workspaces",
    )
    graph = build_investigation_graph(
        GraphServices(
            evidence_providers=(FixtureEvidence(),),
            engine=FixtureEngine(),
            policy=ActionPolicy(),
            action_runner=SafeActionRunner({}),
            recovery_verifier=UnusedRecoveryVerifier(),
            remediation_pipeline=pipeline,
            max_elapsed_seconds=300,
        )
    )
    incident = IncidentEvent(
        source=IncidentSource.GITHUB_ACTIONS,
        kind=IncidentKind.CI_FAILURE,
        external_id="retry-101",
        service="demo/retry-service",
        title="Retry policy tests failed",
        severity="high",
        started_at=datetime.now(UTC),
        correlation_id="github:demo/retry-service:retry-101",
        metadata={
            "head_sha": "broken-sha",
            "target_branch": "main",
            "allowed_actions": ["prepare_draft_change"],
            "remediation_check_profiles": ["python"],
        },
    )
    config = {"configurable": {"thread_id": "real-docker-remediation"}}

    paused = await graph.ainvoke(initial_state(incident), config=config)

    assert paused["status"] == "remediation_prepared", paused.get("errors")
    assert [item["exit_code"] for item in paused["remediation_report"]["checks"]] == [0, 0]
    assert provider.published is None
    print("[2/4] Patch applied; pytest and Ruff passed with network disabled")
    print("[3/4] LangGraph paused for human approval before any branch existed")

    completed = await graph.ainvoke(Command(resume={"approved": True}), config=config)

    assert completed["status"] == "draft_change_created"
    assert provider.published is not None
    assert provider.published.changes[0].content is not None
    assert "attempt - 1" in provider.published.changes[0].content
    print(f"[4/4] Approval created draft PR: {completed['action_result']['external_reference']}")
