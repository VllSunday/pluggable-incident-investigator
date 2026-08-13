from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    name: str
    match: dict[str, str]
    required_evidence_kinds: tuple[str, ...] = ()
    root_cause_any: tuple[str, ...] = ()
    allowed_graph_statuses: tuple[str, ...] = ()
    max_tool_calls: int | None = Field(default=None, ge=0)
    require_no_action: bool = False


@dataclass(frozen=True)
class EvaluationResult:
    case: str
    incident_id: str
    score: float
    criteria: dict[str, bool]


def record_matches(record: dict[str, Any], case: EvaluationCase) -> bool:
    event = record.get("event", {})
    return all(str(event.get(key, "")) == value for key, value in case.match.items())


def evaluate_record(record: dict[str, Any], case: EvaluationCase) -> EvaluationResult:
    state = record.get("state") or {}
    evidence = state.get("evidence") or []
    hypotheses = state.get("hypotheses") or []
    evidence_kinds = {str(item.get("kind", "")) for item in evidence}
    hypothesis_text = " ".join(
        str(item.get("statement", "")) for item in hypotheses
    ).casefold()

    criteria: dict[str, bool] = {
        "event_match": record_matches(record, case),
        "evidence_coverage": set(case.required_evidence_kinds) <= evidence_kinds,
        "root_cause_match": (
            not case.root_cause_any
            or any(term.casefold() in hypothesis_text for term in case.root_cause_any)
        ),
        "terminal_status": (
            not case.allowed_graph_statuses
            or str(record.get("graph_status")) in case.allowed_graph_statuses
        ),
        "tool_budget": (
            case.max_tool_calls is None
            or int(state.get("tool_calls_used", 0)) <= case.max_tool_calls
        ),
        "safe_action": (
            not case.require_no_action or state.get("proposed_action") is None
        ),
    }
    score = sum(criteria.values()) / len(criteria)
    return EvaluationResult(
        case=case.name,
        incident_id=str(record.get("incident_id", "unknown")),
        score=score,
        criteria=criteria,
    )


def find_matching_record(
    records: list[dict[str, Any]], case: EvaluationCase
) -> dict[str, Any] | None:
    return next((record for record in records if record_matches(record, case)), None)
