# M14 — Evaluation Harness Contract (As-Built)

Status: IMPLEMENTED  
Scope: AI evaluation and trust measurement for the product-reviews service  
Last update: 2026-10-13  
Related: M6 (AI runtime), M14 (evaluation standard)

---

## 1. Purpose

M6 demonstrates that the AI feature works with a real LLM, guardrails, and fallback behavior.

M14 takes the question further: does the system have a **standardized, reproducible evaluation harness that can accept external test cases**?

The difference between M6 and M14:

```text
M6:
  AI feature → self-written tests → pass/fail

M14:
  AI system → evaluation harness → external cases
            → standardized metrics → reproducible evidence
```

---

## 2. Core Problem

LLMs differ from deterministic functions. We cannot use `assert output == expected`.

We need a sufficiently robust framework that can:
- Accept external test cases without requiring code changes
- Score results using a well-founded method (not just keyword matching)
- Produce metrics per case, per category, and overall
- Reproduce results with a single command

---

## 3. Harness Architecture

```text
            CLI (__main__.py)
                  │
                  ▼
          Case Loader (loader.py)
                  │
             validate JSONL
                  │
                  ▼
          Evaluator (evaluator_nli.py)
              │          │
         evidence      claim
              │          │
              ▼          ▼
          NLI model (cross-encoder)
                  │
                  ▼
          Aggregator (report.py)
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
    per_case  per_category  overall
                  │
                  ▼
              results.json
```

Differences from the original plan:
- There is no HTTP Runner. Each test case contains its own `(evidence, claim)` pair, so there is no need to call an LLM to obtain a response.
- There are no multiple evaluators. Only the NLI evaluator is implemented.
- The Aggregator combines per-case, per-category, and overall results into one file.

---

## 4. Case Contract

The dataset is a **JSONL** file—each line is a JSON object. Do not read the entire file as a JSON array.

### 4.1. Format

```json
{
  "case_id": "nli-001",
  "category": "supported",
  "evidence": "Great entry-level telescope! Easy to set up and provides clear views.",
  "claim": "Easy to set up",
  "expected": "supported",
  "note": "optional"
}
```

### 4.2. Required Fields

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Unique ID within the file |
| `category` | string | Case group (used for aggregation) |
| `evidence` | string | Source text (the original review) |
| `claim` | string | The claim to be checked |
| `expected` | string | One of three values: `supported`, `contradicted`, or `unsupported` |

### 4.3. Optional Fields

| Field | Type | Description |
|---|---|---|
| `note` | string | Note written by the case author |

### 4.4. Validation Rules

The Case Loader **fails fast** if:
- The file does not exist → `FileNotFoundError`
- Any line contains invalid JSON → `ValueError` with the line number
- A required field is missing → `ValueError` naming the field
- `expected` is not one of the three valid values → `ValueError`
- `evidence` or `claim` is empty → `ValueError`

**Invalid cases must not be silently skipped.** A corrupted dataset must stop execution before evaluation begins.

---

## 5. Evaluator Contract

### 5.1. Model

| Property | Value |
|---|---|
| Model | `cross-encoder/nli-deberta-v3-small` |
| Size | 180 MB |
| Source | Hugging Face Hub |
| Runs in | The `llm` container |
| Cache | The `hf-cache` volume, mounted at `/root/.cache/huggingface/` |

### 5.2. Input

A single `(evidence, claim)` pair.

### 5.3. Output

NLI returns three labels with their probabilities:

```json
[
  {"label": "entailment", "score": 0.98},
  {"label": "neutral", "score": 0.01},
  {"label": "contradiction", "score": 0.01}
]
```

Map them to verdicts as follows:

| NLI label | Verdict |
|---|---|
| `entailment` | `supported` |
| `contradiction` | `contradicted` |
| `neutral` | `unsupported` |

### 5.4. Loading Strategy (MVP)

Load the model **for every case**. After inference, use `del` to release RAM.

```python
for case in cases:
    nli = load_model()            # ~2–5 seconds
    result = nli(evidence, claim) # ~70 ms
    del nli
```

Trade-off: RAM usage is prioritized over latency. In production, the model will be loaded only once.

---

## 6. Report Contract

The output file is **a single JSON object** with three levels.

### 6.1. Per-Case

```json
{
  "case_id": "nli-001",
  "category": "supported",
  "expected": "supported",
  "verdict": "supported",
  "passed": true,
  "raw_label": "entailment",
  "probabilities": {
    "entailment": 0.98,
    "neutral": 0.01,
    "contradiction": 0.01
  },
  "note": null,
  "latency_ms": 234.5
}
```

### 6.2. Per-Category

```json
{
  "supported": {"passed": 15, "total": 35, "rate": 0.4286},
  "contradicted": {"passed": 35, "total": 35, "rate": 1.0},
  "unsupported": {"passed": 30, "total": 30, "rate": 1.0}
}
```

### 6.3. Overall

```json
{
  "passed": 80,
  "total": 100,
  "rate": 0.8
}
```

### 6.4. Principles

- Overall performance **does not replace** per-category metrics. An overall score of 80% can conceal a category that scores only 43%.
- Always retain all three levels: per-case, per-category, and overall.

---

## 7. CLI Contract

```bash
python -m harness \
  --cases /path/to/cases.jsonl \
  --output /path/to/results.json
```

| Argument | Required | Description |
|---|---|---|
| `--cases` | Yes | Path to the JSONL file |
| `--output` | Yes | Path where the JSON report will be written |

The CLI only controls execution. It does not contain evaluation logic.

When running from a container:

```bash
docker compose exec -e PYTHONPATH=/app/fallback llm \
  /venv/bin/python -m harness \
  --cases /app/fallback/data/eval/nli-cases-v2.jsonl \
  --output /app/fallback/data/eval/nli-results-v2.json
```

`PYTHONPATH=/app/fallback` is required so Python can find the `harness` package because the default working directory is `/app`.

---

## 8. Module Structure

```text
src/llm/fallback/harness/
├── __init__.py          # exports
├── __main__.py          # CLI entry point + loop
├── loader.py            # JSONL validation + loading
├── evaluator_nli.py     # NLI model wrapper
└── report.py            # per-case + per-category + overall
```

---

## 9. Current Dataset

| Property | Value |
|---|---|
| File | `data/eval/nli-cases-v2.jsonl` |
| Number of cases | 100 |
| Source | 1,000 reviews from PostgreSQL, deduplicated |
| Generation method | NotebookLM generated claims from 48 evidence snippets |
| Distribution | 35 supported + 35 contradicted + 30 unsupported |

Distribution across the three groups:
- **Supported** (35 cases): the claim is supported by the evidence
- **Contradicted** (35 cases): the claim states the opposite of the evidence
- **Unsupported** (30 cases): the claim discusses a topic not present in the evidence

---

## 10. Status — Results on the 100-Case Dataset

```text
Overall: 80/100 (80%)

| Category      | Pass / Total | Rate  |
|---------------|--------------|-------|
| supported     | 15/35        | 43%   |
| contradicted  | 35/35        | 100%  |
| unsupported   | 30/30        | 100%  |
```

Output file: `data/eval/nli-results-v2.json`.

---

## 11. Known Limitations (Pain Points)

### 11.1. NLI Performs Poorly on Sentence Fragments

The NLI model was trained on complete sentences (SNLI/MNLI). When a claim is a **sentence fragment** (without a subject), the model chooses `neutral` instead of `entailment`.

Example:

```text
evidence: "Great telescope! Easy to set up and provides clear views."
claim:    "Easy to set up"
expected: supported
verdict:  unsupported   ← the model chose neutral because the claim is not grammatically complete
```

This is the main reason the supported rate is only 43%.

### 11.2. Unusual Case `nli-015`

The only case among the 35 supported cases for which NLI returns `contradiction` involves a claim that is an exact substring of the evidence. The cause is not yet clear.

### 11.3. Loading the Model for Every Case

This is slow. Evaluating 100 cases takes about four minutes, mostly because of model loading.

### 11.4. No Subcategories

All supported cases are grouped together. The evaluation does not distinguish between "exact match", "paraphrase", and "sentence fragment".

### 11.5. NotebookLM Occasionally Generates Errors

Case `nli-085` contains the word `"techx"` (possibly a typo inherited from the original seed data). This does not affect NLI logic, but the data is not clean.

---

## 12. Acceptance Criteria Met

| Criterion | Status | Evidence |
|---|---|---|
| Support for external JSONL datasets | ✅ | CLI accepts `--cases` |
| Change datasets without modifying code | ✅ | Only the path needs to change |
| Case contract documented | ✅ | Section 4 |
| Invalid datasets fail clearly | ✅ | Loader raises an error |
| Mixed categories supported | ✅ | Three categories in the file |
| Standard per-case result | ✅ | Section 6.1 |
| Standard per-category metrics | ✅ | Section 6.2 |
| Standard overall metrics | ✅ | Section 6.3 |
| JSON report generated | ✅ | `nli-results-v2.json` |
| Reproducible with one command | ✅ | Section 7 |
| Cases are not silently skipped | ✅ | Loader fails fast |

---

## 13. Design Principles

1. **The dataset does not control source code.** Changing the dataset does not mean changing the code.
2. **No separate HTTP Runner.** Each case contains its own `(evidence, claim)` pair.
3. **The Evaluator only scores; it does not aggregate.** The Aggregator combines batch-level results.
4. **Overall metrics must not hide category-level performance.** Always retain all three levels.
5. **Invalid data must fail clearly.** Never silently skip it.
6. **Do not over-engineer.** Build only what M14 requires.

---

## 14. Definition of Done — Closing M14

M14 is closed with the status **CLOSED WITH DOCUMENTED LIMITATION**.

Reasons no further fixes were made:
- The main pain point (sentence fragments) is a **model capability limitation**, not a pipeline issue.
- Fixing it properly would require a larger NLI model, an LLM judge, or a change to the case format.
- All three options are separate tasks and outside the scope of M14.
- The current case set is sufficient to serve as a baseline for M24, M25, and Phase B.

---

## 15. Reproduction

From the host CMD:

```bash
# Enter the container
docker compose exec llm sh

# Run the harness
cd /app/fallback
/venv/bin/python -m harness \
  --cases data/eval/nli-cases-v2.jsonl \
  --output data/eval/nli-results-v2.json

# Copy the results back to the host
# (from another CMD window)
docker compose cp llm:/app/fallback/data/eval/nli-results-v2.json \
  src/llm/fallback/data/eval/nli-results-v2.json
```

---

## 16. Files

| File | Role |
|---|---|
| `harness/__main__.py` | CLI entry point |
| `harness/loader.py` | Validation + loading |
| `harness/evaluator_nli.py` | NLI model wrapper |
| `harness/report.py` | Aggregation |
| `data/eval/nli-cases-v2.jsonl` | 100-case dataset |
| `data/eval/nli-results-v2.json` | Output (can be regenerated) |
| `data/raw/reviews-export.jsonl` | Original 1,000 reviews |
| `data/raw/unique-reviews.jsonl` | Unique reviews after deduplication |

---

## Notes About This File

This contract differs from the old file in five ways:

1. **More concise.** It has 16 sections instead of 32 and removes sections that have not been implemented.
2. **Accurate.** There is no "HTTP Runner" because it is not used in practice. There is no "Evaluator dispatch" because only one evaluator exists.
3. **As-built.** It reflects the current code, not the plan.
4. **Explicit status and limitations.** It clearly states where M14 ends and why.
5. **Includes a reproduction command.** Anyone reading it can rerun the evaluation.

This file is one part of M14. No other file is required.

Would you like me to change anything in this file before saving it to `docs/m14/CONTRACT.md`?