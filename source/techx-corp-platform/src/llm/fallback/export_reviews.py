"""Export privacy-minimized product review snapshots from PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


QUERY = """
SELECT product_id, id, description, score, created_at, updated_at,
       (user_id IS NULL AND username LIKE 'seed_user_%') AS is_seed
FROM reviews.productreviews
WHERE deleted_at IS NULL AND description IS NOT NULL
ORDER BY product_id, created_at, id
"""


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def build_records(rows, minimum_reviews: int = 1) -> tuple[list[dict], dict]:
    grouped = defaultdict(list)
    for product_id, review_id, description, score, created_at, updated_at, is_seed in rows:
        grouped[str(product_id)].append({
            "review_id": str(review_id),
            "text": str(description).strip(),
            "score": float(score),
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "is_seed": bool(is_seed),
        })

    records, total_duplicates, total_seed = [], 0, 0
    for product_id, reviews in grouped.items():
        if len(reviews) < minimum_reviews:
            continue
        frequencies = Counter(normalize(item["text"]) for item in reviews)
        for item in reviews:
            item["duplicate_count"] = frequencies[normalize(item["text"])]
        total_duplicates += sum(count - 1 for count in frequencies.values())
        total_seed += sum(item["is_seed"] for item in reviews)
        version_material = "|".join(f"{item['review_id']}:{item['updated_at']}" for item in reviews)
        records.append({
            "product_id": product_id,
            "review_version": hashlib.sha256(version_material.encode()).hexdigest()[:16],
            "reviews": reviews,
            "summary": None,
            "label_status": "pending_human_review",
            "provenance": {
                "source": "postgresql.reviews.productreviews",
                "review_count": len(reviews),
                "unique_text_count": len(frequencies),
                "seed_review_count": sum(item["is_seed"] for item in reviews),
            },
        })
    manifest = {
        "products": len(records),
        "reviews": sum(len(item["reviews"]) for item in records),
        "duplicate_reviews": total_duplicates,
        "seed_reviews": total_seed,
        "privacy": "username and user_id intentionally excluded",
    }
    return records, manifest


def export(dsn: str, output: Path, minimum_reviews: int = 1) -> dict:
    try:
        import psycopg2
    except ImportError as error:
        raise SystemExit("Install psycopg2-binary before exporting PostgreSQL reviews") from error
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(QUERY)
        records, manifest = build_records(cursor.fetchall(), minimum_reviews)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("REVIEW_EXPORT_DSN") or os.getenv("DB_CONNECTION_STRING"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-reviews", type=int, default=1)
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("Pass --dsn or set REVIEW_EXPORT_DSN; credentials are never written to output")
    print(json.dumps(export(args.dsn, args.output, args.minimum_reviews), indent=2))


if __name__ == "__main__":
    main()
