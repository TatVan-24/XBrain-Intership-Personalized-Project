# TechX Corp Platform

Internal microservice platform powering the TechX Corp online store: a polyglot,
Kubernetes-native system with a web storefront, product/cart/checkout/payment
services, an async messaging pipeline, an AI product-review summarizer, and a
full observability stack (metrics, logs, traces, dashboards).

## Layout
- `src/` - application microservices + AI review service + LLM
- `docker-compose.yml` - local run
- `Makefile` - build / run helpers

Kubernetes deploy: use the Helm chart in `../techx-corp-chart`.

## Run locally
```sh
cp .env.example .env
# Replace FLAGD_UI_SECRET_KEY_BASE in .env with a private random value.
docker compose up --force-recreate --remove-orphans --detach
```
Storefront: http://localhost:8080/

The `.env` file is local-only and must never be committed.

## License
Distributed under the Apache License 2.0. See `LICENSE`.
