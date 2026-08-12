from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

from incident_investigator.core.ports import ActionExecutor
from incident_investigator.domain import ActionProposal, ActionResult, ApprovalStatus


class BudgetExceededError(RuntimeError):
    pass


class ApprovalRequiredError(RuntimeError):
    pass


class ToolExecutionError(RuntimeError):
    pass


@dataclass
class ExecutionBudget:
    max_tool_calls: int = 12
    max_elapsed_seconds: float = 120.0
    _tool_calls: int = 0
    _started_at: float = 0.0

    def start(self) -> None:
        if self._started_at == 0:
            self._started_at = monotonic()

    def consume_tool_call(self) -> None:
        self.start()
        if self._tool_calls >= self.max_tool_calls:
            raise BudgetExceededError("Tool-call budget exhausted")
        if monotonic() - self._started_at >= self.max_elapsed_seconds:
            raise BudgetExceededError("Execution time budget exhausted")
        self._tool_calls += 1

    @property
    def tool_calls_used(self) -> int:
        return self._tool_calls


@dataclass(frozen=True)
class ToolCallOutcome[T]:
    value: T
    attempts: int


class SafeActionRunner:
    def __init__(
        self,
        executors: dict[str, ActionExecutor],
        *,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._executors = executors
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    async def execute(
        self,
        proposal: ActionProposal,
        approval_status: ApprovalStatus,
        budget: ExecutionBudget,
    ) -> ToolCallOutcome[ActionResult]:
        if approval_status is ApprovalStatus.PENDING:
            raise ApprovalRequiredError("Action is waiting for human approval")
        if approval_status is ApprovalStatus.REJECTED:
            raise ApprovalRequiredError("Action was rejected")

        executor = self._executors.get(proposal.tool_name)
        if executor is None:
            raise ToolExecutionError(f"No executor registered for '{proposal.tool_name}'")

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            budget.consume_tool_call()
            try:
                result = await asyncio.wait_for(
                    executor.execute(proposal), timeout=self._timeout_seconds
                )
                return ToolCallOutcome(value=result, attempts=attempt)
            except (TimeoutError, ConnectionError) as error:
                last_error = error

        raise ToolExecutionError(
            f"Tool '{proposal.tool_name}' failed after {self._max_attempts} attempts"
        ) from last_error
