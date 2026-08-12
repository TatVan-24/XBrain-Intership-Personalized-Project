"""HTTP inference service for the local T5 fallback model."""

from __future__ import annotations

import json
import os
import time
from threading import Lock

from flask import Flask, jsonify, request

from contracts import SummaryRequest, SummaryResponse, validate_summary
from prepare_dataset import chunk_reviews, sanitize

app = Flask(__name__)
MODEL_PATH = os.getenv("FALLBACK_MODEL_PATH", "./fallback/artifacts/t5-small-review-summary")
MODEL_VERSION = os.getenv("FALLBACK_MODEL_VERSION", "t5-small-review-summary-dev")
MAX_INPUT_TOKENS = int(os.getenv("FALLBACK_MAX_INPUT_TOKENS", "256"))
MAX_OUTPUT_TOKENS = int(os.getenv("FALLBACK_MAX_OUTPUT_TOKENS", "96"))
_model = _tokenizer = _device = None
_load_error = None
_load_lock = Lock()


def load_model() -> None:
    global _model, _tokenizer, _device, _load_error
    if _model is not None or _load_error is not None:
        return
    with _load_lock:
        if _model is not None or _load_error is not None:
            return
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
            with open(os.path.join(MODEL_PATH, "training_manifest.json"), encoding="utf-8") as file:
                base_model = json.load(file)["base_model"]
            base = AutoModelForSeq2SeqLM.from_pretrained(base_model)
            _model = PeftModel.from_pretrained(base, MODEL_PATH)
            _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _model.to(_device).eval()
        except Exception as error:
            _load_error = type(error).__name__


@app.get("/health/live")
def live():
    return jsonify({"status": "ok"})


@app.get("/health/ready")
def ready():
    load_model()
    if _model is None:
        return jsonify({"status": "not_ready", "reason": _load_error}), 503
    return jsonify({"status": "ready", "model_version": MODEL_VERSION})


@app.post("/v1/summaries")
def summarize():
    started = time.perf_counter()
    try:
        payload = SummaryRequest.from_dict(request.get_json(force=True))
        load_model()
        if _model is None:
            return jsonify({"error": "fallback_model_unavailable", "reason": _load_error}), 503
        reviews = [{"text": sanitize(item.text), "score": item.score} for item in payload.reviews]
        chunks = chunk_reviews(reviews, max_words=220)
        if not chunks:
            return jsonify({"error": "no_safe_reviews"}), 422
        # Online fallback stays bounded. A background precompute job can process all chunks.
        model_input = f"summarize product reviews: {chunks[0]}"
        encoded = _tokenizer(model_input, return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS).to(_device)
        output = _model.generate(**encoded, max_new_tokens=MAX_OUTPUT_TOKENS, num_beams=2, do_sample=False)
        summary = validate_summary(_tokenizer.decode(output[0], skip_special_tokens=True))
        response = SummaryResponse(
            summary=summary,
            source_review_ids=tuple(item.review_id for item in payload.reviews),
            model_source="t5-small",
            model_version=MODEL_VERSION,
            review_version=payload.review_version,
        ).to_dict()
        response["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return jsonify(response)
    except ValueError as error:
        return jsonify({"error": "invalid_request_or_output", "detail": str(error)}), 422


if __name__ == "__main__":
    load_model()
    app.run(host="0.0.0.0", port=int(os.getenv("FALLBACK_MODEL_PORT", "8010")))
