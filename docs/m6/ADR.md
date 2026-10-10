# M6 — Architecture Decision Record

## ADR-01: Groq as primary LLM

**Status:** Accepted

**Context:** M6 requires "real model, no mock". Options considered: Bedrock (quota blocked), OpenAI (paid, no free tier for sustained eval), Groq (free tier, OpenAI-compatible).

**Decision:** Groq with `openai/gpt-oss-120b` as primary, `gpt-oss-20b` and `qwen3.8-27b` as failover.

**Consequences:**
- + Free tier sufficient for ~30 req/min eval
- + OpenAI-compatible API → mock service shape unchanged
- − Rate limit under heavy load
- − No SLA, no support
- Set `User-Agent: techx-llm/1.0` to pass Cloudflare (403 error code 1010 blocked default `Python-urllib` UA)

## ADR-02: Deterministic regex guardrails

**Status:** Accepted

**Context:** Layer 1 needs to detect injection, mask PII. Options: regex + fuzzy matching (deterministic), or second LLM as classifier (probabilistic).

**Decision:** Deterministic regex + fuzzy matching. No LLM classifier in Layer 1.

**Consequences:**
- + Deterministic, reproducible
- + No token cost, no latency penalty
- + No dependency on second model's availability
- − Cannot catch sophisticated semantic injections that don't match patterns
- − PII regex may miss non-standard formats

## ADR-03: Mock JSON as summary fallback

**Status:** Accepted

**Context:** When Groq is unreachable, summary path needs a fallback that doesn't hang the product page.

**Decision:** Pre-generated per-product mock JSON (`product-review-summaries.json`) served as fallback only for the summary path.

**Consequences:**
- + Product page never hangs
- + Fallback proven in original mock implementation
- + Zero latency (in-memory dict lookup)
- − Content is stale, not real-time
- Only applies to summary; QA path uses honest abstain instead

## ADR-04: QA semantic adherence delegated to model

**Status:** Accepted

**Context:** Initial implementation added `check_qa_adherence()` in Layer 4 to verify the answer contained at least one question keyword. Faithfulness eval showed this produced 2 false rejections (faith-03, faith-05): Groq returned semantically correct answers that used different vocabulary than the question.

**Decision:** Remove `check_qa_adherence()` from Layer 4. Delegate answerability and adherence decision to the model's structured `status` field in the QA contract.

**Consequences:**
- + Faithfulness eval: 10/10 (answerable 5/5, unanswerable 5/5)
- + Layer 4 keeps its safety role (PII, prompt leak, format)
- + No additional model call (compare to LLM judge approach)
- − QA semantic adherence is **not independently verified** by Layer 4
- − If the model returns `status: "answered"` for a question it should have abstained on, Layer 4 will not catch this
- Trade-off accepted given M6 scope

**Evidence:** `data/eval/faithfulness-results.json` (10/10 after fix).
