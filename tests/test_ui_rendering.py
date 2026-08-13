from incident_investigator.ui.app import (
    TEXT,
    _evidence_summary,
    _humanize_error,
    _visible_evidence,
)


def test_visible_evidence_keeps_only_latest_metric_sample() -> None:
    items = [
        {
            "kind": "metric_snapshot",
            "summary": '{"result":[{"metric":{},"value":[1,"0.7"]}]}',
            "attributes": {"query_name": "error_ratio"},
        },
        {
            "kind": "event_metadata",
            "summary": "inspect deployment history",
            "attributes": {},
        },
        {
            "kind": "metric_snapshot",
            "summary": '{"result":[{"metric":{},"value":[2,"0.8"]}]}',
            "attributes": {"query_name": "error_ratio"},
        },
    ]

    visible = _visible_evidence(items)

    assert len(visible) == 2
    assert visible[-1] == items[-1]
    assert _evidence_summary(visible[-1]) == "error ratio = 0.8"


def test_budget_truncation_is_an_operator_note() -> None:
    message, is_note = _humanize_error(
        "budget:tool_call_budget_truncated", TEXT["en"]
    )

    assert is_note is True
    assert "safely escalated" in message
