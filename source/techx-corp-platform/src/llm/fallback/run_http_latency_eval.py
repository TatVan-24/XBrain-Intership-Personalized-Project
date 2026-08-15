from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path


URL = "http://127.0.0.1:8010/v1/summaries"
WARMUP_REQUESTS = 3
MEASURED_REQUESTS = 30
TIMEOUT_SECONDS = 15
P95_TARGET_MS = 1500.0

OUTPUT_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "eval"
    / "t5-small-http-latency-results.json"
)

PAYLOAD = {
    "product_id": "P123",
    "review_version": "v1",
    "reviews": [
        {
            "review_id": "r1",
            "score": 5.0,
            "text": (
                "Image quality is sharp and setup is straightforward."
            ),
        },
        {
            "review_id": "r2",
            "score": 3.0,
            "text": "Documentation needs improvement.",
        },
    ],
}


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("Cannot calculate percentile of empty values")

    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return round(ordered[index], 2)


def send_request(sequence: int) -> dict:
    body = json.dumps(PAYLOAD).encode("utf-8")

    request = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": f"latency-eval-{sequence:03d}",
        },
    )

    started = time.perf_counter()

    try:
        with urllib.request.urlopen(
            request,
            timeout=TIMEOUT_SECONDS,
        ) as response:
            response_body = response.read().decode("utf-8")
            http_status = response.status
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8")
        http_status = error.code

    client_latency_ms = (
        time.perf_counter() - started
    ) * 1000

    data = json.loads(response_body)

    return {
        "sequence": sequence,
        "http_status": http_status,
        "client_latency_ms": round(client_latency_ms, 2),
        "server_latency_ms": float(data.get("latency_ms", 0.0)),
        "status": data.get("status"),
        "summary_is_null": data.get("summary") is None,
        "validation_codes": data.get("validation_codes", []),
        "model_version": data.get("model_version"),
    }


def main() -> int:
    warmups = []

    for index in range(1, WARMUP_REQUESTS + 1):
        result = send_request(index)
        warmups.append(result)

        print(
            f"warmup {index}/{WARMUP_REQUESTS}: "
            f"server={result['server_latency_ms']}ms "
            f"client={result['client_latency_ms']}ms"
        )

    measured = []

    for index in range(1, MEASURED_REQUESTS + 1):
        sequence = WARMUP_REQUESTS + index
        result = send_request(sequence)
        measured.append(result)

        print(
            f"measured {index}/{MEASURED_REQUESTS}: "
            f"server={result['server_latency_ms']}ms "
            f"client={result['client_latency_ms']}ms "
            f"status={result['status']}"
        )

    server_latencies = [
        item["server_latency_ms"]
        for item in measured
    ]

    client_latencies = [
        item["client_latency_ms"]
        for item in measured
    ]

    http_counts = Counter(
        str(item["http_status"])
        for item in measured
    )

    status_counts = Counter(
        str(item["status"])
        for item in measured
    )

    validation_counts = Counter(
        code
        for item in measured
        for code in item["validation_codes"]
    )

    unsafe_summary_returned_count = sum(
        1
        for item in measured
        if item["status"] == "unavailable"
        and not item["summary_is_null"]
    )

    safety_passed = (
        http_counts == {"200": MEASURED_REQUESTS}
        and status_counts == {"unavailable": MEASURED_REQUESTS}
        and validation_counts["MODEL_FORMAT_LEAK"]
        == MEASURED_REQUESTS
        and unsafe_summary_returned_count == 0
    )

    server_p95 = percentile(server_latencies, 0.95)
    latency_target_passed = server_p95 <= P95_TARGET_MS

    aggregate = {
        "warmup_request_count": WARMUP_REQUESTS,
        "measured_request_count": MEASURED_REQUESTS,
        "http_status_counts": dict(http_counts),
        "response_status_counts": dict(status_counts),
        "validation_code_counts": dict(validation_counts),
        "server_latency_ms": {
            "min": round(min(server_latencies), 2),
            "p50": percentile(server_latencies, 0.50),
            "p95": server_p95,
            "max": round(max(server_latencies), 2),
            "mean": round(
                sum(server_latencies) / len(server_latencies),
                2,
            ),
        },
        "client_latency_ms": {
            "min": round(min(client_latencies), 2),
            "p50": percentile(client_latencies, 0.50),
            "p95": percentile(client_latencies, 0.95),
            "max": round(max(client_latencies), 2),
            "mean": round(
                sum(client_latencies) / len(client_latencies),
                2,
            ),
        },
        "unsafe_summary_returned_count": (
            unsafe_summary_returned_count
        ),
        "safety_passed": safety_passed,
        "p95_target_ms": P95_TARGET_MS,
        "latency_target_passed": latency_target_passed,
    }

    report = {
        "schema_version": 1,
        "evaluation": "t5-small-base-http-warm-latency",
        "endpoint": URL,
        "aggregate": aggregate,
        "warmups": warmups,
        "results": measured,
    }

    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(aggregate, indent=2))
    print(f"Results written to: {OUTPUT_PATH}")

    if not safety_passed:
        return 1

    if not latency_target_passed:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())