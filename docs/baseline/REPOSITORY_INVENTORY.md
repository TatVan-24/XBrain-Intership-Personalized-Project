# Repository Inventory

## Scope

Infrastructure build-readiness inventory for the raw baseline under `source/`.
AI behavior and AI mandate compliance are intentionally out of scope until the
platform has a working runtime baseline.

## Deployment surfaces

| Surface | Location | Current role |
| --- | --- | --- |
| Local/full stack | `source/techx-corp-platform/docker-compose.yml` | Complete local platform |
| Local/minimal stack | `source/techx-corp-platform/docker-compose.minimal.yml` | Intended reduced local platform |
| Integration tests | `source/techx-corp-platform/docker-compose-tests.yml` | Full stack plus test services |
| Kubernetes | `source/techx-corp-chart/` | Helm chart for cluster deployment |
| Deployment overrides | `source/deploy/` | Image build/push and environment values |

## Runtime components

The full Compose configuration resolves 28 services.

| Layer | Components |
| --- | --- |
| Edge/UI | `frontend-proxy`, `frontend`, `image-provider`, `load-generator` |
| Commerce | `ad`, `cart`, `checkout`, `currency`, `email`, `payment`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping` |
| Event processing | `kafka`, `accounting`, `fraud-detection` |
| State | `postgresql`, `valkey-cart` |
| Platform control | `flagd`, `flagd-ui` |
| Model dependency | `llm` |
| Observability | `otel-collector`, `prometheus`, `jaeger`, `opensearch`, `grafana` |

## Build ecosystems

| Ecosystem | Representative components | Build input |
| --- | --- | --- |
| Node.js/TypeScript | frontend, payment | `package.json`, Dockerfiles |
| Python | product-reviews, recommendation, load-generator, llm | `requirements.txt`, Dockerfiles |
| Go | checkout, product-catalog | `go.mod`, Dockerfiles |
| .NET | cart, accounting | `.csproj`, Dockerfiles |
| Java/Kotlin | ad, fraud-detection | Gradle files, Dockerfiles |
| Rust | shipping | `Cargo.toml`, Dockerfile |
| C++ | currency | CMake, Dockerfile |
| Ruby | email | Gemfile, Dockerfile |
| PHP | quote | Composer manifest, Dockerfile |
| Elixir | flagd-ui | `mix.exs`, Dockerfile |

There are 28 Dockerfiles, including application, test and protobuf-generation
images.

## Local audit toolchain

| Tool | State |
| --- | --- |
| Docker client/engine | Available, version 29.2.1 |
| Node.js/npm | Available, Node 22.13.1 and npm 10.9.2 |
| Python | Available, 3.12.3 |
| Java | Available, 21.0.6 |
| kubectl | Available; version not captured by the generic version command |
| Helm | Missing |
| Go | Missing |
| .NET SDK | Missing |
| Rust/Cargo | Missing |

Missing host SDKs are audit-environment limitations, not repository defects.
Container builds can still validate most language toolchains.
