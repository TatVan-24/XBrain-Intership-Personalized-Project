# Infrastructure Repair Plan

## Objective

Move the raw repository from `NOT READY FOR FULL BUILD` to a reproducible build
baseline without changing AI behavior, removing incident hooks or deploying to
production.

## Phase A — Repair configuration blockers

1. Repair the minimal Compose service graph.
2. Supply every startup-required product-reviews environment variable in minimal
   mode with the same semantics as the full stack.
3. Decide whether trace testing should be restored from an authorized source or
   explicitly removed from the supported baseline. Do not fabricate evidence.
4. Re-run Compose validation for full, minimal and combined test stacks.

| File/path | Expected change |
| --- | --- |
| `source/techx-corp-platform/docker-compose.minimal.yml` | Restore valid database dependency and required environment |
| `source/techx-corp-platform/test/tracetesting/` | Restore missing assets only from an authoritative source |
| `source/techx-corp-platform/docker-compose-tests.yml` | Change only if the missing suite is intentionally retired |

## Phase B — Validate Helm build inputs — DEFERRED

1. Make Helm available in an approved environment.
2. Run `helm dependency build` for `source/techx-corp-chart`.
3. Run `helm lint` with default and deployment values.
4. Render manifests and perform client-side Kubernetes validation.
5. Compare components, ports, environment and secret references with Compose.

No cluster mutation is authorized in this phase. This phase is deferred because
the project scope is local-first and does not require Kubernetes/EKS delivery.

## Phase C — Build images in dependency order — COMPLETED

Build without pushing:

1. Custom dependency/platform images.
2. Stateful dependencies and platform-control images.
3. Stateless application images.
4. Edge/UI images.
5. Test images after their source is restored.

All 20 application images passed and are present locally. See
`docs/baseline/IMAGE_BUILD_RESULT.md` for the result and outstanding findings.

## Phase D — Runtime baseline

1. Start the full Compose stack.
2. Verify container state and health checks.
3. Exercise a non-AI storefront smoke path.
4. Confirm PostgreSQL, Valkey and Kafka connectivity.
5. Confirm telemetry reaches the collector and configured backends.
6. Stop the stack cleanly and record cleanup/recovery behavior.

AI functional evaluation remains out of scope. The model dependency only needs
to start without blocking the infrastructure baseline.

## Planned evidence

```text
docs/baseline/evidence/
├── compose-full-config.txt
├── compose-minimal-config.txt
├── compose-tests-config.txt
├── helm-lint.txt
├── helm-template.txt
├── image-build-results.txt
├── runtime-containers.txt
├── runtime-health.txt
└── smoke-test.txt
```

## Rollback

Rollback consists of reverting the approved repair diff and removing only the
explicitly tagged local images/containers created by validation. No registry
push, Git commit or Kubernetes deployment is included.

## Approval boundary

Stop before restoring files from an external repository, installing host tools,
pushing images, committing/pushing Git, deploying Kubernetes or changing AI
behavior unless explicitly authorized.
