# aggregate + output

"""Aggregate per-case NLI results into per-category and overall."""
from __future__ import annotations

from collections import defaultdict


def build_report(case_results: list[dict]) -> dict:
    overall_passed = sum(1 for r in case_results if r["passed"])
    overall_total = len(case_results)

    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    for r in case_results:
        by_cat[r["category"]]["total"] += 1
        if r["passed"]:
            by_cat[r["category"]]["passed"] += 1

    per_category = {
        cat: {
            "passed": c["passed"],
            "total": c["total"],
            "rate": round(c["passed"] / c["total"], 4) if c["total"] else 0.0,
        }
        for cat, c in by_cat.items()
    }

    return {
        "schema_version": 1,
        "per_case": case_results,
        "per_category": per_category,
        "overall": {
            "passed": overall_passed,
            "total": overall_total,
            "rate": round(overall_passed / overall_total, 4) if overall_total else 0.0,
        },
    }