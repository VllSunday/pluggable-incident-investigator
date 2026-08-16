from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from typing import Any
from uuid import UUID

from langgraph.types import Command

from incident_investigator.application.models import IncidentRecord, IncidentStatus
from incident_investigator.application.notifications import BestEffortNotifier
from incident_investigator.application.operator_input import (
    OperatorEvidenceStore,
    OperatorEvidenceSubmission,
)
from incident_investigator.application.repository import SqliteIncidentRepository
from incident_investigator.core.graph import initial_state
from incident_investigator.domain import IncidentEvent, InformationRequest


class IncidentNotFoundError(LookupError):
    pass


class InvalidIncidentStateError(RuntimeError):
    pass


class InvestigationService:
    def __init__(
        self,
        repository: SqliteIncidentRepository,
        graph: Any,
        *,
        poll_interval_seconds: float = 0.5,
        notifier: BestEffortNotifier | None = None,
        operator_evidence_store: OperatorEvidenceStore | None = None,
    ) -> None:
        self._repository = repository
        self._graph = graph
        self._poll_interval_seconds = poll_interval_seconds
        self._notifier = notifier or BestEffortNotifier()
        self._operator_evidence_store = operator_evidence_store
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._repository.initialize()
        await self._repository.recover_interrupted_runs()
        if self._worker_task is None:
            self._stop_event.clear()
            self._worker_task = asyncio.create_task(self._worker(), name="incident-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker_task is not None:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

    async def accept(self, incident: IncidentEvent) -> None:
        record, created = await self._repository.enqueue(incident)
        if created:
            await self._notifier.publish(
                "incident.received",
                {
                    "incident": record.event.model_dump(mode="json"),
                    "status": record.status.value,
                },
            )

    async def list_incidents(self, limit: int = 100) -> Sequence[IncidentRecord]:
        return await self._repository.list(limit)

    async def get_incident(self, incident_id: UUID | str) -> IncidentRecord:
        record = await self._repository.get(incident_id)
        if record is None:
            raise IncidentNotFoundError(str(incident_id))
        return record

    async def decide_approval(
        self, incident_id: UUID | str, *, approved: bool
    ) -> IncidentRecord:
        record = await self.get_incident(incident_id)
        if record.status is not IncidentStatus.AWAITING_APPROVAL:
            raise InvalidIncidentStateError(
                f"Incident is '{record.status}', not awaiting approval"
            )
        config = self._graph_config(record)
        try:
            result = await self._graph.ainvoke(
                Command(resume={"approved": approved}), config=config
            )
            await self._save_graph_result(record.incident_id, result)
        except Exception as error:
            await self._repository.update(
                record.incident_id,
                status=IncidentStatus.FAILED,
                graph_status="approval_resume_failed",
                error=f"{type(error).__name__}: {error}",
            )
            raise
        return await self.get_incident(record.incident_id)

    async def submit_evidence(
        self,
        incident_id: UUID | str,
        submission: OperatorEvidenceSubmission,
    ) -> IncidentRecord:
        record = await self.get_incident(incident_id)
        request = self._active_information_request(record)
        if submission.request_id != request.request_id:
            raise InvalidIncidentStateError(
                "Evidence submission does not match the active information request"
            )
        if self._operator_evidence_store is None:
            raise RuntimeError("Operator evidence storage is not configured")
        evidence = await asyncio.to_thread(
            self._operator_evidence_store.save, record.incident_id, submission
        )
        return await self._resume_input(
            record,
            {"evidence": [evidence.model_dump(mode="json")]},
        )

    async def decline_information_request(
        self, incident_id: UUID | str
    ) -> IncidentRecord:
        record = await self.get_incident(incident_id)
        self._active_information_request(record)
        return await self._resume_input(record, {"unable": True})

    @staticmethod
    def _active_information_request(record: IncidentRecord) -> InformationRequest:
        if record.status is not IncidentStatus.AWAITING_INPUT:
            raise InvalidIncidentStateError(
                f"Incident is '{record.status}', not awaiting operator input"
            )
        payload = record.state.get("information_request")
        if payload is None:
            raise InvalidIncidentStateError("Incident has no active information request")
        return InformationRequest.model_validate(payload)

    async def _resume_input(
        self, record: IncidentRecord, resume_payload: dict[str, Any]
    ) -> IncidentRecord:
        try:
            result = await self._graph.ainvoke(
                Command(resume=resume_payload), config=self._graph_config(record)
            )
            await self._save_graph_result(record.incident_id, result)
        except Exception as error:
            await self._repository.update(
                record.incident_id,
                status=IncidentStatus.FAILED,
                graph_status="input_resume_failed",
                error=f"{type(error).__name__}: {error}",
            )
            raise
        return await self.get_incident(record.incident_id)

    async def process_next(self) -> bool:
        record = await self._repository.claim_next()
        if record is None:
            return False
        config = self._graph_config(record)
        try:
            result = await self._graph.ainvoke(initial_state(record.event), config=config)
            await self._save_graph_result(record.incident_id, result)
        except Exception as error:
            await self._repository.update(
                record.incident_id,
                status=IncidentStatus.FAILED,
                graph_status="execution_failed",
                error=f"{type(error).__name__}: {error}",
            )
        return True

    @staticmethod
    def _graph_config(record: IncidentRecord) -> dict[str, Any]:
        event = record.event
        return {
            "configurable": {"thread_id": str(record.incident_id)},
            "tags": [
                "incident-investigator",
                f"source:{event.source.value}",
                f"kind:{event.kind.value}",
            ],
            "metadata": {
                "incident_id": str(record.incident_id),
                "correlation_id": record.correlation_id,
                "source": event.source.value,
                "kind": event.kind.value,
                "service": event.service,
            },
        }

    async def _worker(self) -> None:
        while not self._stop_event.is_set():
            processed = await self.process_next()
            if not processed:
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._poll_interval_seconds
                    )

    async def _save_graph_result(self, incident_id: UUID, result: dict[str, Any]) -> None:
        graph_status = str(result.get("status", "unknown"))
        if result.get("__interrupt__"):
            interrupt_type = self._interrupt_type(result)
            status = (
                IncidentStatus.AWAITING_INPUT
                if interrupt_type == "evidence_request"
                else IncidentStatus.AWAITING_APPROVAL
            )
        elif graph_status in {"recovered", "draft_change_created"}:
            status = IncidentStatus.COMPLETED
        elif graph_status in {
            "escalated",
            "no_safe_action",
            "recovery_failed",
            "remediation_blocked",
            "evidence_budget_exhausted",
            "operator_escalated",
            "action_failed_escalated",
            "repeated_action_blocked",
        }:
            status = IncidentStatus.ESCALATED
        elif graph_status == "action_rejected":
            status = IncidentStatus.REJECTED
        else:
            status = IncidentStatus.COMPLETED

        serializable = {key: value for key, value in result.items() if key != "__interrupt__"}
        if result.get("__interrupt__"):
            serializable["interrupts"] = [
                item.value if hasattr(item, "value") else str(item)
                for item in result["__interrupt__"]
            ]
        await self._repository.update(
            incident_id,
            status=status,
            graph_status=graph_status,
            state=serializable,
        )
        record = await self._repository.get(incident_id)
        if record is not None:
            if status is IncidentStatus.AWAITING_INPUT:
                event_name = "input.required"
            elif status is IncidentStatus.AWAITING_APPROVAL:
                event_name = "approval.required"
            elif graph_status == "draft_change_created":
                event_name = "draft_pr.created"
            else:
                event_name = "investigation.completed"
            await self._notifier.publish(
                event_name,
                {
                    "incident": record.event.model_dump(mode="json"),
                    "status": status.value,
                    "graph_status": graph_status,
                    "action_result": result.get("action_result"),
                    "information_request": result.get("information_request"),
                },
            )

    @staticmethod
    def _interrupt_type(result: dict[str, Any]) -> str | None:
        interrupts = result.get("__interrupt__") or []
        if not interrupts:
            return None
        value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        return str(value.get("type")) if isinstance(value, dict) else None
