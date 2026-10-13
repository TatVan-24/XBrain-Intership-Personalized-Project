# đọc JSONL

"""Load and validate JSONL case files for NLI evaluator."""
from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FIELDS = ("case_id", "category", "evidence", "claim", "expected")
VALID_VERDICTS = {"supported", "contradicted", "unsupported"}


def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Cases file not found: {path}")

    cases: list[dict] = []
    errors: list[str] = []

    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: invalid JSON ({e})")
                continue

            missing = [k for k in REQUIRED_FIELDS if k not in case]
            if missing:
                errors.append(f"line {lineno}: missing fields {missing}")
                continue

            if case["expected"] not in VALID_VERDICTS:
                errors.append(
                    f"line {lineno}: expected must be one of {VALID_VERDICTS}, "
                    f"got {case['expected']!r}"
                )
                continue

            if not str(case["evidence"]).strip():
                errors.append(f"line {lineno}: evidence is empty")
                continue

            if not str(case["claim"]).strip():
                errors.append(f"line {lineno}: claim is empty")
                continue

            cases.append(case)

    if errors:
        raise ValueError("Invalid cases:\n  " + "\n  ".join(errors))
    if not cases:
        raise ValueError(f"No valid cases in {path}")
    return cases