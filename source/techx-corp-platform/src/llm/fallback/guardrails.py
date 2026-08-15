"""Deterministic Layer 1 waterfall guardrails for untrusted reviews."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from contracts import SummaryRequest

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
SPACE = re.compile(r"\s+")

OVERRIDE = re.compile(r"\b(ignore|disregard|forget|override|reveal|execute|call)\b", re.IGNORECASE)
PROTECTED = re.compile(r"\b(system\s*prompt|developer\s*message|secret|credential|api\s*key|tool)\b", re.IGNORECASE)
EXFILTRATION = re.compile(r"\b(show|print|return|expose|leak|send)\b.{0,50}\b(prompt|secret|credential|api\s*key)\b", re.IGNORECASE)
PROTECTED_TERMS = ("ignore", "system prompt", "developer message", "reveal", "secret", "credential", "execute tool")


@dataclass(frozen=True)
class SafeReview:
    review_id: str
    sanitized_text: str
    score: float | None


@dataclass(frozen=True)
class QuarantinedReview:
    review_id: str
    risk_level: str
    risk_score: int
    signals: tuple[str, ...]
    action: str = "quarantine"


@dataclass(frozen=True)
class GuardrailResult:
    product_id: str
    review_version: str
    safe_reviews: tuple[SafeReview, ...]
    quarantined_reviews: tuple[QuarantinedReview, ...]
    pii_mask_count: int
    decision: str
    degraded: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize(text: str) -> tuple[str, bool]:
    original = str(text)
    normalized = unicodedata.normalize("NFKC", original)
    cleaned = CONTROL.sub("", normalized)
    cleaned = SPACE.sub(" ", cleaned).strip()
    return cleaned, cleaned != SPACE.sub(" ", original).strip()


def reconstruct_spaced_tokens(text: str) -> tuple[str, bool]:
    """Build a detector-only view that joins runs such as 'i g n o r e'."""
    tokens = text.split()
    output: list[str] = []
    changed = False
    index = 0
    while index < len(tokens):
        end = index
        while end < len(tokens) and len(tokens[end]) == 1 and tokens[end].isalnum():
            end += 1
        if end - index >= 3:
            output.append("".join(tokens[index:end]))
            changed = True
            index = end
        else:
            output.append(tokens[index])
            index += 1
    return " ".join(output), changed


def mask_pii(text: str) -> tuple[str, int]:
    text, emails = EMAIL.subn("[EMAIL]", text)
    text, phones = PHONE.subn("[PHONE]", text)
    return text, emails + phones


def _fuzzy_signal(text: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", text.casefold())
    for term in PROTECTED_TERMS:
        target = re.sub(r"[^a-z0-9]", "", term)
        width = len(target)
        if target in compact:
            return True
        if width >= 6 and any(
            SequenceMatcher(None, compact[i:i + width], target).ratio() >= 0.86
            for i in range(max(1, len(compact) - width + 1))
        ):
            return True
    return False


def _assess(text: str, normalization_changed: bool, spacing_changed: bool) -> tuple[int, tuple[str, ...]]:
    signals: list[str] = []
    score = 0
    if normalization_changed or spacing_changed:
        signals.append("obfuscation")
        score += 1
    override = bool(OVERRIDE.search(text))
    protected = bool(PROTECTED.search(text))
    exfiltration = bool(EXFILTRATION.search(text))
    if override:
        signals.append("override_instruction")
        score += 2
    if protected:
        signals.append("protected_target")
        score += 2
    if exfiltration:
        signals.append("data_exfiltration")
        score += 3
    if (normalization_changed or spacing_changed) and _fuzzy_signal(text):
        signals.append("fuzzy_protected_term")
        score += 1
    if sum((override, protected, exfiltration)) >= 2:
        signals.append("combined_attack_pattern")
        score += 2
    return score, tuple(dict.fromkeys(signals))


def inspect_request(value: dict[str, Any] | SummaryRequest) -> GuardrailResult:
    request = value if isinstance(value, SummaryRequest) else SummaryRequest.from_dict(value)
    safe: list[SafeReview] = []
    quarantined: list[QuarantinedReview] = []
    pii_count = 0

    for review in request.reviews:
        normalized, normalization_changed = normalize(review.text)
        detector_text, spacing_changed = reconstruct_spaced_tokens(normalized)
        sanitized, masked = mask_pii(normalized)
        pii_count += masked
        risk_score, signals = _assess(detector_text, normalization_changed, spacing_changed)
        if risk_score >= 3:
            level = "critical" if risk_score >= 5 else "high"
            quarantined.append(QuarantinedReview(review.review_id, level, risk_score, signals))
        else:
            safe.append(SafeReview(review.review_id, sanitized, review.score))

    decision = "continue" if safe else "abstain"
    return GuardrailResult(
        product_id=request.product_id,
        review_version=request.review_version,
        safe_reviews=tuple(safe),
        quarantined_reviews=tuple(quarantined),
        pii_mask_count=pii_count,
        decision=decision,
        degraded=bool(quarantined),
    )
