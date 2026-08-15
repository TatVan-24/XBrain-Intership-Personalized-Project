"""HTTP inference service for the local T5 fallback model."""

from __future__ import annotations

import json
import os
import time
from threading import Lock

from flask import Flask, jsonify, request

try:
    from .contracts import SummaryRequest, SummaryResponse
    from .output_guardrails import (
        Layer4Input,
        Review as GuardrailReview,
        validate_candidate,
    )
    from .prepare_dataset import chunk_reviews, sanitize
except ImportError:
    from contracts import SummaryRequest, SummaryResponse
    from output_guardrails import (
        Layer4Input,
        Review as GuardrailReview,
        validate_candidate,
    )
    from prepare_dataset import chunk_reviews, sanitize

from dataclasses import dataclass
from typing import Mapping

app = Flask(__name__)

DEFAULT_BASE_MODEL_PATH = "google-t5/t5-small"
DEFAULT_PEFT_MODEL_PATH = (
    "./fallback/artifacts/t5-small-review-summary"
)


class ModelConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ModelConfig:
    model_type: str
    model_path: str
    model_version: str


def read_model_config(
    environ: Mapping[str, str] | None = None,
) -> ModelConfig:
    source = os.environ if environ is None else environ

    model_type = source.get(
        "FALLBACK_MODEL_TYPE",
        "peft",
    ).strip().lower()

    if model_type not in {"base", "peft"}:
        raise ModelConfigurationError(
            "FALLBACK_MODEL_TYPE must be base or peft"
        )

    default_path = (
        DEFAULT_BASE_MODEL_PATH
        if model_type == "base"
        else DEFAULT_PEFT_MODEL_PATH
    )

    default_version = (
        "google-t5-t5-small-untuned"
        if model_type == "base"
        else "t5-small-review-summary-dev"
    )

    model_path = source.get(
        "FALLBACK_MODEL_PATH",
        default_path,
    ).strip()

    model_version = source.get(
        "FALLBACK_MODEL_VERSION",
        default_version,
    ).strip()

    if not model_path:
        raise ModelConfigurationError(
            "FALLBACK_MODEL_PATH cannot be empty"
        )

    if not model_version:
        raise ModelConfigurationError(
            "FALLBACK_MODEL_VERSION cannot be empty"
        )

    return ModelConfig(
        model_type=model_type,
        model_path=model_path,
        model_version=model_version,
    )


MODEL_VERSION = os.getenv(
    "FALLBACK_MODEL_VERSION",
    "t5-small-review-summary-dev",
)

MAX_INPUT_TOKENS = int(os.getenv("FALLBACK_MAX_INPUT_TOKENS", "256"))
MAX_OUTPUT_TOKENS = int(os.getenv("FALLBACK_MAX_OUTPUT_TOKENS", "96"))
_model = _tokenizer = _device = _model_config = None
_load_error = None
_load_lock = Lock()


def load_model() -> None:
    global _model
    global _tokenizer
    global _device
    global _model_config
    global _load_error

    if _model is not None or _load_error is not None:
        return

    with _load_lock:
        if _model is not None or _load_error is not None:
            return

        try:
            import torch
            from transformers import (
                AutoModelForSeq2SeqLM,
                AutoTokenizer,
            )

            config = read_model_config()

            if config.model_type == "base":
                _tokenizer = AutoTokenizer.from_pretrained(
                    config.model_path
                )
                _model = AutoModelForSeq2SeqLM.from_pretrained(
                    config.model_path
                )

            elif config.model_type == "peft":
                from peft import PeftModel

                manifest_path = os.path.join(
                    config.model_path,
                    "training_manifest.json",
                )

                with open(
                    manifest_path,
                    encoding="utf-8",
                ) as file:
                    manifest = json.load(file)

                base_model = str(
                    manifest.get("base_model", "")
                ).strip()

                if not base_model:
                    raise ModelConfigurationError(
                        "training_manifest.json requires base_model"
                    )

                _tokenizer = AutoTokenizer.from_pretrained(
                    config.model_path
                )

                base = AutoModelForSeq2SeqLM.from_pretrained(
                    base_model
                )

                _model = PeftModel.from_pretrained(
                    base,
                    config.model_path,
                )

            _device = torch.device(
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

            _model.to(_device).eval()
            _model_config = config
            _load_error = None

        except Exception as error:
            _model = None
            _tokenizer = None
            _device = None
            _model_config = None
            _load_error = type(error).__name__

def generate_candidate(payload: SummaryRequest) -> str:
    reviews = [
        {
            "text": sanitize(item.text),
            "score": item.score,
        }
        for item in payload.reviews
    ]

    chunks = chunk_reviews(reviews, max_words=220)

    if not chunks:
        raise ValueError("NO_SAFE_REVIEWS")

    model_input = f"summarize product reviews: {chunks[0]}"

    encoded = _tokenizer(
        model_input,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_INPUT_TOKENS,
    ).to(_device)

    output = _model.generate(
        **encoded,
        max_new_tokens=MAX_OUTPUT_TOKENS,
        num_beams=2,
        do_sample=False,
    )

    return _tokenizer.decode(
        output[0],
        skip_special_tokens=True,
    )



@app.get("/health/live")
def live():
    return jsonify({"status": "ok"})


@app.get("/health/ready")
def ready():
    load_model()

    if _model is None:
        return jsonify(
            {
                "status": "not_ready",
                "reason": _load_error,
            }
        ), 503

    return jsonify(
        {
            "status": "ready",
            "model_type": _model_config.model_type,
            "model_version": _model_config.model_version,
            "device": str(_device),
        }
    )


@app.post("/v1/summaries")
def summarize():
    started = time.perf_counter()

    try:
        payload = SummaryRequest.from_dict(
            request.get_json(force=True)
        )
    except ValueError as error:
        return jsonify(
            {
                "error": "invalid_request",
                "detail": str(error),
            }
        ), 422

    load_model()

    if _model is None:
        return jsonify(
            {
                "error": "fallback_model_unavailable",
                "reason": _load_error,
            }
        ), 503

    active_model_version = (
        _model_config.model_version
        if _model_config is not None
        else MODEL_VERSION
    )

    try:
        candidate = generate_candidate(payload)
    except ValueError as error:
        if str(error) == "NO_SAFE_REVIEWS":
            response = SummaryResponse(
                status="unavailable",
                summary=None,
                source_review_ids=(),
                model_source="t5-small",
                model_version=active_model_version,
                review_version=payload.review_version,
                degraded=True,
                validation_codes=("NO_SAFE_REVIEWS",),
            ).to_dict()

            response["latency_ms"] = round(
                (time.perf_counter() - started) * 1000,
                2,
            )

            return jsonify(response), 200

        return jsonify(
            {"error": "fallback_inference_failed"}
        ), 503
    except Exception:
        # Không trả raw exception vì có thể làm lộ thông tin runtime.
        return jsonify(
            {"error": "fallback_inference_failed"}
        ), 503

    guardrail_reviews = tuple(
        GuardrailReview(
            review_id=item.review_id,
            text=sanitize(item.text),
            score=item.score,
        )
        for item in payload.reviews
    )

    validation = validate_candidate(
        Layer4Input(
            request_id=(
                request.headers.get("X-Request-ID")
                or f"fallback-{time.time_ns()}"
            ),
            product_id=payload.product_id,
            review_version=payload.review_version,
            candidate_role="fallback",
            model=active_model_version,
            summary=candidate,
            source_review_ids=tuple(
                item.review_id for item in payload.reviews
            ),
            reviews=guardrail_reviews,
            degraded=True,
        )
    )

    if validation.decision == "reject":
        response = SummaryResponse(
            status="unavailable",
            summary=None,
            source_review_ids=(),
            model_source="t5-small",
            model_version=active_model_version,
            review_version=payload.review_version,
            degraded=True,
            validation_codes=validation.violations,
        ).to_dict()
    else:
        response = SummaryResponse(
            status="completed",
            summary=validation.response["summary"],
            source_review_ids=tuple(
                item.review_id for item in payload.reviews
            ),
            model_source="t5-small",
            model_version=active_model_version,
            review_version=payload.review_version,
            degraded=True,
            validation_codes=(),
        ).to_dict()

    response["latency_ms"] = round(
        (time.perf_counter() - started) * 1000,
        2,
    )


    return jsonify(response), 200


if __name__ == "__main__":
    load_model()
    app.run(host="0.0.0.0", port=int(os.getenv("FALLBACK_MODEL_PORT", "8010")))
