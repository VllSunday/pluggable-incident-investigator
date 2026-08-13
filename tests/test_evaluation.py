from incident_investigator.evaluation import EvaluationCase, evaluate_record


def test_evaluation_scores_evidence_root_cause_budget_and_safety() -> None:
    case = EvaluationCase(
        name="runtime",
        match={"source": "alertmanager", "service": "runtime-demo"},
        required_evidence_kinds=("event_metadata", "metric_snapshot"),
        root_cause_any=("error ratio",),
        allowed_graph_statuses=("escalated",),
        max_tool_calls=12,
        require_no_action=True,
    )
    record = {
        "incident_id": "incident-1",
        "graph_status": "escalated",
        "event": {"source": "alertmanager", "service": "runtime-demo"},
        "state": {
            "evidence": [
                {"kind": "event_metadata"},
                {"kind": "metric_snapshot"},
            ],
            "hypotheses": [{"statement": "The observed error ratio is 0.8"}],
            "tool_calls_used": 12,
            "proposed_action": None,
        },
    }

    result = evaluate_record(record, case)

    assert result.score == 1.0
    assert all(result.criteria.values())
