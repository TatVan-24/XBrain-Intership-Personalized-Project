"""Shared request/response contracts for the local summary fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Review:
    review_id: str
    text: str
    score: float | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Review":
        review_id = str(value.get("review_id", "")).strip()
        text = str(value.get("text", "")).strip()
        if not review_id or not text:
            raise ValueError("Each review requires non-empty review_id and text")
        score = value.get("score")
        if score is not None:
            score = float(score)
            if not 1 <= score <= 5:
                raise ValueError("Review score must be between 1 and 5")
        return cls(review_id=review_id, text=text, score=score)


@dataclass(frozen=True)
class SummaryRequest:
    product_id: str
    review_version: str
    reviews: tuple[Review, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SummaryRequest":
        product_id = str(value.get("product_id", "")).strip()
        review_version = str(value.get("review_version", "")).strip()
        raw_reviews = value.get("reviews")
        if not product_id or not review_version:
            raise ValueError("product_id and review_version are required")
        if not isinstance(raw_reviews, list) or not raw_reviews:
            raise ValueError("reviews must be a non-empty list")
        return cls(product_id, review_version, tuple(Review.from_dict(item) for item in raw_reviews))


@dataclass(frozen=True)
class SummaryResponse:
    summary: str
    source_review_ids: tuple[str, ...]
    model_source: str
    model_version: str
    review_version: str
    degraded: bool = True

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_review_ids"] = list(self.source_review_ids)
        return result


def validate_summary(text: str, minimum_words: int = 3, maximum_words: int = 160) -> str:
    normalized = " ".join(str(text).split())
    word_count = len(normalized.split())
    if word_count < minimum_words:
        raise ValueError("Generated summary is too short")
    if word_count > maximum_words:
        raise ValueError("Generated summary is too long")
    return normalized
