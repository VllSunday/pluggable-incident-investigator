from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.ports import (
    EvidenceProvider,
    InvestigationEngine,
    RecoveryVerifier,
)
from incident_investigator.core.remediation import (
    RemediationBlockedError,
    RemediationPipeline,
    RemediationReport,
)
from incident_investigator.core.runtime import ExecutionBudget, SafeActionRunner
from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    ApprovalStatus,
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    ReflectionDecision,
    ReflectionOutcome,
)


class InvestigationState(TypedDict, total=False):
    incident: dict[str, Any]
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    evidence_requests: list[str]
    reflection: dict[str, Any] | None
    proposed_action: dict[str, Any] | None
    policy_decision: dict[str, Any] | None
    approval_status: str
    action_result: dict[str, Any] | None
    recovery_verified: bool | None
    recovery_summary: str | None
    remediation_report: dict[str, Any] | None
    iteration: int
    max_iterations: int
    tool_calls_used: int
    started_at: str
    errors: list[str]
    status: str


@dataclass(frozen=True)
class GraphServices:
    evidence_providers: tuple[EvidenceProvider, ...]
    engine: InvestigationEngine
    policy: ActionPolicy
    action_runner: SafeActionRunner
    recovery_verifier: RecoveryVerifier
    remediation_pipeline: RemediationPipeline | None = None
    max_tool_calls: int = 12
    max_elapsed_seconds: float = 120.0


def _incident(state: InvestigationState) -> IncidentEvent:
    return IncidentEvent.model_validate(state["incident"])


def _evidence(state: InvestigationState) -> list[EvidenceItem]:
    return [EvidenceItem.model_validate(item) for item in state.get("evidence", [])]


def _hypotheses(state: InvestigationState) -> list[Hypothesis]:
    return [Hypothesis.model_validate(item) for item in state.get("hypotheses", [])]


def build_investigation_graph(
    services: GraphServices,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    async def collect_evidence(state: InvestigationState) -> dict[str, Any]:
        incident = _incident(state)
        requests = state.get("evidence_requests") or ["collect initial diagnostic evidence"]
        existing = _evidence(state)
        errors = list(state.get("errors", []))
        collected: list[EvidenceItem] = []

        applicable_providers = [
            provider
            for provider in services.evidence_providers
            if getattr(provider, "sources", None) is None
            or incident.source in provider.sources
        ]
        call_specs = [
            (provider, request)
            for request in requests
            for provider in applicable_providers
        ]
        used = state.get("tool_calls_used", 0)
        started_at = datetime.fromisoformat(state["started_at"])
        elapsed = (datetime.now(UTC) - started_at).total_seconds()
        remaining_calls = services.max_tool_calls - used
        if remaining_calls <= 0:
            return {
                "errors": [*errors, "budget:tool_call_budget_exhausted"],
                "iteration": state.get("max_iterations", 3),
                "status": "evidence_budget_exhausted",
            }
        if elapsed >= services.max_elapsed_seconds:
            return {
                "errors": [*errors, "budget:elapsed_time_budget_exhausted"],
                "iteration": state.get("max_iterations", 3),
                "status": "evidence_budget_exhausted",
            }
        if len(call_specs) > remaining_calls:
            call_specs = call_specs[:remaining_calls]
            errors.append("budget:tool_call_budget_truncated")
        calls = [
            provider.collect(incident, request)
            for provider, request in call_specs
        ]
        results = await asyncio.gather(*calls, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                errors.append(f"evidence_collection:{type(result).__name__}:{result}")
            else:
                collected.extend(result)

        unique = {str(item.evidence_id): item for item in [*existing, *collected]}
        return {
            "evidence": [item.model_dump(mode="json") for item in unique.values()],
            "errors": errors,
            "evidence_requests": [],
            "iteration": state.get("iteration", 0) + 1,
            "tool_calls_used": used + len(call_specs),
            "status": "evidence_collected",
        }

    async def generate_hypotheses(state: InvestigationState) -> dict[str, Any]:
        hypotheses = await services.engine.generate_hypotheses(
            _incident(state), _evidence(state)
        )
        return {
            "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
            "status": "hypotheses_generated",
        }

    def route_after_evidence(
        state: InvestigationState,
    ) -> Literal["generate_hypotheses", "finish"]:
        if state.get("status") == "evidence_budget_exhausted":
            return "finish"
        return "generate_hypotheses"

    async def reflect(state: InvestigationState) -> dict[str, Any]:
        decision = await services.engine.reflect(
            _incident(state), _evidence(state), _hypotheses(state)
        )
        if (
            decision.outcome is ReflectionOutcome.GATHER_MORE
            and state.get("iteration", 0) >= state.get("max_iterations", 3)
        ):
            decision = ReflectionDecision(
                outcome=ReflectionOutcome.ESCALATE,
                critique="Investigation iteration budget exhausted; human escalation required",
            )
        return {
            "reflection": decision.model_dump(mode="json"),
            "evidence_requests": list(decision.additional_evidence_requests),
            "status": "reflection_complete",
        }

    def route_after_reflection(
        state: InvestigationState,
    ) -> Literal["collect_evidence", "propose_action", "finish"]:
        decision = ReflectionDecision.model_validate(state["reflection"])
        if decision.outcome is ReflectionOutcome.GATHER_MORE:
            return "collect_evidence"
        if decision.outcome is ReflectionOutcome.READY_FOR_ACTION:
            return "propose_action"
        return "finish"

    async def propose_action(state: InvestigationState) -> dict[str, Any]:
        proposal = await services.engine.propose_action(
            _incident(state), _evidence(state), _hypotheses(state)
        )
        if proposal is None:
            return {"proposed_action": None, "status": "no_safe_action"}
        decision = services.policy.evaluate(proposal)
        if (
            decision.allowed
            and proposal.tool_name == RemediationPipeline.tool_name
            and services.remediation_pipeline is not None
        ):
            proposal = await services.remediation_pipeline.stage(
                _incident(state), proposal
            )
        return {
            "proposed_action": proposal.model_dump(mode="json"),
            "policy_decision": {
                "allowed": decision.allowed,
                "approval_status": decision.approval_status.value,
                "reason": decision.reason,
            },
            "approval_status": decision.approval_status.value,
            "status": "action_proposed",
        }

    def route_after_policy(
        state: InvestigationState,
    ) -> Literal["prepare_remediation", "approval", "execute_action", "finish"]:
        if state.get("proposed_action") is None:
            return "finish"
        decision = state.get("policy_decision") or {}
        if not decision.get("allowed", False):
            return "finish"
        if (
            state["proposed_action"]["tool_name"] == RemediationPipeline.tool_name
        ):
            return "prepare_remediation"
        status = ApprovalStatus(state["approval_status"])
        if status is ApprovalStatus.PENDING:
            return "approval"
        return "execute_action"

    async def prepare_remediation(state: InvestigationState) -> dict[str, Any]:
        if services.remediation_pipeline is None:
            return {
                "status": "remediation_blocked",
                "errors": [*state.get("errors", []), "remediation:not_configured"],
            }
        try:
            proposal = ActionProposal.model_validate(state["proposed_action"])
            report = await services.remediation_pipeline.prepare(
                _incident(state), proposal
            )
        except RemediationBlockedError as error:
            return {
                "status": "remediation_blocked",
                "errors": [*state.get("errors", []), f"remediation:{error}"],
            }
        return {
            "proposed_action": proposal.model_copy(
                update={
                    "arguments": {
                        **report.request.model_dump(mode="json"),
                        "patch_sha256": report.patch_sha256,
                    }
                }
            ).model_dump(mode="json"),
            "remediation_report": report.model_dump(mode="json"),
            "status": "remediation_prepared",
        }

    def route_after_remediation(
        state: InvestigationState,
    ) -> Literal["approval", "finish"]:
        return "approval" if state.get("remediation_report") else "finish"

    async def approval(
        state: InvestigationState,
    ) -> Command[Literal["publish_remediation", "execute_action", "finish"]]:
        decision = interrupt(
            {
                "type": "action_approval",
                "incident_id": state["incident"]["incident_id"],
                "proposal": state["proposed_action"],
                "policy": state["policy_decision"],
                "remediation_report": state.get("remediation_report"),
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        if (
            not approved
            and state.get("remediation_report") is not None
            and services.remediation_pipeline is not None
        ):
            await services.remediation_pipeline.discard(_incident(state))
        is_remediation = state.get("remediation_report") is not None
        return Command(
            update={
                "approval_status": (
                    ApprovalStatus.APPROVED.value
                    if approved
                    else ApprovalStatus.REJECTED.value
                ),
                "status": "action_approved" if approved else "action_rejected",
            },
            goto=(
                "publish_remediation"
                if approved and is_remediation
                else "execute_action"
                if approved
                else "finish"
            ),
        )

    async def publish_remediation(state: InvestigationState) -> dict[str, Any]:
        if services.remediation_pipeline is None:
            raise RemediationBlockedError("Remediation pipeline is not configured")
        result = await services.remediation_pipeline.publish(
            _incident(state),
            ActionProposal.model_validate(state["proposed_action"]),
            RemediationReport.model_validate(state["remediation_report"]),
        )
        return {
            "action_result": result.model_dump(mode="json"),
            "status": "draft_change_created",
        }

    async def execute_action(state: InvestigationState) -> dict[str, Any]:
        proposal = ActionProposal.model_validate(state["proposed_action"])
        remaining_calls = services.max_tool_calls - state.get("tool_calls_used", 0)
        action_budget = ExecutionBudget(
            max_tool_calls=max(remaining_calls, 0),
            max_elapsed_seconds=services.max_elapsed_seconds,
        )
        outcome = await services.action_runner.execute(
            proposal,
            ApprovalStatus(state["approval_status"]),
            action_budget,
        )
        return {
            "action_result": outcome.value.model_dump(mode="json"),
            "tool_calls_used": (
                state.get("tool_calls_used", 0) + action_budget.tool_calls_used
            ),
            "status": "action_executed",
        }

    async def verify_recovery(state: InvestigationState) -> dict[str, Any]:
        result = ActionResult.model_validate(state["action_result"])
        verified, summary = await services.recovery_verifier.verify(_incident(state), result)
        return {
            "recovery_verified": verified,
            "recovery_summary": summary,
            "status": "recovered" if verified else "recovery_failed",
        }

    def finish(state: InvestigationState) -> dict[str, Any]:
        status = state.get("status", "completed")
        if status == "reflection_complete":
            status = "escalated"
        return {"status": status}

    builder = StateGraph(InvestigationState)
    builder.add_node("collect_evidence", collect_evidence)
    builder.add_node("generate_hypotheses", generate_hypotheses)
    builder.add_node("reflect", reflect)
    builder.add_node("propose_action", propose_action)
    builder.add_node("prepare_remediation", prepare_remediation)
    builder.add_node("approval", approval)
    builder.add_node("publish_remediation", publish_remediation)
    builder.add_node("execute_action", execute_action)
    builder.add_node("verify_recovery", verify_recovery)
    builder.add_node("finish", finish)

    builder.add_edge(START, "collect_evidence")
    builder.add_conditional_edges("collect_evidence", route_after_evidence)
    builder.add_edge("generate_hypotheses", "reflect")
    builder.add_conditional_edges("reflect", route_after_reflection)
    builder.add_conditional_edges("propose_action", route_after_policy)
    builder.add_conditional_edges("prepare_remediation", route_after_remediation)
    builder.add_edge("publish_remediation", END)
    builder.add_edge("execute_action", "verify_recovery")
    builder.add_edge("verify_recovery", END)
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def initial_state(incident: IncidentEvent, *, max_iterations: int = 3) -> InvestigationState:
    return {
        "incident": incident.model_dump(mode="json"),
        "evidence": [],
        "hypotheses": [],
        "evidence_requests": [],
        "reflection": None,
        "proposed_action": None,
        "policy_decision": None,
        "approval_status": ApprovalStatus.NOT_REQUIRED.value,
        "action_result": None,
        "recovery_verified": None,
        "recovery_summary": None,
        "remediation_report": None,
        "iteration": 0,
        "max_iterations": max_iterations,
        "tool_calls_used": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "errors": [],
        "status": "received",
    }
