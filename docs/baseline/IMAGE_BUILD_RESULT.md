# Application Image Build Result

## Status

`IMPLEMENTED — LOCAL BUILD VALIDATION PASSED`

All 20 application images declared by the platform baseline were built and are
present in the local Docker image store. No image was pushed to a registry.

## Results

| Service | Result | Local tag |
| --- | --- | --- |
| accounting | PASS | `nghiadaulau/techx-corp:latest-accounting` |
| ad | PASS | `nghiadaulau/techx-corp:latest-ad` |
| cart | PASS | `nghiadaulau/techx-corp:latest-cart` |
| checkout | PASS | `nghiadaulau/techx-corp:latest-checkout` |
| currency | PASS | `nghiadaulau/techx-corp:latest-currency` |
| email | PASS | `nghiadaulau/techx-corp:latest-email` |
| flagd-ui | PASS AFTER REPAIR | `nghiadaulau/techx-corp:latest-flagd-ui` |
| fraud-detection | PASS | `nghiadaulau/techx-corp:latest-fraud-detection` |
| frontend | PASS | `nghiadaulau/techx-corp:latest-frontend` |
| frontend-proxy | PASS | `nghiadaulau/techx-corp:latest-frontend-proxy` |
| image-provider | PASS | `nghiadaulau/techx-corp:latest-image-provider` |
| kafka | PASS | `nghiadaulau/techx-corp:latest-kafka` |
| llm | PASS | `nghiadaulau/techx-corp:latest-llm` |
| load-generator | PASS | `nghiadaulau/techx-corp:latest-load-generator` |
| payment | PASS WITH SECURITY FINDING | `nghiadaulau/techx-corp:latest-payment` |
| product-catalog | PASS | `nghiadaulau/techx-corp:latest-product-catalog` |
| product-reviews | PASS | `nghiadaulau/techx-corp:latest-product-reviews` |
| quote | PASS | `nghiadaulau/techx-corp:latest-quote` |
| recommendation | PASS | `nghiadaulau/techx-corp:latest-recommendation` |
| shipping | PASS | `nghiadaulau/techx-corp:latest-shipping` |

Final inventory check: `20/20` images present. The full Compose configuration
also returned exit code 0 after the builds.

## Source defect repaired during build

The raw `flagd-ui` source omitted assets expected by the generated Phoenix
application. `mix assets.deploy` failed successively on missing Heroicons,
DaisyUI and Topbar inputs.

Repair:

- added `src/flagd-ui/assets/vendor/heroicons.js`;
- added `src/flagd-ui/assets/vendor/topbar.js`;
- updated `src/flagd-ui/Dockerfile` to fetch the two large Phoenix v1.8.1
  DaisyUI assets from pinned URLs with SHA-256 checksum verification.

The repaired image completed Tailwind, esbuild, compilation and release.

## Findings that remain open

- `payment`: `npm ci --omit=dev` reported 35 dependency vulnerabilities (27
  moderate, 7 high and 1 critical). No automatic audit fix was applied because
  that could introduce unreviewed dependency or behavior changes.
- Registry/metadata requests intermittently returned EOF during early attempts.
  These were transient Docker/network failures, not source defects; sequential
  retries completed successfully.
- The trace-test image remains blocked because `test/tracetesting/` is absent in
  both this raw repository and the audited upstream baseline.
- Helm/Kubernetes validation remains deferred. The agreed target is local
  Docker Compose, with only an optional short AWS/Bedrock demonstration later.

## Scope boundary

This result proves that the application image set can be built locally. It does
not yet prove that containers start, become healthy, communicate correctly or
export telemetry. Those checks belong to the next local runtime phase.
