#!/usr/bin/python
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""LLM service.

Runtime flow for review summaries:
  messages (with tool results)
    -> Layer 1 input guardrails (quarantine/PII mask)
    -> Layer 2 prompt builder (trusted vs untrusted roles)
    -> Groq primary (failover across free models)
    -> Layer 4 output guardrails (schema/PII/leak)
    -> if all fail -> mock JSON fallback

Mock responses are kept for /v1/chat/completions tool handshake and
as the safety net when Groq cannot be reached.
"""

from flask import Flask, request, jsonify
import json
import time
import re
import os
import sys
import logging
import urllib.request
import urllib.error

# --- Fallback modules (guardrails, prompt builder, output guardrails) ---
_FALLBACK_DIR = os.path.join(os.path.dirname(__file__), "fallback")
if os.path.isdir(_FALLBACK_DIR):
    sys.path.insert(0, _FALLBACK_DIR)

try:
    from guardrails import inspect_request  # Layer 1
    from prompt_builder import build_prompt, PromptBuildError  # Layer 2
    from output_guardrails import (  # Layer 4
        Layer4Input,
        Review as GuardrailReview,
        validate_candidate,
    )
    _GUARDRAILS_AVAILABLE = True
except ImportError as _e:
    _GUARDRAILS_AVAILABLE = False
    _GUARDRAILS_IMPORT_ERROR = str(_e)

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

product_review_summaries = {}
product_review_summaries_file_path = "./product-review-summaries.json"

inaccurate_product_review_summaries = {}
inaccurate_product_review_summaries_file_path = "./inaccurate-product-review-summaries.json"

def load_product_review_summaries(file_path):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
            summaries = data.get("product-review-summaries", [])
            result = {}
            for product in summaries:
                product_id = product.get("product_id")
                if product_id:
                    result[product_id] = product.get("product_review_summary")
            return result
    except FileNotFoundError:
        app.logger.error(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        app.logger.error(f"Error: Failed to decode JSON from '{file_path}'.")
    except Exception as e:
        app.logger.error(f"Unexpected error loading summaries: {e}")
    return {}


GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "10"))

GROQ_FREE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

class GroqCallError(Exception):
    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.reason = reason
        self.status = status

def _call_groq_once(model, messages):
    """Single attempt. Returns (content, model_id). Raises GroqCallError."""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GROQ_BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "techx-llm/1.0", 
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=GROQ_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GroqCallError(f"http_{e.code}", status=e.code)
    except urllib.error.URLError as e:
        raise GroqCallError(f"network_{e.reason}")
    except TimeoutError:
        raise GroqCallError("timeout")
    except json.JSONDecodeError:
        raise GroqCallError("bad_json")

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise GroqCallError("bad_response_shape")

    return content, payload.get("model", model)

def call_groq_chain(messages):
    """Try each model in priority order. Returns (content, model_id, attempts)."""
    if not GROQ_API_KEY:
        raise GroqCallError("missing_api_key")

    attempts = []
    last_error = None
    for model in GROQ_FREE_MODELS:
        try:
            content, model_id = _call_groq_once(model, messages)
            attempts.append(f"{model}:ok")
            return content, model_id, attempts
        except GroqCallError as err:
            # 429 / 404 / 5xx / timeout / network -> try next model
            attempts.append(f"{model}:{err.reason}")
            last_error = err

    raise GroqCallError(
        f"all_models_failed:{last_error.reason if last_error else 'unknown'}",
        status=last_error.status if last_error else None,
    )

def extract_reviews_from_messages(messages):
    """Extract reviews from tool-role messages. Returns list or None."""
    reviews = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        try:
            data = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            continue

        items = None
        if isinstance(data, dict):
            for key in ("reviews", "data", "results"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
        elif isinstance(data, list):
            items = data

        if not items:
            continue

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("description") or item.get("comment")
            if not text:
                continue
            reviews.append({
                "review_id": str(item.get("review_id") or item.get("id") or f"r{i}"),
                "text": str(text),
                "score": item.get("score"),
            })
    return reviews if reviews else None

def extract_summary_from_llm_output(content):
    """
    Groq may return:
      - Valid JSON: {"status":"completed","summary":"...","source_review_ids":[...]}
      - Valid JSON with unavailable
      - JSON wrapped in markdown fence
      - Plain text (LLM ignored JSON instruction)
    Returns: summary string, None (unavailable), or raw text (unexpected).
    """
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed, dict):
        status = parsed.get("status")
        if status == "unavailable":
            return None
        if status == "completed":
            summary = parsed.get("summary")
            if isinstance(summary, str):
                return summary.strip()
    return text

def parse_product_id(last_message):
    m = re.search(r"product ID:([A-Z0-9]+)", last_message)
    if m:
        return m.group(1).strip()
    m = re.search(r"product ID, but make the answer inaccurate:([A-Z0-9]+)", last_message)
    if m:
        return m.group(1).strip()
    raise ValueError("product ID not found in input message")

def generate_mock_response(product_id):
    inaccurate = check_feature_flag("llmInaccurateResponse")
    if inaccurate and product_id == "L9ECAV7KIM":
        return inaccurate_product_review_summaries.get(product_id)
    return product_review_summaries.get(product_id)

def generate_summary_via_groq(product_id, messages):
    """
    Returns:
      {"status":"completed","summary":..,"model":..,"source_review_ids":[..]}
      {"status":"unavailable","reason":..,"model":..}
      None -> caller should fall back to mock
    """
    if not _GUARDRAILS_AVAILABLE:
        app.logger.warning(f"guardrails unavailable: {_GUARDRAILS_IMPORT_ERROR}")
        return None

    reviews = extract_reviews_from_messages(messages)
    if not reviews:
        app.logger.info("no reviews in tool messages -> mock fallback")
        return None

    # Layer 1 — input guardrails
    try:
        layer1 = inspect_request({
            "product_id": product_id,
            "review_version": f"m6-{int(time.time())}",
            "reviews": reviews,
        })
    except ValueError as e:
        app.logger.warning(f"layer1_invalid: {e}")
        return {"status": "unavailable", "reason": "input_invalid", "model": "guardrail"}

    if layer1.decision != "continue":
        app.logger.info("layer1_abstain: all reviews quarantined")
        return {"status": "unavailable", "reason": "all_reviews_quarantined", "model": "guardrail"}

    # Layer 2 — prompt builder
    try:
        prompt_pkg = build_prompt(
            request_id=f"req-{int(time.time() * 1000)}",
            guardrail_result=layer1,
            current_review_version=layer1.review_version,
        )
    except PromptBuildError as e:
        app.logger.warning(f"layer2_failed: {e.reason_code}")
        return {"status": "unavailable", "reason": e.reason_code, "model": "guardrail"}

    openai_messages = [{"role": m.role, "content": m.content} for m in prompt_pkg.messages]

    # Groq with model failover
    try:
        content, model_id, attempts = call_groq_chain(openai_messages)
        app.logger.info(f"groq_attempts: {attempts} winner: {model_id}")
    except GroqCallError as e:
        app.logger.warning(f"groq_all_failed: {e.reason}")
        return None

    # Parse LLM JSON if present
    summary_text = extract_summary_from_llm_output(content)
    if summary_text is None:
        return {"status": "unavailable", "reason": "llm_abstained", "model": model_id}
    if not summary_text.strip():
        return None
    content = summary_text

    # Layer 4 — output guardrails
    guardrail_reviews = tuple(
        GuardrailReview(review_id=r.review_id, text=r.sanitized_text, score=r.score)
        for r in layer1.safe_reviews
    )
    validation = validate_candidate(
        Layer4Input(
            request_id=prompt_pkg.request_id,
            product_id=product_id,
            review_version=layer1.review_version,
            candidate_role="primary",
            model=model_id,
            summary=content,
            source_review_ids=prompt_pkg.source_review_ids,
            reviews=guardrail_reviews,
            degraded=layer1.degraded,
        )
    )

    if validation.decision == "reject":
        app.logger.warning(f"layer4_reject: {validation.violations}")
        return None

    return {
        "status": "completed",
        "summary": content,
        "model": model_id,
        "source_review_ids": list(prompt_pkg.source_review_ids),
        "degraded": layer1.degraded,
    }


# ---------- Response builders ----------
def build_response(model, messages, response_text, model_name=None):
    response = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name or model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response_text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": sum(len(str(m.get("content", "")).split()) for m in messages),
            "completion_tokens": len(str(response_text).split()),
            "total_tokens": sum(len(str(m.get("content", "")).split()) for m in messages) + len(str(response_text).split()),
        },
    }
    return jsonify(response)

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    data = request.json or {}
    messages = data.get("messages", [])
    model = data.get("model", "techx-llm")
    tools = data.get("tools", None)

    if not messages:
        return jsonify({"error": "no messages"}), 400

    app.logger.info(f"request with {len(messages)} messages, model={model}, tools={'yes' if tools else 'no'}")
    last_message = str(messages[-1].get("content", ""))

    # Fixed responses (same as mock)
    if "What age(s) is this recommended for?" in last_message:
        return build_response(model, messages, "This product is recommended for ages 7 and above.")
    if "Were there any negative reviews?" in last_message:
        return build_response(model, messages, "No, there were no reviews less than three stars for this product.")
    if not ("Can you summarize the product reviews?" in last_message
            or "Based on the tool results, answer the original question about product ID" in last_message):
        return build_response(model, messages, "Sorry, I'm not able to answer that question.")

    product_id = parse_product_id(last_message)

    # Tool-calling handshake (unchanged from mock)
    if tools is not None:
        tool_args = f"{{\"product_id\": \"{product_id}\"}}"
        if model.endswith("rate-limit"):
            return jsonify({"error": {"message": "Rate limit reached."}}), 429
        return jsonify({
            "id": f"chatcmpl-mock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "requesting a tool call",
                    "tool_calls": [{
                        "id": "call",
                        "type": "function",
                        "function": {"name": "fetch_product_reviews", "arguments": tool_args},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {
                "prompt_tokens": sum(len(str(m.get("content", "")).split()) for m in messages),
                "completion_tokens": 0,
                "total_tokens": sum(len(str(m.get("content", "")).split()) for m in messages),
            },
        })

    # Summary path with Groq
    groq_result = generate_summary_via_groq(product_id, messages)

    if groq_result and groq_result["status"] == "completed":
        return build_response(model, messages, groq_result["summary"], model_name=groq_result["model"])

    if groq_result and groq_result["status"] == "unavailable":
        reason = groq_result.get("reason")
        if reason in ("all_reviews_quarantined", "input_invalid"):
            # Honest abstain visible to caller
            return build_response(model, messages,
                "I don't have enough information to summarize this product.",
                model_name=groq_result.get("model", "guardrail"))
        # e.g. llm_abstained -> treat as fall-through to mock
        # (keep product page usable)

    # Mock fallback
    response_text = generate_mock_response(product_id) or "Summary temporarily unavailable."
    return build_response(model, messages, response_text, model_name="mock-fallback")


@app.route("/v1/models", methods=["GET"])
def list_models():
    return jsonify({
        "object": "list",
        "data": [
            {"id": "techx-llm", "object": "model", "created": int(time.time()), "owned_by": "techx-shop"},
        ],
    })


def check_feature_flag(flag_name):
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)


if __name__ == "__main__":
    api.set_provider(FlagdProvider(
        host=os.environ.get("FLAGD_HOST", "flagd"),
        port=os.environ.get("FLAGD_PORT", 8013),
    ))
    product_review_summaries = load_product_review_summaries(product_review_summaries_file_path)
    inaccurate_product_review_summaries = load_product_review_summaries(inaccurate_product_review_summaries_file_path)

    print(f"LLM server starting — Groq enabled: {bool(GROQ_API_KEY)}")
    print(f"Guardrails available: {_GUARDRAILS_AVAILABLE}")
    if _GUARDRAILS_AVAILABLE:
        print(f"Groq models (priority order): {GROQ_FREE_MODELS}")

    app.run(host="0.0.0.0", port=8000, debug=False)




def generate_response(product_id):

    """Generate a response by providing the pre-generated summary for the specified product"""
    product_review_summary = None

    llm_inaccurate_response = check_feature_flag("llmInaccurateResponse")
    app.logger.info(f"llmInaccurateResponse feature flag: {llm_inaccurate_response}")
    if llm_inaccurate_response and product_id == "L9ECAV7KIM":
        app.logger.info(f"Returning an inaccurate response for product_id: {product_id}")
        product_review_summary = inaccurate_product_review_summaries.get(product_id)
    else:
        product_review_summary = product_review_summaries.get(product_id)

    app.logger.info(f"product_review_summary is: {product_review_summary}")

    return product_review_summary

def parse_product_id(last_message):
    match = re.search(r"product ID:([A-Z0-9]+)", last_message)
    if match:
        return match.group(1).strip()

    match = re.search(r"product ID, but make the answer inaccurate:([A-Z0-9]+)", last_message)
    if match:
        return match.group(1).strip()

    raise ValueError("product ID not found in input message")

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    data = request.json
    messages = data.get('messages', [])
    stream = data.get('stream', False)
    model = data.get('model', 'techx-llm')
    tools = data.get('tools', None)

    app.logger.info(f"Received a chat completion request: '{messages}'")

    last_message = messages[-1]["content"]

    app.logger.info(f"last_message is: '{last_message}'")

    if 'What age(s) is this recommended for?' in last_message:
        response_text = 'This product is recommended for ages 7 and above.'
        return build_response(model, messages, response_text)
    elif 'Were there any negative reviews?' in last_message:
        response_text = 'No, there were no reviews less than three stars for this product.'
        return build_response(model, messages, response_text)
    elif not ('Can you summarize the product reviews?' in last_message or 'Based on the tool results, answer the original question about product ID' in last_message):
        response_text = 'Sorry, I\'m not able to answer that question.'
        return build_response(model, messages, response_text)

    # otherwise, process the product review summary
    product_id = parse_product_id(last_message)

    if tools is not None:

        tool_args = f"{{\"product_id\": \"{product_id}\"}}"

        app.logger.info(f"Processing a tool call with args: '{tool_args}'")

        app.logger.info(f"The model is: {model}")
        if model.endswith("rate-limit"):
            app.logger.info(f"Returning a rate limit error")
            response = {
                "error": {
                    "message": "Rate limit reached. Please try again later.",
                    "type": "rate_limit_exceeded",
                    "param": "null",
                    "code": "null"
                }
            }
            return jsonify(response), 429
        else:
            # Non-streaming response
            response = {
                "id": f"chatcmpl-mock-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "requesting a tool call",
                        "tool_calls": [{
                            "id": "call",
                            "type": "function",
                            "function": {
                                "name": "fetch_product_reviews",
                                "arguments": tool_args
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {
                    "prompt_tokens": sum(len(m.get("content", "").split()) for m in messages),
                    "completion_tokens": "0",
                    "total_tokens": sum(len(m.get("content", "").split()) for m in messages)
                }
            }
            return jsonify(response)

    else:
        # Generate the response
        response_text = generate_response(product_id)

        return build_response(model, messages, response_text)

def build_response(model, messages, response_text):
    app.logger.info(f"Processing a response: '{response_text}'")

    response = {
        "id": f"chatcmpl-mock-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": sum(len(m.get("content", "").split()) for m in messages),
            "completion_tokens": len(response_text.split()),
            "total_tokens": sum(len(m.get("content", "").split()) for m in messages) + len(response_text.split())
        }
    }
    return jsonify(response)

@app.route('/v1/models', methods=['GET'])
def list_models():
    """List available models"""
    return jsonify({
        "object": "list",
        "data": [
            {
                "id": "techx-llm",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "techx-shop"
            }
        ]
    })

def check_feature_flag(flag_name: str):
    # Initialize OpenFeature
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)

if __name__ == '__main__':

    api.set_provider(FlagdProvider(host=os.environ.get('FLAGD_HOST', 'flagd'), port=os.environ.get('FLAGD_PORT', 8013)))
    product_review_summaries = load_product_review_summaries(product_review_summaries_file_path)
    inaccurate_product_review_summaries = load_product_review_summaries(inaccurate_product_review_summaries_file_path)

    app.logger.info(product_review_summaries)

    print("OpenAI API server starting on http://localhost:8000")
    print("Set your OpenAI base URL to: http://localhost:8000/v1")
    app.run(host='0.0.0.0', port=8000, debug=True)