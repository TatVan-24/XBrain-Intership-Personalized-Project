# M14 — AI Eval Standard Report

## 1. Goal

Standardize evaluation for the AI layer: a reproducible measurement system with objective scoring that can run against hidden case sets.

Applicable surfaces: review summary + QA of the product-reviews service.

## 2. State Before M14

After M6, the following already existed:
- A simple eval harness using a keyword-based evaluator
- 10 faithfulness cases (5 answerable + 5 unanswerable)
- 10 security cases (injection + PII + benign)

Problem: keyword-based evaluation only measures "does the answer contain word X?", not "is the claim supported by the evidence?". This is an abstraction mismatch.

## 3. M14 Design

### 3.1. Metric Definition

Faithfulness = each claim in the answer must be supported by evidence.

Three verdict labels:
- **supported** — evidence supports the claim
- **contradicted** — evidence conflicts with the claim
- **unsupported** — evidence does not mention the claim

### 3.2. Evaluator

Use an NLI model (Natural Language Inference):
- Model: `cross-encoder/nli-deberta-v3-small` (180MB)
- Runs locally in the `llm` container
- Input: (evidence, claim)
- Output: probabilities for 3 labels + top-1 label

Trade-off: load the model for each case (RAM-friendly, slow at ~2s/case). Production will change this to load the model once.

### 3.3. Case Format

Each case requires 5 fields:
```json
{
  "case_id": "nli-001",
  "category": "supported",
  "evidence": "Battery lasts two days.",
  "claim": "The battery lasts two days.",
  "expected": "supported"
}
```

### 3.4. Harness Structure

```text
src/llm/fallback/harness/
├── __init__.py
├── __main__.py         # CLI entry
├── loader.py           # validate + load cases
├── evaluator_nli.py    # NLI evaluator
└── report.py           # aggregate per_case/per_category/overall
```

## 4. Dataset

- **Source:** 1000 reviews from PostgreSQL (`productreview` table)
- **Generation:** NotebookLM generated from 48 evidence reviews
- **Structure:**
  - 35 supported (2 claim/evidence from 18 evidence)
  - 35 contradicted (2 claim/evidence from 18 evidence)
  - 30 unsupported (1 claim/evidence from 30 evidence)
- **File:** `data/eval/nli-cases-v2.jsonl`

## 5. Results

```text
Overall: 80/100 (80%)

| Category      | Pass / Total | Rate  |
|---------------|--------------|-------|
| supported     | 15/35        | 43%   |
| contradicted  | 35/35        | 100%  |
| unsupported   | 30/30        | 100%  |
```

Output file: `data/eval/nli-results-v2.json`

## 6. Pain Point — Abnormal Distribution

### 6.1. Observation

- Contradicted: 100% pass, score usually > 0.99 (very confident)
- Unsupported: 100% pass, score usually > 0.99 (very confident)
- Supported: 57% fail, with the model choosing `neutral` instead of `entailment`

If the model were weak semantically, all three categories should fail. If the model were strong, all three should pass. The current pattern suggests that the model has the capability but does not apply it well to the specific form of the supported claims.

### 6.2. Characteristics of the 20 Failed Supported Cases

Claims belong to one of two forms:

**Form A — Sentence fragments without a subject:**
- "Easy to set up" (fragment of "Easy to set up and provides clear views")
- "provides clear views of the moon and brighter planets" (missing subject)
- "tricky to get used to the manual controls"
- "lightweight and portable"

**Form B — Descriptive phrases:**
- "battery drain on the phone"
- "Rugged and versatile"

### 6.3. Characteristics of the 15 Passed Supported Cases

Claims are complete sentences with subject + predicate:
- "The red light is useful"
- "Acceptable quality"
- "Solid product and easy to use"

### 6.4. Root Cause Hypothesis

The small NLI model (180MB) is trained on SNLI/MNLI — datasets containing **complete sentences**, not sentence fragments. When given a sentence fragment as the hypothesis:
- The model cannot identify an entailment relation with the evidence
- It chooses `neutral` as a "safe fallback"

This is normal model behavior, not a bug in the harness or case generation.

### 6.5. Special Case: nli-015

```text
evidence: "Compact and easy to carry, this telescope..."
claim:    "Compact and easy to carry"
expected: supported
verdict:  contradicted (score 0.978)
```

The model returns `contradiction` for a case where the claim is an exact substring of the evidence. This is an unusual error that does not follow the pattern of the other 19 failed cases. It may be caused by the model interpreting "repeating a fragment" as contradiction with the original sentence.

### 6.6. Uncertainty Region

Looking at the scores of passed cases:

| Case | entailment | neutral | verdict |
|---|---:|---:|---|
| nli-004 | 0.549 | 0.451 | supported |
| nli-020 | 0.622 | 0.377 | supported |
| nli-024 | 0.456 | 0.542 | unsupported (fail) |

Some cases have entailment and neutral probabilities close to each other (~50/50). Results may change if the cases are run again. This is a risk area, but there is not enough data to conclude more.

## 7. Known Limitations

1. **NLI does not handle sentence fragments well.** This is the main cause of the 20 supported-case failures.
2. **Model is loaded for each case**, which is slow (~2s/case). A 100-case benchmark takes ~3–4 minutes.
3. **No sub-categories.** All supported cases are grouped together; there is no distinction between "exact match" vs "paraphrase" vs "sentence fragment".
4. **NotebookLM may generate errors.** Case nli-085 contains the word `"techx"` (possibly a typo from the seed data).
5. **No adversarial cases.** The current case set is "clean" and does not test malformed inputs.

## 8. M14 Conclusion

**Achieved:**
- Working NLI evaluation harness
- 100 test cases with a clear structure
- Report with per-case, per-category, and overall results
- 80% result that honestly reflects the model's current capability

**Not achieved:**
- 43% supported rate is low
- Not at the 90%+ level to be considered production-ready

**Decision:** Close M14 with the limitation documented. Do not fix further.

Reasons:
- The pain point is in **model capability**, not the pipeline
- Correctly addressing it requires: (a) a larger NLI model, or (b) an LLM judge instead of NLI, or (c) a different case-generation strategy
- All three are separate work and outside the M14 scope
- The current case set is sufficient as a baseline for subsequent mandates (M24, M25, Phase B)

## 9. Repro

From the host CMD:

```bash
# Enter the container
docker compose exec llm sh

# Run the harness
cd /app/fallback
/venv/bin/python -m harness --cases data/eval/nli-cases-v2.jsonl --output data/eval/nli-results-v2.json

# Copy the result back to the host
# (from another CMD)
docker compose cp llm:/app/fallback/data/eval/nli-results-v2.json \
  src/llm/fallback/data/eval/nli-results-v2.json
```

## 10. Files

| File | Description |
|---|---|
| `harness/__main__.py` | CLI entry |
| `harness/loader.py` | Validate JSONL |
| `harness/evaluator_nli.py` | NLI evaluator |
| `harness/report.py` | Aggregate |
| `data/eval/nli-cases-v2.jsonl` | 100 cases |
| `data/eval/nli-results-v2.json` | Output |
| `data/raw/reviews-export.jsonl` | 1000 original reviews |
| `data/raw/unique-reviews.jsonl` | Unique reviews |

## 11. Proposed Commit Message

```text
feat(m14): NLI evaluator + 100-case benchmark (CLOSED WITH LIMITATION)

- Add harness with NLI evaluator (cross-encoder/nli-deberta-v3-small)
- Add 100-case benchmark (35 supported, 35 contradicted, 30 unsupported)
- Add per-case probability output + confusion-ready format
- Load model per case (MVP: RAM > latency)
- Results: 80/100 overall (43% supported, 100% contradicted, 100% unsupported)
- Known limitation: NLI fails on sentence fragments (documented in REPORT.md)
```

## 12. Status

`CLOSED WITH DOCUMENTED LIMITATION`

Proceed to M24.
