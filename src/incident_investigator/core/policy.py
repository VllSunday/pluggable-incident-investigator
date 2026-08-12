from __future__ import annotations

from dataclasses import dataclass, field

from incident_investigator.domain import ActionProposal, ApprovalStatus, RiskLevel


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    approval_status: ApprovalStatus
    reason: str


@dataclass(frozen=True)
class ActionPolicy:
    forbidden_tools: frozenset[str] = field(default_factory=frozenset)
    always_require_approval_tools: frozenset[str] = field(
        default_factory=lambda: frozenset({"prepare_draft_change"})
    )
    approval_required_for: frozenset[RiskLevel] = field(
        default_factory=lambda: frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})
    )

    def evaluate(self, proposal: ActionProposal) -> PolicyDecision:
        if proposal.tool_name in self.forbidden_tools:
            return PolicyDecision(
                allowed=False,
                approval_status=ApprovalStatus.REJECTED,
                reason=f"Tool '{proposal.tool_name}' is forbidden by policy",
            )

        if (
            proposal.tool_name in self.always_require_approval_tools
            or proposal.risk in self.approval_required_for
        ):
            return PolicyDecision(
                allowed=True,
                approval_status=ApprovalStatus.PENDING,
                reason=f"Risk level '{proposal.risk}' requires human approval",
            )

        return PolicyDecision(
            allowed=True,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            reason="Action is allowed without approval",
        )
