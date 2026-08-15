from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from contracts import validate_summary
from prepare_dataset import chunk_reviews


TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []

    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue

            case = json.loads(line)

            required = {
                "case_id",
                "product_id",
                "reviews",
                "reference_summary",
            }

            missing = required - case.keys()
            if missing:
                raise ValueError(
                    f"Line {line_number}: missing {sorted(missing)}"
                )

            cases.append(case)

    if not cases:
        raise ValueError("Baseline eval dataset is empty")

    return cases


def tokens(text: str) -> list[str]:
    return TOKEN.findall(str(text).lower())


def rouge1_f1(prediction: str, reference: str) -> float:
    predicted = Counter(tokens(prediction))
    expected = Counter(tokens(reference))

    overlap = sum((predicted & expected).values())
    predicted_count = sum(predicted.values())
    expected_count = sum(expected.values())

    if not predicted_count or not expected_count:
        return 0.0

    precision = overlap / predicted_count
    recall = overlap / expected_count

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


def lcs_length(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)

    for left_token in left:
        current = [0]

        for index, right_token in enumerate(right, start=1):
            if left_token == right_token:
                current.append(previous[index - 1] + 1)
            else:
                current.append(
                    max(previous[index], current[index - 1])
                )

        previous = current

    return previous[-1]


def rouge_l_f1(prediction: str, reference: str) -> float:
    predicted = tokens(prediction)
    expected = tokens(reference)

    if not predicted or not expected:
        return 0.0

    overlap = lcs_length(predicted, expected)
    precision = overlap / len(predicted)
    recall = overlap / len(expected)

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    index = max(
        0,
        math.ceil(value * len(ordered)) - 1,
    )
    return ordered[index]


def build_model_input(case: dict[str, Any]) -> str:
    chunks = chunk_reviews(
        case["reviews"],
        max_words=220,
    )

    if not chunks:
        raise ValueError("No usable review chunk")

    # Match the existing T5 training/serving contract.
    return f"summarize product reviews: {chunks[0]}"


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main() -> None:
    root = Path(__file__).parent

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "data" / "eval" / "pilot-cases.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            root
            / "data"
            / "eval"
            / "t5-small-baseline-results.json"
        ),
    )
    parser.add_argument(
        "--model",
        default="google-t5/t5-small",
    )
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=256,
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=96,
    )
    parser.add_argument(
        "--num-beams",
        type=int,
        default=2,
    )
    args = parser.parse_args()

    if args.max_input_tokens <= 0:
        raise SystemExit("max-input-tokens must be positive")

    if args.max_output_tokens <= 0:
        raise SystemExit("max-output-tokens must be positive")

    if args.num_beams <= 0:
        raise SystemExit("num-beams must be positive")

    torch.manual_seed(42)

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    cases = load_cases(args.input)

    load_started = time.perf_counter()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model)
    model.to(device)
    model.eval()

    model_load_ms = round(
        (time.perf_counter() - load_started) * 1000,
        2,
    )

    # Warm-up is deliberately excluded from per-case latency.
    warmup = tokenizer(
        "summarize product reviews: review=Works well.",
        return_tensors="pt",
        truncation=True,
        max_length=args.max_input_tokens,
    ).to(device)

    with torch.inference_mode():
        model.generate(
            **warmup,
            max_new_tokens=8,
            num_beams=args.num_beams,
            do_sample=False,
        )

    synchronize(device)

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    results = []
    latencies = []

    for case in cases:
        model_input = build_model_input(case)

        encoded = tokenizer(
            model_input,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_input_tokens,
        ).to(device)

        synchronize(device)
        started = time.perf_counter()

        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_output_tokens,
                num_beams=args.num_beams,
                do_sample=False,
            )

        synchronize(device)

        latency_ms = round(
            (time.perf_counter() - started) * 1000,
            2,
        )

        prediction = tokenizer.decode(
            generated[0],
            skip_special_tokens=True,
        ).strip()

        validation_error = None

        try:
            validate_summary(prediction)
            output_valid = True
        except ValueError as error:
            output_valid = False
            validation_error = str(error)

        reference = case["reference_summary"]

        result = {
            "case_id": case["case_id"],
            "product_id": case["product_id"],
            "prediction": prediction,
            "reference_summary": reference,
            "output_valid": output_valid,
            "validation_error": validation_error,
            "input_tokens": int(encoded["input_ids"].shape[1]),
            "output_tokens": int(generated.shape[1]),
            "latency_ms": latency_ms,
            "rouge1_f1": round(
                rouge1_f1(prediction, reference),
                4,
            ),
            "rouge_l_f1": round(
                rouge_l_f1(prediction, reference),
                4,
            ),
            # Must be filled by human review later.
            "human_status": "pending",
            "human_notes": None,
        }

        results.append(result)
        latencies.append(latency_ms)

        print(
            f"{case['case_id']}: "
            f"valid={output_valid}, "
            f"latency_ms={latency_ms}, "
            f"rougeL={result['rouge_l_f1']}"
        )

    valid_count = sum(
        result["output_valid"]
        for result in results
    )

    peak_vram_mb = None

    if device.type == "cuda":
        peak_vram_mb = round(
            torch.cuda.max_memory_allocated(device)
            / 1024
            / 1024,
            2,
        )

    aggregate = {
        "case_count": len(results),
        "generation_success_rate": round(
            len(results) / len(cases),
            4,
        ),
        "output_valid_rate": round(
            valid_count / len(results),
            4,
        ),
        "mean_rouge1_f1": round(
            statistics.mean(
                result["rouge1_f1"]
                for result in results
            ),
            4,
        ),
        "mean_rouge_l_f1": round(
            statistics.mean(
                result["rouge_l_f1"]
                for result in results
            ),
            4,
        ),
        "mean_latency_ms": round(
            statistics.mean(latencies),
            2,
        ),
        "p50_latency_ms": round(
            statistics.median(latencies),
            2,
        ),
        "p95_latency_ms": round(
            percentile(latencies, 0.95),
            2,
        ),
        "peak_vram_mb": peak_vram_mb,
    }

    report = {
        "schema_version": 1,
        "baseline_type": "untuned",
        "model": args.model,
        "device": str(device),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "model_load_ms": model_load_ms,
        "generation": {
            "max_input_tokens": args.max_input_tokens,
            "max_output_tokens": args.max_output_tokens,
            "num_beams": args.num_beams,
            "do_sample": False,
        },
        "aggregate": aggregate,
        "results": results,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(json.dumps(aggregate, indent=2))
    print(f"Results written to: {args.output}")


if __name__ == "__main__":
    main()