"""NLI evaluator — load model per case (MVP tradeoff)."""
from __future__ import annotations

import os

MODEL_NAME = os.environ.get(
    "NLI_MODEL_NAME",
    "cross-encoder/nli-deberta-v3-small",
)

# Map NLI output labels to harness verdicts
LABEL_TO_VERDICT = {
    "entailment": "supported",
    "contradiction": "contradicted",
    "neutral": "unsupported",
}


def evaluate_case(evidence: str, claim: str) -> dict:
    """Load NLI, run one inference, free model. Return raw output + verdict.

    WARNING: loading model per call is slow (~3-5s). Acceptable for MVP
    because RAM is prioritized over latency.
    """
    from transformers import pipeline

    # Load fresh each call — MVP tradeoff per CONTRACT.md
    clf = pipeline("text-classification", model=MODEL_NAME, device=-1)

    # top_k=None returns probabilities for all labels
    result = clf({"text": evidence, "text_pair": claim}, top_k=None)

    # result = [{"label": "entailment", "score": 0.98}, ...]
    probs = {item["label"]: float(item["score"]) for item in result}

    # Top-1 by score = model's choice
    top1 = max(result, key=lambda x: x["score"])
    raw_label = top1["label"]
    verdict = LABEL_TO_VERDICT.get(raw_label, "unknown")

    # Free the model from memory
    del clf

    return {
        "raw_label": raw_label,
        "verdict": verdict,
        "probabilities": {
            "entailment": probs.get("entailment", 0.0),
            "neutral": probs.get("neutral", 0.0),
            "contradiction": probs.get("contradiction", 0.0),
        },
    }