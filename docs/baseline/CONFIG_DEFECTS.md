# Configuration Defect Register

## Confirmed defects

| ID | Priority | Surface | Problem | Proposed validation |
| --- | --- | --- | --- | --- |
| CFG-001 | P0 | Minimal Compose | `product-reviews` depends on undefined `postgresql` | RESOLVED: minimal Compose config exits 0 |
| CFG-002 | P0 | Minimal Compose | Required `LLM_HOST` and `LLM_PORT` are absent | RESOLVED: rendered environment contains both |
| CFG-003 | P1 | Test Compose | `test/tracetesting` build and mount source is absent, including in the upstream baseline | OPEN: restore from a compatible authoritative source, then build |
| CFG-004 | P1 | Helm validation | Chart cannot be linted/rendered in the current audit environment | Run dependency build, lint and template with Helm |

## Risks requiring validation

These are not confirmed defects until build/runtime evidence is available.

| ID | Risk | Required check |
| --- | --- | --- |
| RSK-001 | `.env` and `.env.override` may contain publish-unsafe defaults | Review values without exposing them; use placeholders/secrets |
| RSK-002 | Compose and Helm may differ in ports, dependencies or required environment | Compare rendered Compose and Helm inventories |
| RSK-003 | Build/push helper messaging is tied to the seed Docker Hub repository | Parameterize and verify the target before any push |
| RSK-004 | `service_started` does not prove dependency readiness | Validate startup races in runtime smoke tests |
| RSK-005 | Probes may be missing or test only process health | Inventory rendered probes after Helm rendering |

## Credential scan status

A keyword scan found credential-related configuration in expected locations such
as Compose, Helm values, PostgreSQL initialization and secret references. It does
not prove that a real secret is present or absent. Values must be reviewed before
the first commit/push without printing secrets into evidence.

## Scope boundary

No AI behavior defect is registered here. AI requirements are deferred until the
platform reaches a reproducible runtime baseline.
