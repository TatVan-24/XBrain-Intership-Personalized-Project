"""Validate human-approved labels and build a deterministic eval set."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

try:
    from .prepare_dataset import EMAIL, INJECTION, PHONE
except ImportError:  # Support direct execution from src/llm/fallback.
    from prepare_dataset import EMAIL, INJECTION, PHONE


def normalized(text: str) -> str:
    return " ".join(str(text).lower().split())


def case_id(product_id: str, category: str) -> str:
    return hashlib.sha256(f"{product_id}:{category}".encode()).hexdigest()[:12]


def validate_record(item: dict, line_number: int) -> list[str]:
    errors = []
    if not str(item.get("product_id", "")).strip():
        errors.append(f"line {line_number}: missing product_id")
    if item.get("label_status") != "human_approved":
        errors.append(f"line {line_number}: label_status must be human_approved")
    summary = str(item.get("summary") or "").strip()
    if len(summary.split()) < 5:
        errors.append(f"line {line_number}: reference summary is too short")
    if EMAIL.search(summary) or PHONE.search(summary):
        errors.append(f"line {line_number}: reference summary contains PII")
    if not item.get("reviews"):
        errors.append(f"line {line_number}: no reviews")
    return errors


def build(source: Path, output: Path, manifest_path: Path) -> dict:
    records, errors, seen_products = [], [], set()
    with source.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            errors.extend(validate_record(item, line_number))
            product_id = str(item.get("product_id", "")).strip()
            if product_id in seen_products:
                errors.append(f"line {line_number}: duplicate product_id {product_id}")
            seen_products.add(product_id)
            records.append(item)
    if errors:
        raise ValueError("\n".join(errors))

    cases, category_counts = [], Counter()
    excluded_seed_reviews = 0
    source_fingerprints = set()
    for item in records:
        product_id = item["product_id"]
        all_reviews = item["reviews"]
        reviews = [review for review in all_reviews if not review.get("is_seed", False)]
        excluded_seed_reviews += len(all_reviews) - len(reviews)
        if not reviews:
            raise ValueError(f"no natural reviews available for {product_id}")
        fingerprint = hashlib.sha256("|".join(sorted(normalized(r["text"]) for r in reviews)).encode()).hexdigest()
        if fingerprint in source_fingerprints:
            raise ValueError(f"cross-product duplicate review corpus detected for {product_id}")
        source_fingerprints.add(fingerprint)
        categories = {"faithfulness"}
        if any(INJECTION.search(str(review.get("text", ""))) for review in reviews):
            categories.add("injection")
        if any(EMAIL.search(str(review.get("text", ""))) or PHONE.search(str(review.get("text", ""))) for review in reviews):
            categories.add("pii")
        scores = [float(review["score"]) for review in reviews if review.get("score") is not None]
        if scores and min(scores) <= 2 and max(scores) >= 4:
            categories.add("mixed_sentiment")
        if len(reviews) <= 2:
            categories.add("partial_information")
        case = {
            "case_id": case_id(product_id, "summary"),
            "surface": "review_summary",
            "product_id": product_id,
            "review_version": item.get("review_version"),
            "reviews": reviews,
            "reference_summary": item["summary"],
            "categories": sorted(categories),
            "expected": {"pii_leak": False, "follow_review_instructions": False},
        }
        cases.append(case)
        category_counts.update(categories)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for case in sorted(cases, key=lambda value: value["case_id"]):
            file.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": 1,
        "case_count": len(cases),
        "category_counts": dict(sorted(category_counts.items())),
        "excluded_seed_reviews": excluded_seed_reviews,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "policy": "human-approved labels and natural reviews only; never use this output for training",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.input, args.output, args.manifest), indent=2))
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
