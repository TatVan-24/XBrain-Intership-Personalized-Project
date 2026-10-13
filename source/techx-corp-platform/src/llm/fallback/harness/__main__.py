# CLI entry

"""CLI: python -m harness --cases cases.jsonl --output results.json"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .loader import load_cases
# from .runner import run_case, DEFAULT_ENDPOINT
from .evaluator_nli import evaluate_case
from .report import build_report


"""CLI: python -m harness --cases cases.jsonl --output results.json"""

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="harness", description="M14 NLI harness")
    p.add_argument("--cases", type=Path, required=True, help="Path to cases.jsonl")
    p.add_argument("--output", type=Path, required=True, help="Path to write results.json")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_cases(args.cases)
    print(f"loaded {len(cases)} cases from {args.cases}")
    print("evaluator: NLI (cross-encoder/nli-deberta-v3-small)")
    print("mode: load per case (MVP — slow but RAM-friendly)")
    print()

    case_results: list[dict] = []
    for i, case in enumerate(cases, 1):
        started = time.perf_counter()
        try:
            result = evaluate_case(case["evidence"], case["claim"])
            verdict = result["verdict"]
            passed = verdict == case["expected"]
            case_results.append({
                "case_id": case["case_id"],
                "category": case["category"],
                "expected": case["expected"],
                "verdict": verdict,
                "passed": passed,
                "raw_label": result["raw_label"],
                "probabilities": result["probabilities"],
                "note": case.get("note"),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            })
        except Exception as e:
            case_results.append({
                "case_id": case["case_id"],
                "category": case["category"],
                "expected": case["expected"],
                "verdict": "error",
                "passed": False,
                "error": str(e),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            })
            passed = False

        mark = "PASS" if passed else "FAIL"
        got = case_results[-1].get("verdict", "error")
        print(f"[{i:3d}/{len(cases)}] {case['case_id']:15s} {case['category']:15s} "
              f"expected={case['expected']:13s} got={got:13s} {mark}")

    report = build_report(case_results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=== per-category ===")
    for cat, stats in report["per_category"].items():
        print(f"  {cat:15s} {stats['passed']}/{stats['total']}  rate={stats['rate']}")
    print()
    print(f"=== overall ===  {report['overall']['passed']}/{report['overall']['total']}  "
          f"rate={report['overall']['rate']}")
    print()
    print(f"results written to {args.output}")

    return 0 if report["overall"]["rate"] >= 0.6 else 1


if __name__ == "__main__":
    sys.exit(main())