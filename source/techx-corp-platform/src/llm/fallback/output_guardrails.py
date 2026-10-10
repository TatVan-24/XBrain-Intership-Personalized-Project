from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Literal


MIN_WORDS = 3
MAX_WORDS = 160
MIN_QUOTE_WORDS = 6
EXCESSIVE_COPY_RATIO = 0.70


EMAIL = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE = re.compile(
    r"(?<!\w)(?:\+?\d[\d().\s-]{7,}\d)(?!\w)"
)

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

FORMAT_LEAK_PATTERNS = (
    re.compile(r"\b(?:rating|review|score)\s*=", re.IGNORECASE),
    re.compile(r"</?\s*(?:untrusted_reviews|response_schema)\s*>", re.IGNORECASE),
    re.compile(
        r"\s+\|\s+(?=(?:rating|review|score)\s*=)",
        re.IGNORECASE,
    ),
)

PROMPT_LEAK_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\breveal\s+(?:the\s+)?system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\btrusted_policy\b", re.IGNORECASE),
    re.compile(r"\btrusted_instruction\b", re.IGNORECASE),
    re.compile(r"\bsecurity rules\s*:", re.IGNORECASE),
)


# STOPWORDS = frozenset({
#     "the","a","an","is","are","was","were","be","been","being","have","has","had",
#     "do","does","did","will","would","could","should","may","might","must","can",
#     "this","that","these","those","i","you","he","she","it","we","they","what",
#     "which","who","whom","whose","where","when","why","how","of","in","on","at",
#     "to","for","with","from","by","about","as","into","through","during","before",
#     "after","above","below","up","down","out","off","over","under","again","further",
#     "then","once","here","there","all","any","both","each","few","more","most",
#     "other","some","such","no","nor","not","only","own","same","so","than","too",
#     "very","just","now","product","products","review","reviews","user","users",
# })

# ABSTAIN_MARKERS = (
#     "no information", "don't have", "do not have", "unable to answer",
#     "cannot answer", "can't answer", "not mentioned", "insufficient",
# )


# def extract_question_keywords(question: str, min_length: int = 4) -> set[str]:
#     tokens = re.findall(r"\b[a-z0-9]+\b", question.lower())
#     return {t for t in tokens if len(t) >= min_length and t not in STOPWORDS}


# def check_qa_adherence(answer: str, question: str) -> tuple[bool, tuple[str, ...]]:
#     """QA output is adherent if it either abstains or contains at least one
#     question keyword. Non-adherent = output ignores the question."""
#     text = normalize_text(answer).lower()

#     if any(m in text for m in ABSTAIN_MARKERS):
#         return True, ()

#     q_kw = extract_question_keywords(question)
#     if not q_kw:
#         return True, ()  # cannot determine -> don't reject

#     text_tokens = set(re.findall(r"\b[a-z0-9]+\b", text))
#     if q_kw & text_tokens:
#         return True, ()

#     return False, ("QA_NOT_ADHERENT",)

@dataclass(frozen=True)
class Review:
    review_id: str
    text: str
    score: float | None = None


@dataclass(frozen=True)
class Layer4Input:
    request_id: str
    product_id: str
    review_version: str
    candidate_role: Literal["primary", "fallback"]
    model: str
    summary: str
    source_review_ids: tuple[str, ...]
    reviews: tuple[Review, ...]
    degraded: bool = False
    task_type: Literal["summary", "qa"] = "summary"
    question: str = "" 


@dataclass(frozen=True)
class ExactQuoteMatch:
    review_id: str
    quote: str
    word_count: int


@dataclass(frozen=True)
class Layer4Result:
    decision: Literal["allow", "reject"]
    next_action: Literal["return_response", "fallback", "abstain"]
    violations: tuple[str, ...]
    warnings: tuple[str, ...]
    exact_quote_matches: tuple[ExactQuoteMatch, ...]
    response: dict | None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["exact_quote_matches"] = [
            asdict(item) for item in self.exact_quote_matches
        ]
        return result


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", value).strip()


def normalize_for_match(value: str) -> str:
    value = normalize_text(value).casefold()
    value = re.sub(r"[^\w\s'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def find_exact_quotes(
    summary: str,
    reviews: tuple[Review, ...],
    minimum_words: int = MIN_QUOTE_WORDS,
) -> tuple[ExactQuoteMatch, ...]:
    summary_words = normalize_for_match(summary).split()
    matches: list[ExactQuoteMatch] = []

    if len(summary_words) < minimum_words:
        return ()

    for review in reviews:
        review_text = normalize_for_match(review.text)

        # Search longest summary span first.
        found: ExactQuoteMatch | None = None

        for size in range(len(summary_words), minimum_words - 1, -1):
            for start in range(0, len(summary_words) - size + 1):
                quote_words = summary_words[start : start + size]
                quote = " ".join(quote_words)

                if quote and quote in review_text:
                    found = ExactQuoteMatch(
                        review_id=review.review_id,
                        quote=quote,
                        word_count=size,
                    )
                    break

            if found:
                break

        if found:
            matches.append(found)

    return tuple(matches)


def copied_word_ratio(
    summary: str,
    matches: tuple[ExactQuoteMatch, ...],
) -> float:
    total_words = len(normalize_for_match(summary).split())

    if total_words == 0 or not matches:
        return 0.0

    # Diagnostic approximation, not a semantic grounding score.
    longest_match = max(match.word_count for match in matches)
    return min(longest_match / total_words, 1.0)


def validate_candidate(payload: Layer4Input) -> Layer4Result:
    summary = normalize_text(payload.summary)
    violations: list[str] = []
    warnings: list[str] = []

    if not payload.request_id.strip():
        violations.append("INVALID_REQUEST_ID")

    if not payload.product_id.strip():
        violations.append("INVALID_PRODUCT_ID")



    known_review_ids = {review.review_id for review in payload.reviews}
    supplied_review_ids = set(payload.source_review_ids)

    if not supplied_review_ids:
        violations.append("NO_SOURCE_REVIEW_IDS")
    elif not supplied_review_ids.issubset(known_review_ids):
        violations.append("UNKNOWN_SOURCE_REVIEW_ID")

    word_count = len(summary.split())

    if not summary:
        violations.append("EMPTY_SUMMARY")
    elif word_count < MIN_WORDS:
        violations.append("SUMMARY_TOO_SHORT")
    elif word_count > MAX_WORDS:
        violations.append("SUMMARY_TOO_LONG")

    if CONTROL_CHARS.search(summary):
        violations.append("CONTROL_CHARACTER_LEAK")

    if EMAIL.search(summary):
        violations.append("PII_EMAIL_LEAK")

    if PHONE.search(summary):
        violations.append("PII_PHONE_LEAK")

    if any(pattern.search(summary) for pattern in PROMPT_LEAK_PATTERNS):
        violations.append("PROMPT_INSTRUCTION_LEAK")

    if any(pattern.search(summary) for pattern in FORMAT_LEAK_PATTERNS):
        violations.append("MODEL_FORMAT_LEAK")

    exact_matches = find_exact_quotes(summary, payload.reviews)
    copy_ratio = copied_word_ratio(summary, exact_matches)

    if exact_matches:
        warnings.append("EXACT_QUOTE_DETECTED")

    if copy_ratio >= EXCESSIVE_COPY_RATIO:
        warnings.append("EXCESSIVE_EXTRACTIVE_COPY")

    # if payload.task_type == "qa" and payload.question.strip():
    #     adherent, qa_violations = check_qa_adherence(summary, payload.question)
    #     if not adherent:
    #         violations.extend(qa_violations)    

    if violations:
        next_action = (
            "fallback"
            if payload.candidate_role == "primary"
            else "abstain"
        )

        response = None

        if next_action == "abstain":
            response = {
                "status": "unavailable",
                "summary": None,
                "source_review_ids": [],
                "model": payload.model,
                "degraded": True,
            }

        return Layer4Result(
            decision="reject",
            next_action=next_action,
            violations=tuple(sorted(set(violations))),
            warnings=tuple(sorted(set(warnings))),
            exact_quote_matches=exact_matches,
            response=response,
        )

    response = {
        "status": "completed",
        "summary": summary,
        "source_review_ids": list(payload.source_review_ids),
        "model": payload.model,
        "degraded": payload.degraded,
    }

    return Layer4Result(
        decision="allow",
        next_action="return_response",
        violations=(),
        warnings=tuple(sorted(set(warnings))),
        exact_quote_matches=exact_matches,
        response=response,
    )