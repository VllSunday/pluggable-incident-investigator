from __future__ import annotations

from uuid import uuid4

import pytest

from incident_investigator.core.runtime import (
    ApprovalRequiredError,
    BudgetExceededError,
    ExecutionBudget,
    SafeActionRunner,
    ToolExecutionError,
)
from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    ApprovalStatus,
    RiskLevel,
)


class SuccessfulExecutor:
    name = "restart_service"

    async def execute(self, proposal: ActionProposal) -> ActionResult:
        return ActionResult(action_id=proposal.action_id, success=True, summary="Restarted")


class FailingExecutor:
    name = "restart_service"

    async def execute(self, proposal: ActionProposal) -> ActionResult:
        del proposal
        raise ConnectionError("temporary outage")


def action() -> ActionProposal:
    return ActionProposal(
        action_id=uuid4(),
        tool_name="restart_service",
        description="Restart demo service",
        risk=RiskLevel.HIGH,
        idempotency_key="incident-1:restart-1",
        expected_outcome="Health check passes",
    )


@pytest.mark.asyncio
async def test_runner_blocks_pending_action() -> None:
    runner = SafeActionRunner({"restart_service": SuccessfulExecutor()})

    with pytest.raises(ApprovalRequiredError):
        await runner.execute(action(), ApprovalStatus.PENDING, ExecutionBudget())


@pytest.mark.asyncio
async def test_runner_executes_approved_action() -> None:
    runner = SafeActionRunner({"restart_service": SuccessfulExecutor()})
    budget = ExecutionBudget()

    outcome = await runner.execute(action(), ApprovalStatus.APPROVED, budget)

    assert outcome.value.success
    assert outcome.attempts == 1
    assert budget.tool_calls_used == 1


@pytest.mark.asyncio
async def test_runner_retries_transient_failure() -> None:
    runner = SafeActionRunner(
        {"restart_service": FailingExecutor()}, timeout_seconds=0.1, max_attempts=2
    )
    budget = ExecutionBudget(max_tool_calls=3)

    with pytest.raises(ToolExecutionError):
        await runner.execute(action(), ApprovalStatus.APPROVED, budget)

    assert budget.tool_calls_used == 2


def test_budget_stops_extra_calls() -> None:
    budget = ExecutionBudget(max_tool_calls=1)
    budget.consume_tool_call()

    with pytest.raises(BudgetExceededError):
        budget.consume_tool_call()

