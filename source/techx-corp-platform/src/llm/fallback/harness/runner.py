# gọi HTTP

"""Call the llm service HTTP endpoint with a case."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


DEFAULT_ENDPOINT = "http://localhost:8000/v1/chat/completions"


def build_messages(case: dict) -> list[dict]:
    """Convert a case into an OpenAI-compatible messages list
    matching the pattern product-reviews uses."""
    inp = case["input"]
    product_id = inp["product_id"]
    reviews = inp.get("reviews", [])
    surface = case["surface"]

    tool_payload = json.dumps({"reviews": reviews})
    messages = [
        {
            "role": "user",
            "content": f"Can you summarize the product reviews? product ID:{product_id}",
        },
        {"role": "tool", "tool_call_id": "c1", "content": tool_payload},
    ]

    if surface == "qa":
        question = inp.get("question", "")
        messages.append({
            "role": "user",
            "content": (
                f"Based on the tool results, answer the original question "
                f"about product ID:{product_id}. Question: {question}"
            ),
        })
    else:  # summary
        messages.append({
            "role": "user",
            "content": (
                f"Based on the tool results, answer the original question "
                f"about product ID:{product_id}"
            ),
        })
    return messages


def run_case(
    case: dict,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: int = 30,
) -> dict:
    """Run one case. Returns dict with content/model/latency_ms/error."""
    body = json.dumps({
        "model": "techx-llm",
        "messages": build_messages(case),
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        content = payload["choices"][0]["message"]["content"]
        return {
            "content": content,
            "model": payload.get("model", "unknown"),
            "latency_ms": latency_ms,
            "error": None,
        }
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "content": "",
            "model": "unknown",
            "latency_ms": latency_ms,
            "error": str(e),
        }