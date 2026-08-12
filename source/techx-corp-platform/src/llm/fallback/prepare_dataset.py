"""Prepare product-isolated JSONL splits for T5 review-summary fine-tuning."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")
INJECTION = re.compile(r"\b(ignore|disregard|forget)\b.{0,40}\b(instruction|prompt|system|above|previous)\b", re.IGNORECASE)


def sanitize(text: str) -> str:
    text = EMAIL.sub("[EMAIL]", str(text))
    text = PHONE.sub("[PHONE]", text)
    return " ".join(text.split())


def chunk_reviews(reviews: Iterable[dict], max_words: int) -> list[str]:
    chunks, current = [], []
    current_words = 0
    for review in reviews:
        text = sanitize(review.get("text", ""))
        if not text or INJECTION.search(text):
            continue
        score = review.get("score")
        rendered = f"rating={score}; review={text}" if score is not None else f"review={text}"
        words = rendered.split()
        if len(words) > max_words:
            rendered = " ".join(words[:max_words])
            words = rendered.split()
        if current and current_words + len(words) > max_words:
            chunks.append(" | ".join(current))
            current, current_words = [], 0
        current.append(rendered)
        current_words += len(words)
    if current:
        chunks.append(" | ".join(current))
    return chunks


def product_split(product_id: str) -> str:
    bucket = int(hashlib.sha256(product_id.encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 8 else "validation" if bucket == 8 else "test"


def prepare(source: Path, destination: Path, max_words: int = 220) -> dict[str, int]:
    destination.mkdir(parents=True, exist_ok=True)
    handles = {name: (destination / f"{name}.jsonl").open("w", encoding="utf-8") for name in ("train", "validation", "test")}
    counts = {name: 0 for name in handles}
    try:
        with source.open(encoding="utf-8") as input_file:
            for line_number, line in enumerate(input_file, start=1):
                if not line.strip():
                    continue
                item = json.loads(line)
                product_id = str(item.get("product_id", "")).strip()
                target = sanitize(item.get("summary", ""))
                if not product_id or not target:
                    raise ValueError(f"Line {line_number}: product_id and summary are required")
                split = product_split(product_id)
                for index, chunk in enumerate(chunk_reviews(item.get("reviews", []), max_words)):
                    record = {"example_id": f"{product_id}:{index}", "product_id": product_id, "input_text": f"summarize product reviews: {chunk}", "target_text": target}
                    handles[split].write(json.dumps(record, ensure_ascii=False) + "\n")
                    counts[split] += 1
    finally:
        for handle in handles.values():
            handle.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-words", type=int, default=220)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output, args.max_words), indent=2))


if __name__ == "__main__":
    main()
