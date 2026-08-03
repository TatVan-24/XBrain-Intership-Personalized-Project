# Infrastructure Build Readiness

## Baseline status

`APPLICATION IMAGE BUILD PASSED — READY FOR LOCAL RUNTIME`

The full, minimal and combined test Compose graphs parse, and all 20 application
images have passed local build validation. The trace-test image remains blocked
because its source directory is absent. Helm is intentionally deferred because
the agreed project target is a local Docker Compose runtime.

## Validation evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Full Compose config | PASS | `docker compose -f docker-compose.yml config --quiet` returned 0 |
| Minimal Compose config | PASS AFTER REPAIR | PostgreSQL and required environment were restored |
| Test Compose config | PASS | `docker-compose-tests.yml` resolved its include graph |
| Test override standalone | NOT APPLICABLE | It is an override fragment, not a standalone project |
| Docker engine | PASS | Docker engine 29.2.1 responded |
| Python syntax | PASS | 13 Python files parsed successfully |
| JSON syntax | PASS | 32 JSON files parsed successfully |
| Plain YAML syntax | PASS WITH EXCLUSIONS | Helm templates require rendering before YAML parsing |
| Helm lint/template | NOT VALIDATED | Helm CLI is missing |
| Native Go/.NET/Rust build | NOT VALIDATED | Host SDKs are missing |
| Container image build | PASS | 20/20 required application images are present locally |
| Runtime startup | BLOCKED BY ENVIRONMENT | Docker CDN repeatedly returned EOF for Valkey, PostgreSQL and Grafana image layers |

## Confirmed readiness blockers

### BR-001 — Minimal Compose dependency graph is invalid — RESOLVED

- Priority: P0
- File: `source/techx-corp-platform/docker-compose.minimal.yml`
- Evidence: Compose reports that `product-reviews` depends on undefined service
  `postgresql`.
- Repair: restored the PostgreSQL service definition from the full Compose
  baseline.
- Validation: minimal Compose config now exits 0.

### BR-002 — Minimal product-reviews startup environment is incomplete — RESOLVED

- Priority: P0
- Files: `docker-compose.minimal.yml` and
  `src/product-reviews/product_reviews_server.py`.
- Evidence: the service requires `LLM_HOST` and `LLM_PORT` during startup, while
  the minimal Compose environment does not provide them.
- Repair: restored `FLAGD_HOST`, `FLAGD_PORT`, `LLM_HOST` and `LLM_PORT` to match
  the full Compose service contract, and restored the LLM dependency on flagd.
- Validation: rendered minimal config contains `LLM_HOST=llm` and `LLM_PORT=8000`.

### BR-003 — Trace-test build context is absent

- Priority: P1
- File: `source/techx-corp-platform/docker-compose-tests.yml`
- Missing path: `source/techx-corp-platform/test/tracetesting/`
- Evidence: test services reference the directory for Dockerfile, configuration
  and bind mounts, but `test/` does not exist.
- Effect: `traceBasedTests` cannot be built or executed.
- Upstream verification: the `main` branch of
  `TechX-Corp/xbrain-learners` also lacks this directory while retaining the
  Compose references. It cannot be restored exactly from that source.

## Items that are not defects yet

- Helm templates failing a plain YAML parser is expected before rendering.
- `docker-compose-tests_include-override.yml` is intentionally an override
  fragment. The combined test project resolves successfully.
- Missing host Go, .NET and Cargo commands do not prove their source is broken.
- AI quality, safety and AIOps capabilities are deferred until a reproducible
  infrastructure runtime exists.

## Exit criteria

- Full and minimal Compose configurations resolve.
- Referenced Dockerfiles, configs and bind-mount sources exist.
- Helm dependencies resolve and the chart passes lint/template.
- Every required application image builds for the target architecture.
- No real secret is stored in tracked baseline files.
- Repair evidence is captured before runtime startup begins.
