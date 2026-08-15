"""Create a deduplicated, human-reviewable labeling batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_drafts(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["product_id"]): str(item["product_review_summary"]).strip()
        for item in payload.get("product-review-summaries", [])
    }


def deduplicate(reviews: list[dict]) -> list[dict]:
    """Prefer a natural review when seed and natural texts collide."""
    selected = {}
    for review in reviews:
        key = " ".join(str(review["text"]).lower().split())
        existing = selected.get(key)
        if existing is None or (existing.get("is_seed") and not review.get("is_seed")):
            selected[key] = review
    return sorted(selected.values(), key=lambda item: (bool(item.get("is_seed")), item["review_id"]))


def create_batch(source: Path, output: Path, drafts_path: Path | None = None) -> dict:
    drafts = load_drafts(drafts_path)
    records, total_reviews = [], 0
    with source.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            reviews = deduplicate(item["reviews"])
            total_reviews += len(reviews)
            records.append({
                "product_id": item["product_id"],
                "review_version": item["review_version"],
                "reviews": [{
                    "review_id": review["review_id"],
                    "text": review["text"],
                    "score": review.get("score"),
                    "is_seed": review.get("is_seed", False),
                } for review in reviews],
                "draft_summary": drafts.get(item["product_id"]),
                "summary": None,
                "label_status": "pending_human_review",
                "reviewer_notes": None,
                "provenance": item.get("provenance", {}),
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "products": len(records),
        "unique_reviews_for_labeling": total_reviews,
        "draft_summaries_available": sum(bool(item["draft_summary"]) for item in records),
        "approved_labels": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draft-summaries", type=Path)
    args = parser.parse_args()
    print(json.dumps(create_batch(args.input, args.output, args.draft_summaries), indent=2))


if __name__ == "__main__":
    main()
