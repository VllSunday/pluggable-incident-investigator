from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from incident_investigator.domain import IncidentEvent


class IncidentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    REJECTED = "rejected"
    FAILED = "failed"


class IncidentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: UUID
    correlation_id: str
    event: IncidentEvent
    status: IncidentStatus
    graph_status: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

