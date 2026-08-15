from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

# from layer4_preview import Layer4Input, Review, validate_candidate
from output_guardrails import Layer4Input, Review, validate_candidate

ROOT = Path(__file__).resolve().parent
EVAL_DIR = ROOT / "data" / "eval"

BASELINE_PATH = EVAL_DIR / "t5-small-baseline-results.json"
CASES_PATH = EVAL_DIR / "pilot-cases.jsonl"
OUTPUT_PATH = EVAL_DIR / "t5-small-layer4-results.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict]:
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSONL at line {line_number}: {error}"
                ) from error

    return records


def main() -> int:
    baseline = load_json(BASELINE_PATH)
    pilot_cases = load_jsonl(CASES_PATH)

    cases_by_id = {
        case["case_id"]: case
        for case in pilot_cases
    }

    results = []
    decision_counts = Counter()
    next_action_counts = Counter()
    violation_counts = Counter()
    warning_counts = Counter()

    for prediction_record in baseline["results"]:
        case_id = prediction_record["case_id"]
        source_case = cases_by_id.get(case_id)

        if source_case is None:
            raise ValueError(
                f"Baseline case {case_id} is missing from pilot-cases.jsonl"
            )

        if prediction_record["product_id"] != source_case["product_id"]:
            raise ValueError(
                f"Product mismatch for case {case_id}"
            )

        reviews = tuple(
            Review(
                review_id=str(review["review_id"]),
                text=str(review["text"]),
                score=(
                    float(review["score"])
                    if review.get("score") is not None
                    else None
                ),
            )
            for review in source_case["reviews"]
        )

        payload = Layer4Input(
            request_id=f"baseline-{case_id}",
            product_id=str(source_case["product_id"]),
            review_version=str(source_case["review_version"]),
            candidate_role="fallback",
            model=str(baseline["model"]),
            summary=str(prediction_record["prediction"]),
            source_review_ids=tuple(
                review.review_id for review in reviews
            ),
            reviews=reviews,
            degraded=True,
        )

        validation = validate_candidate(payload)

        decision_counts[validation.decision] += 1
        next_action_counts[validation.next_action] += 1
        violation_counts.update(validation.violations)
        warning_counts.update(validation.warnings)

        results.append(
            {
                "case_id": case_id,
                "product_id": source_case["product_id"],
                "prediction": prediction_record["prediction"],
                "decision": validation.decision,
                "next_action": validation.next_action,
                "violations": list(validation.violations),
                "warnings": list(validation.warnings),
                "exact_quote_matches": [
                    {
                        "review_id": match.review_id,
                        "quote": match.quote,
                        "word_count": match.word_count,
                    }
                    for match in validation.exact_quote_matches
                ],
                "safe_response": validation.response,
            }
        )

    case_count = len(results)
    rejected_count = decision_counts["reject"]
    format_leak_count = violation_counts["MODEL_FORMAT_LEAK"]
    abstain_count = next_action_counts["abstain"]

    expected_behavior_passed = (
        case_count == 10
        and rejected_count == case_count
        and format_leak_count == case_count
        and abstain_count == case_count
        and all(
            item["safe_response"] is not None
            and item["safe_response"]["status"] == "unavailable"
            and item["safe_response"]["summary"] is None
            for item in results
        )
    )

    report = {
        "schema_version": 1,
        "evaluation": "t5-small-untuned-layer4-regression",
        "model": baseline["model"],
        "case_count": case_count,
        "aggregate": {
            "decision_counts": dict(decision_counts),
            "next_action_counts": dict(next_action_counts),
            "violation_counts": dict(violation_counts),
            "warning_counts": dict(warning_counts),
            "format_leak_recall_on_known_baseline": (
                format_leak_count / case_count
                if case_count
                else 0.0
            ),
            "unsafe_summary_returned_count": sum(
                1
                for item in results
                if item["decision"] == "reject"
                and item["safe_response"]
                and item["safe_response"]["summary"] is not None
            ),
            "expected_behavior_passed": expected_behavior_passed,
        },
        "results": results,
    }

    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report["aggregate"],
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Results written to: {OUTPUT_PATH}")

    return 0 if expected_behavior_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())