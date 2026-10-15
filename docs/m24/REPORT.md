# M24 — LLM Observability Report

Status: COMPLETED
Scope: LLM observability — trace, log, metric for AI service layer
Last update: 2026-10-15
Related: M6 (AI runtime), M14 (eval harness)

---

## 1. Objective

M6 proved the AI feature works. M14 proved the AI quality is measurable.
M24 asks a different question:

> When the AI answers a request, can we reconstruct the entire journey of that request?

Specifically, M24 requires:

- Every model call is traced (model, tokens, latency, cost, outcome)
- The system can reconstruct the full chain from one customer request
- Traces do not leak PII or secrets

This report documents what was built, what was found, and what remains.

---

## 2. Architecture

### 2.1. Before M24

```text
frontend
└── product-reviews (has OTEL)
    └── llm (no OTEL) ← trace stops here
        └── Groq
```

Llm service had no OpenTelemetry instrumentation. Traces from product-reviews did not propagate into the llm layer. From Jaeger's perspective, the request disappeared after product-reviews.

### 2.2. After M24

```text
frontend-web
└── frontend-proxy
    └── frontend
        └── product-reviews
            ├── flagd (feature flag evaluation)
            ├── llm (has OTEL now)
            │   ├── llm.handle_qa
            │   │   ├── llm.input_guardrail
            │   │   ├── llm.groq_call → Groq API
            │   │   └── llm.output_validate
            │   └── llm.handle_summary
            │       ├── llm.input_guardrail
            │       ├── llm.groq_call → Groq API
            │       └── llm.output_validate
            └── postgresql (SELECT reviews)
```

Single trace now spans 5-6 services with 20+ spans.

### 2.3. Telemetry pipeline

```text
llm service
├── spans ──→ otel-collector ──→ Jaeger
└── logs  ──→ otel-collector ──→ OpenSearch
```

No changes needed to otel-collector, Jaeger, OpenSearch, or Prometheus. They were already in the stack and accepted the new data without configuration changes.

---

## 3. Implementation

### 3.1. Package additions

Added to `src/llm/requirements.txt`:

```text
opentelemetry-api>=1.20,<2
opentelemetry-sdk>=1.20,<2
opentelemetry-exporter-otlp-proto-http>=1.20,<2
opentelemetry-instrumentation-flask>=0.41b0,<1
opentelemetry-exporter-otlp-proto-http (log exporter)
```

Image size increased by approximately 50 MB.

### 3.2. Environment variables

Added to llm service in `docker-compose.yml`:

```text
OTEL_SERVICE_NAME=llm
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

### 3.3. Tracer initialization

In `src/llm/app.py`:

- Created `init_otel()` function to set up `TracerProvider`, `OTLPSpanExporter`, and `BatchSpanProcessor`
- Initialized tracer at module load
- Called `FlaskInstrumentor().instrument_app(app)` to auto-instrument HTTP routes

### 3.4. Manual spans

Added manual spans around key logic in `app.py`:

| Span | Location | Purpose |
|---|---|---|
| `llm.handle_qa` | `handle_qa()` | Parent span for QA path |
| `llm.handle_summary` | `handle_summary()` | Parent span for summary path |
| `llm.input_guardrail` | Inside both handlers | Wrap Layer 1 call |
| `llm.groq_call` | `_call_groq_once()` | Wrap Groq API call |
| `llm.output_validate` | Inside both handlers | Wrap Layer 4 call |

### 3.5. Span attributes

**`llm.groq_call`** — model call details:

```text
model              (attempted model)
model_returned     (actual model that responded)
tokens.prompt      (input tokens)
tokens.completion  (output tokens)
tokens.total       (total tokens)
outcome            (ok | error)
error              (if error, the reason)
```

**`llm.input_guardrail`** — Layer 1 results:

```text
layer                  (1)
operation              (input_guardrail)
review_count           (total reviews in request)
safe_review_count      (reviews that passed)
quarantined_count      (reviews blocked)
pii_mask_count         (PII items masked)
decision               (continue | abstain)
degraded               (bool)
```

**`llm.output_validate`** — Layer 4 results:

```text
layer               (4)
operation           (output_validate)
decision            (allow | reject)
violations_count    (number of violations)
violations          (comma-separated list)
```

**`llm.handle_qa` / `llm.handle_summary`** — overall outcome:

```text
product_id
surface    (qa | summary)
model      (which model served the request)
outcome    (completed | no_reviews | no_question | ... | layer4_reject)
```

### 3.6. Log export

Configured `LoggerProvider` + `OTLPLogExporter` + `LoggingHandler` in `app.py`. Every `app.logger.info(...)` call now flows through otel-collector into OpenSearch with structured fields including `trace_id`.

### 3.7. PII masker extension

Extended `src/llm/fallback/guardrails.py` with 3 new regex patterns:

| Pattern | Placeholder | Example match |
|---|---|---|
| Email (existing) | `[EMAIL]` | `user@example.com` |
| Phone (existing) | `[PHONE]` | `0912345678` |
| Credit card (new) | `[CREDIT_CARD]` | `4111 1111 1111 1111` |
| SSN (new) | `[SSN]` | `123-45-6789` |
| API key (new) | `[API_KEY]` | `gsk_abc123...` |

Masking applies before logging. Raw PII never reaches OpenSearch.

### 3.8. Product-reviews bug fixes

Two bugs were discovered in `product_reviews_server.py` while debugging M24 trace:

**Bug 1 — Missing pattern in message routing**

The llm service only accepted two request patterns:

- `"Can you summarize the product reviews?"`
- `"Based on the tool results, answer the original question about product ID"`

Any other phrasing was rejected with `"Sorry, I'm not able to answer that question."` Added a third pattern:

- `"Answer the following question about product ID"`

**Bug 2 — Question not forwarded to llm**

The second LLM call sent:

```text
Based on the tool results, answer the original question about product ID:XXX.
```

The llm service could not find the actual question because it was never included. Fixed by appending the question:

```text
Based on the tool results, answer the original question about product ID:XXX. Question: {question}.
```

**Bug 3 — llm could not extract reviews from proto JSON**

Tool response from product-reviews is a proto-serialized array of arrays:

```json
[["username", "description", 4.5], ...]
```

The llm `extract_reviews_from_messages` function only handled dict items. Fixed by adding a second branch for list items.

---

## 4. Results

### 4.1. Full trace reconstruction

Sample trace from a real customer request via storefront:

```text
Duration:      2.53s
Services:      5 (frontend-web, frontend-proxy, frontend, product-reviews, llm)
Total spans:   20
Depth:         14
Trace ID:      ec014ca
```

Span tree (simplified):

```text
frontend-web HTTP POST                          2.11s
└── frontend-proxy ingress                      2.02s
    └── frontend-proxy router egress            2.02s
        └── frontend POST                       2.02s
            └── frontend api route              2.02s
                └── frontend grpc AskProductAIAssistant   2.02s
                    └── product-reviews AskProductAIAssistant  2.02s
                        └── product-reviews get_ai_assistant_response  2.02s
                            ├── product-reviews chat techx-llm (handshake)  10.89ms
                            │   └── llm POST  1.91ms
                            ├── product-reviews SELECT  1.72ms
                            └── product-reviews chat techx-llm (final)  1.98s
                                └── llm POST  1.98s
                                    └── llm.handle_qa  1.97s
                                        ├── llm.input_guardrail  1.72ms
                                        ├── llm.groq_call  1.96s
                                        └── llm.output_validate  14.05ms
```

### 4.2. Groq call observed in span

The `llm.groq_call` span records:

```text
model:              openai/gpt-oss-120b
tokens.prompt:      2068
tokens.completion:  329
tokens.total:       2397
model_returned:     openai/gpt-oss-120b
outcome:            ok
duration:           1.96s
```

Correlated Groq API dashboard confirms:

```text
Model: openai/gpt-oss-120b
Code: 200
TTFT: 0.895s
Latency: 1.578s
Input tokens: 2068
Output tokens: 329
```

### 4.3. Time breakdown

For the sample request:

| Layer | Duration | % of total |
|---|---|---|
| Frontend + proxy + routing | ~90ms | 3.5% |
| gRPC to product-reviews | ~90ms | 3.5% |
| Tool handshake | ~11ms | 0.4% |
| DB query | ~2ms | 0.1% |
| Groq call | 1.96s | 77% |
| Output validation | 14ms | 0.6% |

Groq call dominates. This is expected — model inference is the slowest step. Cache and smaller-model strategies are the two levers available for future optimization.

### 4.4. Log export verified

Query OpenSearch:

```text
yellow open   otel-logs-2026-10-15  docs.count: 301  size: 2.4mb
```

301 log documents from the stack, including llm service logs with structured fields (`service.name`, `trace_id`, `level`, `message`). Logs are searchable by `trace_id` to correlate with Jaeger traces.

### 4.5. Masker validated

Unit test extended for new patterns. All 5 pattern types masked correctly before logging.

---

## 5. Value demonstrated — Bugs found via observability

Three real bugs were found while implementing M24. None were visible without distributed tracing.

### Bug 1 — Silent pattern rejection

**Symptom:** Customer asks custom question. AI replies "Sorry, I'm not able to answer that question."

**Without tracing:** Hard to tell why. Logs were unstructured. Could be LLM, could be network, could be guardrail.

**With tracing:** Jaeger showed the first llm POST span at ~2ms with response "Sorry...". Trace confirmed llm never called Groq. Reading the code path, the pattern check rejected the message before reaching Groq.

**Fix:** Add pattern to whitelist.

### Bug 2 — Question lost between two LLM calls

**Symptom:** After fixing Bug 1, AI replied "I don't have enough information to answer from the provided reviews."

**Without tracing:** Response looks like an "abstain" case — but reviews exist.

**With tracing:** `llm.handle_qa` span was 70µs. Groq never called. Adding debug attributes showed `extract_original_question` returned `None`. Tracing to product-reviews source, the second LLM call did not include the question text.

**Fix:** Append `Question: {question}.` to the message.

### Bug 3 — Reviews not extracted from proto JSON

**Symptom:** After fixing Bug 2, still abstained.

**Without tracing:** Would need to add print statements and rebuild repeatedly.

**With tracing:** Span showed `handle_qa` returned `reason=no_reviews`. Add debug log in `extract_reviews_from_messages` — saw that tool response items were lists (`[username, text, score]`), not dicts. The extractor only handled dicts.

**Fix:** Add second branch for list-type items.

This sequence demonstrates the value of M24. Three silent bugs, one after another, each hidden by the previous symptom. Distributed tracing reduced the debugging loop from "guess + rebuild + check" to "open Jaeger + look at the last failing span".

---

## 6. Known limitations

- **Jaeger is in-memory.** Traces are lost on restart. `MEMORY_MAX_TRACES=25000` bounds the recent history. Persisting to Cassandra or OpenSearch is deferred until needed.
- **Log export is recent.** OpenSearch only has logs from after the OTEL LoggerProvider was added. Older logs are gone.
- **No metric export yet.** The M24 contract mentions metric (p50/p95 latency, total tokens). Currently only traces and logs are exported. Metric via OTLP to Prometheus is not implemented.
- **No dashboards.** Grafana has no custom dashboard for llm service yet. Queries must be written manually.
- **No alerting.** No alert rules on latency, error rate, or token spend.
- **No tiering.** Log retention and archive to S3 is documented but not implemented locally.
- **Groq's own metrics are separate.** The Groq dashboard shows token usage and latency, but is not integrated into Jaeger or OpenSearch. Correlation requires checking two places.

---

## 7. Reproduction

From host machine:

```bash
# Start full stack
docker compose --profile e2e --profile commerce --profile events up -d

# Get frontend port
docker compose port frontend-proxy 8080

# Open browser to http://localhost:<port>
# Navigate to any product, ask AI assistant a question

# View trace in Jaeger
# Open http://localhost:<jaeger_port>
# Service: llm, click Find Traces

# Query logs in OpenSearch
docker compose exec opensearch curl -s "http://localhost:9200/otel-logs-*/_search?q=service.name:llm&size=5&pretty"
```

Expected trace characteristics for a QA request:

```text
Total spans:      ~20
Total duration:   1.5 - 3s
Services:         5 (frontend-web, frontend-proxy, frontend, product-reviews, llm)
Critical span:    llm.groq_call (1-2s, contains token + model attributes)
```

---

## 8. Files changed

| File | Change |
|---|---|
| `src/llm/app.py` | Add OTEL SDK, tracer, manual spans, span attributes, log exporter |
| `src/llm/requirements.txt` | Add 4 OTEL packages |
| `src/llm/Dockerfile` | No change (slim base already supports OTEL) |
| `src/llm/fallback/guardrails.py` | Extend masker: CREDIT_CARD, SSN, API_KEY |
| `src/product-reviews/product_reviews_server.py` | Fix pattern whitelist + question forwarding |
| `docker-compose.yml` | Add OTEL env vars to llm service |
| `docs/m24/CONTRACT.md` | Contract document (see separate file) |
| `docs/m24/REPORT.md` | This report |

---

## 9. Status

**M24 CORE — COMPLETED**

What was promised in the contract and delivered:

- [x] Llm service has OTEL instrumentation
- [x] Full chain trace frontend → llm → Groq visible in Jaeger
- [x] Service Map shows correct topology
- [x] Every request has a trace_id
- [x] Span attributes: model, tokens, latency, outcome
- [x] Layer 1 and Layer 4 have detailed span attributes
- [x] Masker extended with 3 new patterns
- [x] Logs exported to OpenSearch
- [x] Logs searchable by trace_id

Deferred to future work:

- [ ] Metric export (p50/p95 latency, token totals)
- [ ] Grafana dashboard for llm service
- [ ] Alerting rules
- [ ] Log tiering (cache → S3)
- [ ] Persistent Jaeger backend

---

## 10. Summary

M24 delivered a working observability foundation for the llm service. Traces now connect every layer from browser to Groq. Logs are structured and searchable. PII is masked before hitting disk.

Three real bugs were surfaced and fixed during this work. None required a code change to have been prevented — they were integration issues between services. Without distributed tracing, each bug would have taken significantly longer to isolate.

The next work on M24, if continued, would be moving from "we can see the request" to "we can act on what we see": metric, dashboard, alerting.