from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class IncidentSource(StrEnum):
    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    ALERTMANAGER = "alertmanager"


class IncidentKind(StrEnum):
    CI_FAILURE = "ci_failure"
    RUNTIME_ALERT = "runtime_alert"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReflectionOutcome(StrEnum):
    GATHER_MORE = "gather_more"
    READY_FOR_ACTION = "ready_for_action"
    ESCALATE = "escalate"


class IncidentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: UUID = Field(default_factory=uuid4)
    source: IncidentSource
    kind: IncidentKind
    external_id: str = Field(min_length=1)
    service: str = Field(min_length=1)
    title: str = Field(min_length=1)
    severity: str = "unknown"
    status: str = "firing"
    started_at: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID = Field(default_factory=uuid4)
    kind: str
    source_uri: str
    summary: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: UUID = Field(default_factory=uuid4)
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    contradicting_evidence_ids: list[UUID] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    verified: bool = False


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ReflectionOutcome
    critique: str = Field(min_length=1)
    additional_evidence_requests: tuple[str, ...] = ()


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: UUID = Field(default_factory=uuid4)
    tool_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel
    idempotency_key: str = Field(min_length=1)
    rollback_plan: str | None = None
    expected_outcome: str = Field(min_length=1)


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: UUID
    success: bool
    summary: str
    external_reference: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)
