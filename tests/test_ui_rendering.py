from incident_investigator.ui.app import (
    TEXT,
    _evidence_html,
    _evidence_summary,
    _humanize_error,
    _operator_guidance,
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


def test_long_code_evidence_is_isolated_in_expandable_preformatted_block() -> None:
    rendered = _evidence_html(
        {
            "kind": "commit_diff",
            "summary": "FILE SNAPSHOT README.md\n`retry_delay`\n<script>alert(1)</script>",
            "attributes": {},
        },
        TEXT["en"],
    )

    assert '<details class="evidence-details">' in rendered
    assert '<div class="evidence-raw">' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&#96;retry_delay&#96;" in rendered


def test_escalated_guidance_names_manual_check_and_confirms_no_change() -> None:
    guidance = _operator_guidance(
        {
            "status": "escalated",
            "state": {
                "hypotheses": [
                    {
                        "statement": "The error ratio is 0.8 while the target remains up.",
                        "confidence": 0.88,
                        "required_checks": ["Inspect application logs for the failing route."],
                    }
                ]
            },
        },
        TEXT["en"],
    )

    assert guidance["headline"] == "Manual review needed"
    assert "Inspect application logs" in guidance["next_step"]
    assert guidance["impact"] == "No changes were made."


def test_recovered_guidance_requires_no_manual_recheck() -> None:
    guidance = _operator_guidance(
        {
            "status": "completed",
            "state": {
                "recovery_verified": True,
                "action_result": {"success": True},
            },
        },
        TEXT["en"],
    )

    assert "Nothing else is required" in guidance["next_step"]
    assert "independently verified" in guidance["impact"]


def test_awaiting_input_guidance_explains_that_investigation_will_resume() -> None:
    guidance = _operator_guidance(
        {
            "status": "awaiting_input",
            "state": {
                "information_request": {
                    "question": "Provide application logs for the incident window."
                }
            },
        },
        TEXT["en"],
    )

    assert guidance["headline"] == "The agent needs additional evidence"
    assert "resume automatically" in guidance["next_step"]
    assert "No changes were made" in guidance["impact"]
