# Local Runtime Validation Result

## Status

`PASS — FULL LOCAL RUNTIME BASELINE STARTED`

The Step 5 full-stack startup completed with Docker Compose. All 28 declared
services are running and the public storefront returned HTTP 200.

## Startup attempt

Command:

```text
docker compose -f docker-compose.yml up -d --remove-orphans
```

Result: exit code 1 during image download. No application runtime health claim
can be made from this attempt.

## Dependency image results

| Compose service | Image | Result |
| --- | --- | --- |
| flagd | `ghcr.io/open-feature/flagd:v0.12.9` | PULLED |
| jaeger | `jaegertracing/jaeger:2.12.0` | PULLED AFTER RETRIES |
| otel-collector | `ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.142.0` | PULLED |
| prometheus | `quay.io/prometheus/prometheus:v3.8.1` | PULLED |
| valkey-cart | `valkey/valkey:9.0.1-alpine3.23` | PULLED AFTER RETRIES |
| postgresql | `postgres:17.6` | PULLED VIA SKOPEO WORKAROUND |
| grafana | `grafana/grafana:12.3.1` | PULLED VIA SKOPEO WORKAROUND |

Docker Engine continued to receive CloudFront EOF errors even after a Docker
Desktop restart. The exact Docker Hub images were therefore copied with Skopeo
and imported into the local Docker daemon. Compose configuration and image tags
were not changed.

## Runtime evidence

All 28 services declared by the full Compose project are running. Product
catalog restarted twice during the initial PostgreSQL startup window, recovered,
and remained running; no other non-zero restart count was observed.

| Check | Result |
| --- | --- |
| Kafka container health | HEALTHY |
| OpenSearch container health | HEALTHY |
| Valkey command | `PONG` |
| Flagd UI HTTP | 200 |
| Jaeger HTTP | 200 |
| OpenSearch HTTP | 200 |
| Prometheus readiness HTTP | 200 |
| Grafana health HTTP | 200 |
| Storefront through frontend-proxy | 200 (11,342-byte response) |
| OTEL debug exporter | Logs, metrics and traces observed |

The earlier OTEL PostgreSQL receiver DNS errors were generated only during the
degraded run before PostgreSQL existed. No fatal, panic, exception or connection
refused entry was found in the final 45-second full-runtime log window.

## Runtime defect repaired

`flagd-ui` originally failed before process creation because its Dockerfile
called `/app/bin/server`, while the built release only contained
`/app/bin/flagd_ui`. The raw repository did not include the Phoenix release
overlay that normally generates `bin/server`.

The image now starts `/app/bin/flagd_ui start` and sets `PHX_SERVER=true` in the
final runtime stage. After rebuilding, Bandit listened on port 4000 and the root
HTTP endpoint returned 200.

## Failure classification

The same `failed to copy` / `httpReadSeeker` / CloudFront `EOF` failure occurred
in all of these modes:

1. full `docker compose up`;
2. sequential `docker compose pull` with three retries per failed service;
3. direct `docker pull` for each remaining image.

Different valid image layers failed between attempts. This is evidence of an
environment/network transfer failure, not evidence that the Compose manifest or
application source is defective. The full Compose configuration still parses,
and all 20 locally built application images remain available.

## Validation not reached

- a complete interactive checkout/Kafka business transaction;
- browser-level UI automation;
- trace correlation across every service in one transaction;
- clean full-stack shutdown and cold-start recovery behavior.

## Current local state

The full stack remains running for continued functional validation. PostgreSQL
and Grafana are now present in the local Docker image store, so future Compose
starts do not depend on downloading those images again.

No registry push, Git commit, Git push or Kubernetes deployment was performed.
