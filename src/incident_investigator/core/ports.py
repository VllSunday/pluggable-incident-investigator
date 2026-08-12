from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from incident_investigator.domain import (
    ActionProposal,
    ActionResult,
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    IncidentSource,
    ReflectionDecision,
)


class EventAdapter(Protocol):
    name: str

    def verify(self, body: bytes, headers: Mapping[str, str]) -> None: ...

    def normalize(self, payload: Mapping[str, Any]) -> list[IncidentEvent]: ...


class EvidenceProvider(Protocol):
    name: str
    capabilities: frozenset[str]
    sources: frozenset[IncidentSource] | None

    async def collect(
        self, incident: IncidentEvent, request: str
    ) -> Sequence[EvidenceItem]: ...


class InvestigationEngine(Protocol):
    async def generate_hypotheses(
        self, incident: IncidentEvent, evidence: Sequence[EvidenceItem]
    ) -> Sequence[Hypothesis]: ...

    async def reflect(
        self,
        incident: IncidentEvent,
        evidence: Sequence[EvidenceItem],
        hypotheses: Sequence[Hypothesis],
    ) -> ReflectionDecision: ...

    async def propose_action(
        self,
        incident: IncidentEvent,
        evidence: Sequence[EvidenceItem],
        hypotheses: Sequence[Hypothesis],
    ) -> ActionProposal | None: ...


class ActionExecutor(Protocol):
    name: str

    async def execute(self, proposal: ActionProposal) -> ActionResult: ...


class NotificationSink(Protocol):
    name: str

    async def publish(self, event_name: str, payload: Mapping[str, Any]) -> None: ...


class RecoveryVerifier(Protocol):
    async def verify(
        self, incident: IncidentEvent, action_result: ActionResult
    ) -> tuple[bool, str]: ...
