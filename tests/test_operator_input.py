from __future__ import annotations

from uuid import uuid4

from incident_investigator.application.operator_input import (
    OperatorEvidenceStore,
    OperatorEvidenceSubmission,
)


def test_operator_evidence_is_redacted_hashed_and_stored(tmp_path) -> None:
    incident_id = uuid4()
    request_id = uuid4()
    store = OperatorEvidenceStore(tmp_path)

    evidence = store.save(
        incident_id,
        OperatorEvidenceSubmission(
            request_id=request_id,
            text="database refused connection\npassword=super-secret-value",
            source_name="../stack trace.log",
            media_type="text/plain",
        ),
    )

    assert evidence.kind == "operator_evidence"
    assert "super-secret-value" not in evidence.summary
    assert "[REDACTED]" in evidence.summary
    assert evidence.content_hash is not None
    assert evidence.attributes["source_name"] == "stack-trace.log"
    stored = list((tmp_path / str(incident_id) / str(request_id)).iterdir())
    assert len(stored) == 1
    assert "super-secret-value" not in stored[0].read_text(encoding="utf-8")
