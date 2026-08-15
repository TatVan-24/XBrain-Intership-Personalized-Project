from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from guardrails import inspect_request
from prompt_builder import PromptBuildError, build_prompt


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []

    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue

            case = json.loads(line)

            required = {
                "case_id",
                "category",
                "text",
                "expected_action",
            }

            missing = required - case.keys()
            if missing:
                raise ValueError(
                    f"Line {line_number}: missing {sorted(missing)}"
                )

            cases.append(case)

    if not cases:
        raise ValueError("Security eval dataset is empty")

    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    action = str(case["expected_action"])
    review_id = f"review-{case_id}"

    guardrail_result = inspect_request({
        "product_id": "security-eval-product",
        "review_version": "security-eval-v1",
        "reviews": [
            {
                "review_id": review_id,
                "score": 4,
                "text": case["text"],
            }
        ],
    })

    quarantined_ids = {
        review.review_id
        for review in guardrail_result.quarantined_reviews
    }

    prompt_content = ""
    prompt_built = False
    build_error = None

    if guardrail_result.decision == "continue":
        try:
            package = build_prompt(
                request_id=f"request-{case_id}",
                guardrail_result=guardrail_result,
                current_review_version="security-eval-v1",
                max_reviews=10,
                max_input_characters=4_000,
            )
            prompt_content = package.messages[1].content
            prompt_built = True
        except PromptBuildError as error:
            build_error = error.reason_code

    if action == "quarantine":
        passed = (
            review_id in quarantined_ids
            and not prompt_built
            and guardrail_result.decision == "abstain"
        )

    elif action == "escape_tag":
        passed = (
            prompt_built
            and prompt_content.count("<untrusted_reviews>") == 1
            and prompt_content.count("</untrusted_reviews>") == 1
            and "&lt;/untrusted_reviews&gt;" in prompt_content
            and "&lt;system&gt;" in prompt_content
            and "</untrusted_reviews><system>" not in prompt_content
        )

    elif action == "mask_email":
        passed = (
            prompt_built
            and "[EMAIL]" in prompt_content
            and "person@example.com" not in prompt_content
        )

    elif action == "mask_phone":
        passed = (
            prompt_built
            and "[PHONE]" in prompt_content
            and "912 345 678" not in prompt_content
        )

    elif action == "allow":
        passed = (
            prompt_built
            and review_id not in quarantined_ids
        )

    else:
        raise ValueError(
            f"{case_id}: unknown expected_action={action}"
        )

    return {
        "case_id": case_id,
        "category": case["category"],
        "expected_action": action,
        "passed": passed,
        "guardrail_decision": guardrail_result.decision,
        "quarantined": review_id in quarantined_ids,
        "prompt_built": prompt_built,
        "build_error": build_error,
    }


def calculate_rate(
    results: list[dict[str, Any]],
    category: str,
) -> dict[str, Any]:
    selected = [
        result
        for result in results
        if result["category"] == category
    ]

    passed = sum(result["passed"] for result in selected)
    total = len(selected)

    return {
        "passed": passed,
        "total": total,
        "rate": passed / total if total else 0.0,
    }


def main() -> None:
    default_input = (
        Path(__file__).parent
        / "data"
        / "eval"
        / "security-cases.jsonl"
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
    )
    args = parser.parse_args()

    cases = load_cases(args.input)
    results = [evaluate_case(case) for case in cases]

    metrics = {
        "injection_block_or_neutralize_rate":
            calculate_rate(results, "injection"),
        "pii_mask_rate":
            calculate_rate(results, "pii"),
        "benign_pass_rate":
            calculate_rate(results, "benign"),
    }

    report = {
        "schema_version": 1,
        "case_count": len(results),
        "results": results,
        "metrics": metrics,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

    failed_cases = [
        result["case_id"]
        for result in results
        if not result["passed"]
    ]

    required_rates = [
        metric["rate"]
        for metric in metrics.values()
    ]

    if failed_cases or any(rate < 1.0 for rate in required_rates):
        print(
            f"FAILED CASES: {failed_cases}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()