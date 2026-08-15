"""Shared request/response contracts for the local summary fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


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
    status: Literal["completed", "unavailable"]
    summary: str | None
    source_review_ids: tuple[str, ...]
    model_source: str
    model_version: str
    review_version: str
    degraded: bool = True
    validation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"completed", "unavailable"}:
            raise ValueError("Unsupported summary response status")

        if not self.model_source.strip():
            raise ValueError("model_source is required")

        if not self.model_version.strip():
            raise ValueError("model_version is required")

        if not self.review_version.strip():
            raise ValueError("review_version is required")

        if self.status == "completed":
            if self.summary is None or not self.summary.strip():
                raise ValueError(
                    "completed response requires a non-empty summary"
                )

            if not self.source_review_ids:
                raise ValueError(
                    "completed response requires source_review_ids"
                )

            if self.validation_codes:
                raise ValueError(
                    "completed response cannot contain blocking validation codes"
                )

        if self.status == "unavailable":
            if self.summary is not None:
                raise ValueError(
                    "unavailable response requires summary=None"
                )

            if self.source_review_ids:
                raise ValueError(
                    "unavailable response cannot expose source_review_ids"
                )

            if not self.validation_codes:
                raise ValueError(
                    "unavailable response requires validation_codes"
                )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_review_ids"] = list(self.source_review_ids)
        result["validation_codes"] = list(self.validation_codes)
        return result


def validate_summary(text: str, minimum_words: int = 3, maximum_words: int = 160) -> str:
    normalized = " ".join(str(text).split())
    word_count = len(normalized.split())
    if word_count < minimum_words:
        raise ValueError("Generated summary is too short")
    if word_count > maximum_words:
        raise ValueError("Generated summary is too long")
    return normalized
