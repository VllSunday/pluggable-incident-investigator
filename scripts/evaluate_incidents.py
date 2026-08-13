from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import yaml

from incident_investigator.evaluation import (
    EvaluationCase,
    evaluate_record,
    find_matching_record,
)
from incident_investigator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score persisted incidents against ground truth")
    parser.add_argument("--cases", type=Path, default=Path("evals/ground_truth.yaml"))
    parser.add_argument("--case", action="append", dest="selected_cases")
    parser.add_argument("--input", type=Path, help="JSON list exported from /api/incidents")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--minimum-score", type=float, default=0.8)
    return parser.parse_args()


def load_records(args: argparse.Namespace) -> list[dict]:
    if args.input:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("--input must contain a JSON list")
        return value

    token = Settings().admin_api_token.get_secret_value()
    response = httpx.get(
        f"{args.api_url.rstrip('/')}/api/incidents",
        params={"limit": 500},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    args = parse_args()
    raw_cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))["cases"]
    cases = [EvaluationCase.model_validate(item) for item in raw_cases]
    if args.selected_cases:
        selected = set(args.selected_cases)
        cases = [case for case in cases if case.name in selected]
        missing_names = selected - {case.name for case in cases}
        if missing_names:
            raise ValueError(f"Unknown evaluation cases: {sorted(missing_names)}")
    records = load_records(args)
    report = []
    failed = False
    for case in cases:
        record = find_matching_record(records, case)
        if record is None:
            report.append({"case": case.name, "status": "not_observed"})
            failed = True
            continue
        result = evaluate_record(record, case)
        report.append(
            {
                "case": result.case,
                "incident_id": result.incident_id,
                "score": round(result.score, 3),
                "criteria": result.criteria,
            }
        )
        failed = failed or result.score < args.minimum_score

    print(json.dumps({"results": report}, indent=2, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
