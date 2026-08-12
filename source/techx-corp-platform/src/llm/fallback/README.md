# T5-small review-summary fallback

This module is the local degraded path for review summaries, not a second
general-purpose assistant. Bedrock remains primary. The adapter is used only
after a bounded provider failure or rejected primary output.

## Contract

`POST /v1/summaries` accepts a product ID, immutable `review_version`, and
reviews with IDs, text, and optional scores. It returns the summary,
`model_source=t5-small`, `degraded=true`, model/review versions, source review
IDs, and inference latency. Invalid model output is rejected; the future
router must then use deterministic statistics or honestly abstain.

## Prepare labeled data

Raw JSONL has one product per line. Reference summaries must be human-written
or human-approved. Preparation masks common PII, excludes obvious injection,
chunks long inputs, and keeps a product wholly within one stable split.

From `src/llm`:

```powershell
python -m fallback.prepare_dataset `
  --input fallback/data/raw/sample.jsonl `
  --output fallback/data/processed
```

The sample only tests the pipeline; it is not sufficient training data.

## Fine-tune on a GTX 1650-class laptop

Install a CUDA-compatible PyTorch build, then `requirements-train.txt`. The
defaults use T5-small, LoRA rank 8, batch size 1, gradient accumulation 16,
256 input tokens, 96 target tokens, FP16 with CUDA, and gradient checkpointing.

```powershell
python -m fallback.train `
  --data-dir fallback/data/processed `
  --output-dir fallback/artifacts/t5-small-review-summary
```

Start the warm inference process from `src/llm`:

```powershell
python fallback/serve.py
```

## Routing state machine (next integration)

```text
reviews -> safety filter -> Bedrock (bounded timeout/retry)
  -> valid and grounded: return primary
  -> rejected/provider failure: T5 fallback
       -> valid and grounded: return degraded
       -> rejected/unavailable: deterministic summary or honest abstention
```

## Gates before enabling fallback

- Product-isolated labeled data with provenance.
- Faithfulness, sentiment, PII, and injection evaluation.
- CPU/GPU p50 and p95 latency plus peak memory.
- Versioned adapter that beats the unfine-tuned T5-small baseline.
- No raw PII in output, logs, or model artifacts.
- Forced primary failure never produces HTTP 500 at the product surface.
