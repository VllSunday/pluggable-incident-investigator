from incident_investigator.core.policy import ActionPolicy
from incident_investigator.domain import ActionProposal, ApprovalStatus, RiskLevel


def proposal(tool_name: str, risk: RiskLevel) -> ActionProposal:
    return ActionProposal(
        tool_name=tool_name,
        description="Test action",
        arguments={},
        risk=risk,
        idempotency_key="incident-1:action-1",
        expected_outcome="Test outcome",
    )


def test_read_only_action_does_not_require_approval() -> None:
    decision = ActionPolicy().evaluate(proposal("query_logs", RiskLevel.READ_ONLY))

    assert decision.allowed
    assert decision.approval_status is ApprovalStatus.NOT_REQUIRED


def test_high_risk_action_requires_approval() -> None:
    decision = ActionPolicy().evaluate(proposal("restart_service", RiskLevel.HIGH))

    assert decision.allowed
    assert decision.approval_status is ApprovalStatus.PENDING


def test_forbidden_tool_is_rejected_regardless_of_risk() -> None:
    policy = ActionPolicy(forbidden_tools=frozenset({"delete_database"}))

    decision = policy.evaluate(proposal("delete_database", RiskLevel.LOW))

    assert not decision.allowed
    assert decision.approval_status is ApprovalStatus.REJECTED

