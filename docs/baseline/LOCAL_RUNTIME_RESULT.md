# Local Runtime Validation Result

## Status

`BLOCKED — REQUIRED DEPENDENCY IMAGES COULD NOT BE DOWNLOADED`

The Step 5 full-stack startup was attempted with Docker Compose, but the local
runtime could not be created because Docker repeatedly lost connections while
reading image layers from Docker Hub's CloudFront delivery endpoint.

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
| valkey-cart | `valkey/valkey:9.0.1-alpine3.23` | BLOCKED BY REPEATED EOF |
| postgresql | `postgres:17.6` | BLOCKED BY REPEATED EOF |
| grafana | `grafana/grafana:12.3.1` | BLOCKED BY REPEATED EOF |

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

- container running/healthy state;
- PostgreSQL, Valkey and Kafka connectivity;
- storefront HTTP smoke path;
- checkout/Kafka event path;
- OTLP ingestion and Grafana/Jaeger/OpenSearch visibility;
- clean full-stack shutdown behavior.

## Resume condition

Resume Step 5 after Docker can successfully pull the three missing pinned
images. Re-run `docker compose up -d --remove-orphans`; Docker should reuse the
layers and dependency images already cached locally. Do not change image tags or
source code merely to bypass this network failure.

No registry push, Git commit, Git push or Kubernetes deployment was performed.
