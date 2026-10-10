# M6 — LLM Service Contract

## 1. Endpoint

`POST /v1/chat/completions` — OpenAI-compatible chat completion.
Called by `product-reviews` service with `base_url=http://llm:8000/v1`.

Request:
```json
{
  "model": "techx-llm",
  "messages": [...],
  "tools": [...]  // optional, used for tool-calling handshake
}
```

Response: OpenAI chat completion shape (`choices[0].message.content`).

## 2. Task classification

`classify_task(messages)` routes on last user message:

| Trigger substring | Task | Handler |
|---|---|---|
| `"Can you summarize the product reviews?"` | summary | `handle_summary()` |
| `"answer the original question about product ID"` | qa | `handle_qa()` |
| anything else | unknown | fixed refusal response |

Task is decided by the **service**, not by the model.

## 3. Summary contract

Input: reviews extracted from `tool` role messages.

Output from Groq: JSON
```json
{"status": "completed", "summary": "...", "source_review_ids": ["r1", "r2"]}
```
or
```json
{"status": "unavailable", "summary": null, "source_review_ids": []}
```

Success path: response = summary.
Groq abstain → `"I don't have enough information to answer from the provided reviews."`
Groq unreachable → mock JSON fallback (per-product pre-generated summary).

## 4. QA contract

Input: question (extracted from user message via regex `Question:\s*(.+?)(?:\n|$)`) + reviews.

Output from Groq: JSON
```json
{"status": "answered", "answer": "...", "source_review_ids": [...]}
```
or
```json
{"status": "unavailable", "answer": null, "source_review_ids": []}
```

Success path: response = answer.
Groq abstain → `"I don't have enough information to answer from the provided reviews."`
Groq unreachable → same abstain message. **QA never uses mock fallback.**

Answerability decision is delegated to the model's `status` field.

## 5. Guardrails

**Layer 1 — Input (`guardrails.py`)**
- Unicode NFKC normalize, remove control/zero-width chars
- Reconstruct spaced tokens (`i g n o r e` → `ignore`) for detection
- Mask PII: email → `[EMAIL]`, phone → `[PHONE]`
- Detect injection patterns: `ignore`, `reveal`, `execute`, `system prompt`, `secret`, `api key`
- Risk score 0-5+: ≥3 quarantine review; all reviews quarantined → abstain

**Layer 2 — Prompt (`prompt_builder.py`)**
- Role separation: system = trusted policy + schema; user = untrusted reviews
- Escape `<`, `>`, `&` to prevent tag smuggling
- Version check: `review_version` must match current snapshot
- Two builders: `build_prompt()` for summary, `build_qa_prompt()` for QA

**Layer 4 — Output (`output_guardrails.py`)**
- Schema: non-empty, 3-160 words, no control chars
- PII: reject if email/phone in output
- Prompt leak: reject `system prompt`, `security rules`, `trusted_instruction`, `ignore previous instructions`
- Format leak: reject `rating=`, `review=`, `<untrusted_reviews>`
- Source IDs: must be subset of input reviews
- Does **not** check semantic adherence to question. That is delegated to Groq `status` field.

## 6. Fallback

| Failure mode | Summary path | QA path |
|---|---|---|
| Groq unreachable | mock JSON | abstain message |
| Groq returns `unavailable` | abstain message | abstain message |
| Layer 4 reject | mock JSON | abstain message |
| Layer 1 all quarantined | abstain message | abstain message |

## 7. Observability

Logs written to stdout (collected by Docker):
- `request with N messages, model=..., tools=yes/no`
- `groq_attempts: [model1:ok, ...] winner: model1`
- `RAW GROQ CONTENT: <first 500 chars>`
- `layer4_reject: [violations]`
- `layer1_abstain`, `qa layer1_abstain`

No structured OTEL export yet. Deferred to M24.
