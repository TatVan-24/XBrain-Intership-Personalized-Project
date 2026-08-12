# Bedrock to T5 fallback design

## Decision

Use Bedrock as the primary review summarizer and a locally hosted, warm,
LoRA-tuned T5-small adapter as the first degraded path. The final path is a
deterministic review-statistics response or an honest abstention.

## Boundaries

- The T5 model summarizes reviews only; it cannot call tools or act for users.
- The router, not either model, owns timeout, capped retry, circuit breaker,
  output validation, quality gates, tracing, and response selection.
- Review changes create a new `review_version`; cached/precomputed summaries
  from an older version must not be served as current.
- Online inference processes at most one bounded chunk. Complete hierarchical
  summaries are precomputed asynchronously when reviews change.

## State transitions

1. Sanitize untrusted reviews and retain their source IDs.
2. Call Bedrock within the measured timeout budget.
3. Reject provider errors, malformed output, PII leakage, injection compliance,
   and ungrounded summaries.
4. Call the already-warm T5 service and apply the same output gates.
5. If T5 fails, return deterministic statistics or `summary_unavailable` while
   keeping raw reviews and the product page available.
6. Emit one trace containing provider outcomes, timings, retry count, selected
   path, model versions, review version, and validation outcome without raw PII.

## Mandate mapping

- #6: real primary model, injection/PII handling, grounding, reproducible eval.
- #14: per-case metrics and external-input evaluation harness.
- #24: model-call and fallback traceability.
- #25: timeout, bounded retry, breaker, schema validation, controlled degrade.

## Deferred work

Bedrock connectivity, router integration, circuit breaker, background summary
precomputation, groundedness evaluation, and UI degraded-state handling follow
after the local model earns its quality and latency gates.
