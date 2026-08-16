from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from incident_investigator.domain import EvidenceItem

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[:=]\s*)[^\s]+"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
)


class OperatorEvidenceSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    text: str = Field(min_length=1, max_length=1_000_000)
    source_name: str = Field(default="operator-note.txt", min_length=1, max_length=160)
    media_type: str = Field(default="text/plain", min_length=1, max_length=100)


def redact_operator_evidence(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class OperatorEvidenceStore:
    def __init__(self, base_path: Path, *, max_summary_characters: int = 16_000) -> None:
        self._base_path = base_path
        self._max_summary_characters = max_summary_characters

    def save(
        self, incident_id: UUID, submission: OperatorEvidenceSubmission
    ) -> EvidenceItem:
        raw = submission.text
        redacted = redact_operator_evidence(raw)
        digest = hashlib.sha256(raw.encode(errors="replace")).hexdigest()
        safe_name = self._safe_name(submission.source_name)
        destination = self._base_path / str(incident_id) / str(submission.request_id)
        destination.mkdir(parents=True, exist_ok=True)
        stored_name = f"{digest[:12]}-{safe_name}"
        (destination / stored_name).write_text(redacted, encoding="utf-8")
        summary = self._excerpt(redacted)
        return EvidenceItem(
            kind="operator_evidence",
            source_uri=f"operator://{incident_id}/{submission.request_id}/{stored_name}",
            summary=summary,
            content_hash=digest,
            attributes={
                "provider": "operator",
                "request_id": str(submission.request_id),
                "source_name": safe_name,
                "media_type": submission.media_type,
                "redacted": redacted != raw,
                "original_characters": len(raw),
                "stored_characters": len(redacted),
            },
        )

    def _excerpt(self, value: str) -> str:
        if len(value) <= self._max_summary_characters:
            return value
        half = self._max_summary_characters // 2
        return f"{value[:half]}\n... [TRUNCATED] ...\n{value[-half:]}"

    @staticmethod
    def _safe_name(value: str) -> str:
        name = Path(value).name
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
        return cleaned[:100] or "operator-evidence.txt"
