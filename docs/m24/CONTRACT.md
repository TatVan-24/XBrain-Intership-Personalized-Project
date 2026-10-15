# M24 — LLM Observability Contract

Status: CONTRACT (not coded yet)
Scope: LLM observability — trace, log, metric for the AI layer
Last update: 2026-10-14
Related: M6 (AI runtime), M14 (eval harness)

---

## 1. Purpose

M6 proved the AI feature runs. M14 proved quality is measurable.
M24 asks: when the AI answers, can the system trace its entire journey?

Requirements from the M24 mandate:

- Trace every model call (model, token, latency, cost, outcome)
- Be able to trace end-to-end from one customer request
- Traces must not leak PII/secrets

Difference between M14 → M24:

```text
M14:
  AI system → harness → pass/fail metrics

M24:
  AI system → trace + log + metric
            → can reconstruct the journey of each request
            → can search by trace_id
            → can draw a service map
```

---

## 2. Root problems

### 2.1. Current logs are loose text

The llm service log only prints to stdout, with no structure and no trace_id to link entries.

```text
request with 3 messages, model=techx-llm, tools=no
groq_attempts: [openai/gpt-oss-120b:ok] winner: openai/gpt-oss-120b
RAW QA CONTENT: {"status":"answered",...}
```

Nothing links these three lines together. With 100 concurrent requests → logs get mixed and cannot be told apart.

### 2.2. No detailed token, cost, latency counting

Groq returns `usage.prompt_tokens` and `usage.completion_tokens`. The current code **does not store** these numbers. It only takes `content`.

Cannot measure:

- How many tokens 1 request costs
- How long the Groq call takes
- How long Guardrail Layer 1 takes
- How long Layer 4 validate takes

### 2.3. No outcome

When a request finishes, no field records:

- Success using Groq
- Success using fallback
- Abstain (no info)
- Error (timeout, network)

You have to read the logs and guess.

### 2.4. Cannot trace from the original request

Product-reviews calls llm over HTTP. When an error occurs, it is unknown:

- Which trace_id that request has
- Which model was called
- What error the model returned
- Whether the fallback ran

You have to grep the logs by eye and match timestamps manually.

---

## 3. Base concepts

Concepts to know before reading further.

### 3.1. Trace

A record of the entire journey of 1 request. Consists of multiple spans.

### 3.2. Span

A unit of work in a trace. Each span has a name, start time, end time, attributes, and status.

Example of 1 trace with 4 spans:

```text
input_guardrail     5ms
groq_call           1500ms
output_validate     20ms
response_build      1ms
```

### 3.3. Trace ID

An identifier for each request. All spans of the same request share the same trace_id.

### 3.4. Context propagation

The way 1 service passes the trace_id to another service via an HTTP header (W3C traceparent).

Product-reviews calls llm → automatically attaches the `traceparent` header. Llm reads the header and creates a span that is a child of the product-reviews span.

### 3.5. Structured log

Logs in JSON format instead of text. Easy to parse, easy to search.

### 3.6. Metric vs Trace

| Type | Example | Stored in |
|---|---|---|
| Metric | "p95 latency = 1.2s" | Prometheus |
| Trace | "Request abc123 called Groq, took 1.5s" | Jaeger |

A metric is an aggregated number. A trace is the detail of each request.

---

## 4. Target architecture

```text
                    Frontend
                       │
                       ▼
              Product-reviews (already has OTEL)
                       │
                       │ HTTP (traceparent header auto-injected)
                       ▼
              Llm service (M24 adds OTEL)
                    │           │
              span:handle    span:guardrail
                    │           │
                    └─────┬─────┘
                          │
                   span:groq_call
                          │
                          ▼
                     Groq API

              ┌───────────┴───────────┐
              ▼                       ▼
        otel-collector          otel-collector
              │                       │
              ├─→ Jaeger (trace)      ├─→ OpenSearch (log)
              ├─→ Prometheus (metric)
              └─→ Grafana (UI)
```

Key points:

- Product-reviews already has OTEL (since M6)
- Llm service will get OTEL in M24
- Traces link automatically when both services use the standard W3C traceparent

---

## 5. Nine design decisions

### A1 — Can product-reviews be modified?

**Decision:** Yes.

**Reason:** It is the project's own code, not a fixed dependency.

**Consequence:** It can be modified to add a fallback trace_id + a warning log if the header is missing.

### A2 — Does Jaeger need to persist?

**Decision:** In-memory for the MVP.

**Reason:** The MVP needs to prove Jaeger works + understand the fundamentals. Persistence is a later optimization.

**Consequences:**

- Old traces are lost when the container restarts.
- The current stack is already configured with `MEMORY_MAX_TRACES=25000` — keeping the 25,000 most recent traces.
- In production, a backend (Cassandra/Elasticsearch) can be configured to persist.

**Trade-off:** Traces are lost on restart, but setup is simple.

### A3 — Does the llm service get OTEL?

**Decision:** Yes, full OTEL instrumentation.

**Reason:**

- M24 requires "end-to-end traceability" — both ends need OTEL.
- Product-reviews already has OTEL. Only llm needs to be added.
- Without OTEL in llm → the trace stops at product-reviews and the inside cannot be seen.

**Consequences:**

- Add the dependencies `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-grpc` to `requirements.txt`.
- Add ~100 lines of code to init the tracer + spans.
- The llm image grows by ~50MB.

**Learned:** OTEL SDK, context propagation, OTLP exporter, span attributes.

### B1 — Fallback when trace_id is missing?

**Decision:** Log a warning.

**Reason:** A warning log helps with later debugging. Staying silent makes tracing hard.

**Consequence:** Llm creates a new trace_id itself if the header is missing, and also writes the warning log `missing X-Trace-ID from upstream`.

### B2 — Is the Layer 1 masker enough, or should it be extended?

**Decision:** Extend.

**Reason:** Layer 1 currently has only email + phone. Still missing credit card, SSN, API key.

**Consequence:** Add 3-4 patterns to `guardrails.py`. Write tests for the new patterns.

### B3 — What does the system prompt log?

**Decision:** Log full content.

**Reason:**

- The repo is public → the system prompt is already exposed through the code.
- Easier to debug when reading directly.
- Simple.

**Consequences:**

- Trace/log records the full system prompt.
- **But it must be masked before logging** (due to B2).
- If the repo becomes private in the future, this decision needs to be revisited.

**Trade-off:** Less safe, but simple and easy to debug.

### B4 — Send llm logs to OpenSearch?

**Decision:** Yes.

**Reason:** So llm logs can be searched from Grafana like other services.

**Consequences:**

- Requires the OTEL Logs SDK (comes with A3).
- Configure a LoggerProvider pointing at otel-collector.
- Logs flow through otel-collector → OpenSearch.
- Grafana can query llm logs.

### C1 — Tiering policy cache → S3?

**Decision:** Build the base (documented in the ADR), implement when moving to AWS.

**Reason:** There is no S3 locally. It can only be simulated with a folder on disk.

**Consequences:**

- The M24 ADR clearly states the intended policy: cache → S3 standard → S3 infrequent.
- Implementation waits for the AWS mandate (M8/M9/M20/M21).

### C2 — Topology graph?

**Decision:** Yes, use the Jaeger Service Map.

**Reason:** Jaeger has it built in. No extra code needed. Nothing is lost.

**Consequences:**

- After there is traffic (~a few dozen requests), go to the Jaeger UI Service Map tab.
- The diagram draws itself from spans.
- Traffic must be generated to have data.

---

## 6. Scope — 3 work blocks

### Block 1 — Trace

- Add the OTEL SDK to the llm service
- Init tracer + spans in `app.py`
- Modify `product_reviews_server.py`: fallback trace_id + warning log
- Push spans to otel-collector → Jaeger
- Verify the full chain in the Jaeger UI
- Verify the Service Map

### Block 2 — Log + PII

- Extend the masker: 3-4 new patterns
- Modify `app.py`: mask before logging
- Record span attributes: model, tokens, latency, outcome
- Push logs to OpenSearch via the OTEL Logs SDK
- Verify: search logs by trace_id from Grafana

### Block 3 — ADR + Report

- ADR: 9 decisions + trade-offs + tiering policy (waiting for AWS)
- Report: architecture, results, evidence
- Repro command

---

## 7. Out of scope

Not done in M24:

- Persisting Jaeger to a database
- S3 tiering implementation (waiting for AWS)
- Complex Grafana dashboards
- Alerting rules
- OpenSearch index tuning
- Distributed trace sampling
- Cost calculation for paid tier (none yet)

---

## 8. Acceptance criteria

M24 is accepted when:

- [ ] Llm service has OTEL instrumentation
- [ ] Full-chain trace product-reviews → llm → Groq is displayed in the Jaeger UI
- [ ] Service Map draws the correct topology
- [ ] Every request has a trace_id
- [ ] Fallback trace_id logs a warning if the header is missing
- [ ] Masker extended with 3-4 new patterns
- [ ] Spans have attributes: model, tokens, latency, outcome
- [ ] Llm logs are searchable from Grafana (via OpenSearch)
- [ ] M24 ADR is written (9 decisions)
- [ ] M24 Report is written
- [ ] Repro command runs

---

## 9. Trace schema (planned)

### 9.1. Span for each request

```text
Span: llm.handle_request
  Attributes:
    - trace_id: <from header or generated>
    - product_id: P123
    - surface: summary | qa
    - has_tool_calls: true | false
  Status: OK | ERROR
```

### 9.2. Span for guardrail

```text
Span: llm.input_guardrail
  Attributes:
    - review_count: 5
    - quarantined_count: 1
    - pii_mask_count: 2
    - decision: continue | abstain
  Status: OK
```

### 9.3. Span for Groq call

```text
Span: llm.groq_call
  Attributes:
    - model: openai/gpt-oss-120b
    - attempt: 1
    - prompt_tokens: 400
    - completion_tokens: 80
    - total_tokens: 480
    - latency_ms: 1500
    - outcome: ok | error | fallback
  Status: OK | ERROR
```

### 9.4. Span for output validation

```text
Span: llm.output_validate
  Attributes:
    - decision: allow | reject
    - violations: []
    - fallback_triggered: false
  Status: OK
```

### 9.5. Outcome enum

```text
- completed_groq     : Groq success, no fallback
- completed_fallback : Groq fail → mock JSON
- abstained          : Not enough info
- rejected           : Layer 4 reject
- error              : Unhandled exception
```

---

## 10. Log schema (planned)

Each log record is JSON:

```json
{
  "timestamp": "2026-10-14T10:00:00.123Z",
  "level": "INFO",
  "service": "llm",
  "trace_id": "a3f5b8c2e1d9...",
  "span_id": "1111aaaa",
  "event": "groq_call_finished",
  "message": "Groq call succeeded",
  "attributes": {
    "model": "openai/gpt-oss-120b",
    "latency_ms": 1500,
    "tokens_total": 480
  }
}
```

The `trace_id` field lets logs be searched by trace.

---

## 11. Metric schema (planned, deferred)

Not implemented in M24, but planned:

```text
llm_requests_total{outcome="completed_groq"}
llm_request_duration_seconds{quantile="0.95"}
llm_tokens_total{model="openai/gpt-oss-120b", direction="prompt"}
llm_fallback_total{reason="groq_timeout"}
llm_guardrail_quarantine_total
llm_pii_mask_total
```

Pushed to Prometheus via the OTEL Metrics SDK.

---

## 12. Files to change

| File | Change |
|---|---|
| `src/llm/app.py` | Add OTEL tracer + span + log |
| `src/llm/requirements.txt` | Add `opentelemetry-*` packages |
| `src/llm/Dockerfile` | No change (already uses slim) |
| `src/llm/fallback/guardrails.py` | Add PII mask patterns |
| `src/product-reviews/product_reviews_server.py` | Add fallback trace_id + warning log |
| `docker-compose.yml` | May need to expose OTLP ports for the llm service |
| `docs/m24/CONTRACT.md` | This file |
| `docs/m24/ADR-M24.md` | To be written |
| `docs/m24/REPORT.md` | To be written after coding |

---

## 13. Design principles

1. **Full chain, not one-way only.** The trace must link from product-reviews down to llm down to Groq.
2. **Standard first, custom later.** Use W3C traceparent, do not invent your own.
3. **No PII logging.** Mask before logging, whatever the content.
4. **Graceful degradation.** Missing header → do not crash, create a new ID + warning.
5. **Do not over-engineer.** Do not build a Grafana dashboard in M24.
6. **In-memory is enough for the MVP.** Save persistence for production.

---

## 14. Known limitations (planned)

- Traces are lost when the Jaeger container restarts (in-memory).
- The Service Map needs traffic to draw. No traffic → empty.
- Cost = 0 because of the Groq free tier. Paid cost cannot be estimated.
- No alerting rules yet.
- No Grafana dashboard for llm metrics yet.
- Tiering policy not implemented (waiting for AWS).

---

## 15. Status

`CONTRACT — READY FOR IMPLEMENTATION`