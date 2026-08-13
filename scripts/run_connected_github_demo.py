from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

import httpx
from langgraph.types import Command
from openai import AsyncOpenAI

from incident_investigator.adapters.evidence import GitHubCIEvidenceProvider
from incident_investigator.adapters.remediation import DockerSandboxRunner
from incident_investigator.adapters.scm import GitHubSourceControlProvider
from incident_investigator.core.graph import (
    GraphServices,
    build_investigation_graph,
    initial_state,
)
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.remediation import RemediationPipeline
from incident_investigator.core.runtime import SafeActionRunner
from incident_investigator.demo import NoopRecoveryVerifier
from incident_investigator.domain import IncidentEvent, IncidentKind, IncidentSource
from incident_investigator.engines import (
    OpenAIInvestigationEngine,
    OpenAIRemediationReviewer,
)
from incident_investigator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the connected Incident Investigator against a real GitHub CI failure."
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="After sandbox validation, publish the branch and real draft PR.",
    )
    return parser.parse_args()


def build_incident(args: argparse.Namespace) -> IncidentEvent:
    return IncidentEvent(
        source=IncidentSource.GITHUB_ACTIONS,
        kind=IncidentKind.CI_FAILURE,
        external_id=args.run_id,
        service=args.repository,
        title="GitHub Actions CI failed: retry policy regression",
        severity="high",
        started_at=datetime.now(UTC),
        correlation_id=f"github:{args.repository}:{args.run_id}",
        metadata={
            "head_sha": args.head_sha,
            "head_branch": args.target_branch,
            "target_branch": args.target_branch,
            "allowed_actions": ["prepare_draft_change"],
            "remediation_check_profiles": ["python"],
        },
    )


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.github_api_token is None:
        raise RuntimeError(
            "Set INVESTIGATOR_GITHUB_API_TOKEN or inject `gh auth token` into the process."
        )
    headers = {
        "Authorization": f"Bearer {settings.github_api_token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    incident = build_incident(args)
    async with httpx.AsyncClient(
        base_url=settings.github_api_url,
        headers=headers,
        follow_redirects=True,
        timeout=30,
    ) as github_client:
        evidence_provider = GitHubCIEvidenceProvider(github_client)
        if args.evidence_only:
            evidence = await evidence_provider.collect(
                incident, "collect initial diagnostic evidence"
            )
            print(f"Collected {len(evidence)} real evidence items")
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
        engine = OpenAIInvestigationEngine(
            openai_client, model=settings.openai_model
        )
        pipeline = RemediationPipeline(
            {
                IncidentSource.GITHUB_ACTIONS.value: GitHubSourceControlProvider(
                    github_client
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
            OpenAIRemediationReviewer(
                openai_client, model=settings.openai_model
            ),
            settings.remediation_workspace_path,
        )
        graph = build_investigation_graph(
            GraphServices(
                evidence_providers=(evidence_provider,),
                engine=engine,
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
            print(f"Investigation stopped with status: {paused.get('status')}")
            for hypothesis in paused.get("hypotheses", []):
                print(
                    f"- hypothesis ({hypothesis['confidence']:.2f}, "
                    f"verified={hypothesis['verified']}): {hypothesis['statement']}"
                )
            reflection = paused.get("reflection")
            if reflection:
                print(
                    f"- reflection: {reflection['outcome']}: "
                    f"{reflection['critique']}"
                )
            for error in paused.get("errors", []):
                print(f"- {error}")
            return 2

        report = paused["remediation_report"]
        print("Investigation prepared a safe remediation:")
        print(f"- hypothesis: {paused['hypotheses'][0]['statement']}")
        print(f"- critic: {report['review']['summary']}")
        print(f"- changed files: {', '.join(item['path'] for item in report['changes'])}")
        for check in report["checks"]:
            print(f"- check exit {check['exit_code']}: {' '.join(check['command'])}")
        print(f"- patch sha256: {report['patch_sha256']}")
        if not args.approve:
            print("No GitHub branch or PR was created. Re-run with --approve to publish.")
            await pipeline.discard(incident)
            return 0

        completed = await graph.ainvoke(
            Command(resume={"approved": True}), config=config
        )
        print(f"Draft PR created: {completed['action_result']['external_reference']}")
        return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
