"""Faithfulness eval for the review-summary / Q&A surface.

Runs 10 cases (5 answerable + 5 unanswerable) against the running llm
service and reports faithfulness_rate = passed / total.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LLM_URL = "http://localhost:8000/v1/chat/completions"
CASES_PATH = Path(__file__).parent / "data" / "eval" / "faithfulness-cases.jsonl"
OUTPUT_PATH = Path(__file__).parent / "data" / "eval" / "faithfulness-results.json"

ABSTAIN_PHRASES = [
    "no information",
    "don't have",
    "do not have",
    "unable to answer",
    "cannot answer",
    "can't answer",
    "not mentioned",
    "insufficient",
]

RATE_LIMIT_SLEEP = 2.0  # Groq free tier ~30 RPM


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"invalid JSON at line {line_number}: {e}") from e
    if not cases:
        raise ValueError("no cases loaded")
    return cases


def build_messages(case: dict) -> list[dict]:
    product_id = case["product_id"]
    question = case["question"]
    reviews_json = json.dumps({"reviews": case["reviews"]})
    return [
        {"role": "user", "content": f"Can you summarize the product reviews? product ID:{product_id}"},
        {"role": "tool", "tool_call_id": "c1", "content": reviews_json},
        {
            "role": "user",
            "content": (
                f"Based on the tool results, answer the original question about "
                f"product ID:{product_id}. Question: {question}"
            ),
        },
    ]


def call_llm(case: dict, retries: int = 3) -> dict:
    body = json.dumps({"model": "techx-llm", "messages": build_messages(case)}).encode()
    req = urllib.request.Request(
        LLM_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last_error = f"http_{e.code}"
            if e.code == 429:
                time.sleep(RATE_LIMIT_SLEEP * (attempt + 1))
                continue
            raise
        except (TimeoutError, urllib.error.URLError) as e:
            last_error = str(e)
            time.sleep(RATE_LIMIT_SLEEP)
    raise RuntimeError(f"llm call failed after {retries} retries: {last_error}")


def evaluate_case(case: dict) -> dict:
    response = call_llm(case)
    choice = response["choices"][0]["message"]
    content = str(choice.get("content", ""))
    content_lower = content.lower()
    model = response.get("model", "unknown")

    expected = case["expected"]
    if expected == "answerable":
        keywords = [k.lower() for k in case.get("keywords", [])]
        mentions_keyword = any(k in content_lower for k in keywords)
        mentions_abstain = any(p in content_lower for p in ABSTAIN_PHRASES)
        passed = mentions_keyword and not mentions_abstain
    elif expected == "unanswerable":
        passed = any(p in content_lower for p in ABSTAIN_PHRASES)
    else:
        raise ValueError(f"unknown expected: {expected}")

    return {
        "case_id": case["case_id"],
        "expected": expected,
        "passed": passed,
        "model": model,
        "response": content,
    }


def main() -> int:
    cases = load_cases(CASES_PATH)
    print(f"running {len(cases)} faithfulness cases against {LLM_URL}\n")

    results = []
    for i, case in enumerate(cases, 1):
        try:
            result = evaluate_case(case)
        except Exception as e:
            result = {
                "case_id": case["case_id"],
                "expected": case["expected"],
                "passed": False,
                "error": str(e),
            }
        status = "PASS" if result.get("passed") else "FAIL"
        print(f"[{i:2d}/{len(cases)}] {case['case_id']:10s} {case['expected']:12s} {status}")
        results.append(result)
        time.sleep(RATE_LIMIT_SLEEP)

    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    rate = passed / total if total else 0.0

    answerable_passed = sum(1 for r in results if r.get("passed") and r["expected"] == "answerable")
    answerable_total = sum(1 for r in results if r["expected"] == "answerable")
    unanswerable_passed = sum(1 for r in results if r.get("passed") and r["expected"] == "unanswerable")
    unanswerable_total = sum(1 for r in results if r["expected"] == "unanswerable")

    aggregate = {
        "total_cases": total,
        "passed": passed,
        "faithfulness_rate": round(rate, 4),
        "answerable": {
            "passed": answerable_passed,
            "total": answerable_total,
            "rate": round(answerable_passed / answerable_total, 4) if answerable_total else 0.0,
        },
        "unanswerable": {
            "passed": unanswerable_passed,
            "total": unanswerable_total,
            "rate": round(unanswerable_passed / unanswerable_total, 4) if unanswerable_total else 0.0,
        },
    }

    report = {
        "schema_version": 1,
        "evaluation": "m6-faithfulness",
        "endpoint": LLM_URL,
        "aggregate": aggregate,
        "results": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(json.dumps(aggregate, indent=2))
    print(f"\nresults written to: {OUTPUT_PATH}")

    return 0 if rate >= 0.6 else 1


if __name__ == "__main__":
    sys.exit(main())