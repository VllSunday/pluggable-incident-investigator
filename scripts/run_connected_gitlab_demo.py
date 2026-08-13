from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

import httpx
from langgraph.types import Command
from openai import AsyncOpenAI

from incident_investigator.adapters.evidence import GitLabCIEvidenceProvider
from incident_investigator.adapters.remediation import DockerSandboxRunner
from incident_investigator.adapters.scm import GitLabSourceControlProvider
from incident_investigator.core.graph import GraphServices, build_investigation_graph, initial_state
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.remediation import RemediationPipeline
from incident_investigator.core.runtime import SafeActionRunner
from incident_investigator.demo import NoopRecoveryVerifier
from incident_investigator.domain import IncidentEvent, IncidentKind, IncidentSource
from incident_investigator.engines import OpenAIInvestigationEngine, OpenAIRemediationReviewer
from incident_investigator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Incident Investigator against a real GitLab CI failure."
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="After sandbox validation, publish the branch and real draft MR.",
    )
    return parser.parse_args()


def build_incident(args: argparse.Namespace) -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.GITLAB_CI,
        kind=IncidentKind.CI_FAILURE,
        external_id=args.pipeline_id,
        service=args.repository,
        title="GitLab CI failed: retry policy regression",
        severity="high",
        started_at=datetime.now(UTC),
        correlation_id=f"gitlab:{args.repository}:{args.pipeline_id}",
        metadata={
            "sha": args.sha,
            "ref": args.target_branch,
            "target_branch": args.target_branch,
            "allowed_actions": ["prepare_draft_change"],
            "remediation_check_profiles": ["python"],
        },
    )


def print_stopped(state: dict) -> None:
    print(f"Investigation stopped with status: {state.get('status')}")
    for hypothesis in state.get("hypotheses", []):
        print(
            f"- hypothesis ({hypothesis['confidence']:.2f}, "
            f"verified={hypothesis['verified']}): {hypothesis['statement']}"
        )
    reflection = state.get("reflection")
    if reflection:
        print(f"- reflection: {reflection['outcome']}: {reflection['critique']}")
    for error in state.get("errors", []):
        print(f"- {error}")


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.gitlab_api_token is None:
        raise RuntimeError("Fill INVESTIGATOR_GITLAB_API_TOKEN in the ignored .env file.")
    headers = {"PRIVATE-TOKEN": settings.gitlab_api_token.get_secret_value()}
    incident = build_incident(args)
    async with httpx.AsyncClient(
        base_url=settings.gitlab_api_url,
        headers=headers,
        follow_redirects=True,
        timeout=30,
    ) as gitlab_client:
        evidence_provider = GitLabCIEvidenceProvider(gitlab_client)
        if args.evidence_only:
            evidence = await evidence_provider.collect(
                incident, "collect initial diagnostic evidence"
            )
            print(f"Collected {len(evidence)} real GitLab evidence items")
            for item in evidence:
                print(f"- {item.kind}: {item.source_uri}")
                print(f"  {item.summary[:240].replace(chr(10), ' ')}")
            return 0

        if settings.openai_api_key is None:
            raise RuntimeError("Fill INVESTIGATOR_OPENAI_API_KEY in the ignored .env file.")
        openai_client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=60,
            max_retries=2,
        )
        pipeline = RemediationPipeline(
            {
                IncidentSource.GITLAB_CI.value: GitLabSourceControlProvider(
                    gitlab_client
                )
            },
            DockerSandboxRunner(
                {
                    "python": [
                        ["python", "-m", "pytest", "-q"],
                        ["ruff", "check", "."],
                    ]
                },
                image=settings.remediation_sandbox_image,
            ),
            OpenAIRemediationReviewer(openai_client, model=settings.openai_model),
            settings.remediation_workspace_path,
        )
        graph = build_investigation_graph(
            GraphServices(
                evidence_providers=(evidence_provider,),
                engine=OpenAIInvestigationEngine(
                    openai_client, model=settings.openai_model
                ),
                policy=ActionPolicy(),
                action_runner=SafeActionRunner({}),
                recovery_verifier=NoopRecoveryVerifier(),
                remediation_pipeline=pipeline,
                max_elapsed_seconds=300,
            )
        )
        config = {"configurable": {"thread_id": f"connected-{incident.incident_id}"}}
        paused = await graph.ainvoke(
            initial_state(incident, max_iterations=2), config=config
        )
        if not paused.get("__interrupt__"):
            print_stopped(paused)
            return 2

        report = paused["remediation_report"]
        print("Investigation prepared a safe GitLab remediation:")
        print(f"- hypothesis: {paused['hypotheses'][0]['statement']}")
        print(f"- critic: {report['review']['summary']}")
        print(f"- changed files: {', '.join(item['path'] for item in report['changes'])}")
        for check in report["checks"]:
            print(f"- check exit {check['exit_code']}: {' '.join(check['command'])}")
        print(f"- patch sha256: {report['patch_sha256']}")
        if not args.approve:
            print("No GitLab branch or MR was created. Re-run with --approve to publish.")
            await pipeline.discard(incident)
            return 0

        completed = await graph.ainvoke(
            Command(resume={"approved": True}), config=config
        )
        print(f"Draft MR created: {completed['action_result']['external_reference']}")
        return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
