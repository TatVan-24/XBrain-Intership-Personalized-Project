# Repository File Policy

## Commit to Git

- application source, tests and Dockerfiles;
- Docker Compose and Helm definitions;
- `.env.example` files containing placeholders only;
- dependency lock files, including `Chart.lock` and language lock files;
- generated protobuf source required by container builds;
- Grafana dashboards, collector configuration and demo image assets;
- lint, formatting, licensing and line-ending configuration;
- architecture, baseline and operating documentation intended for the project.

## Keep local only

- `.env`, `.env.*`, API keys, cloud credentials and private keys;
- IDE settings and operating-system metadata;
- dependency caches and build output;
- logs, PID files, crash dumps and local databases;
- Terraform state/private variable files;
- downloaded Helm chart archives;
- internal context explicitly listed under `Local project context` in the root
  `.gitignore`.

## Secret handling

- Docker Compose secrets are supplied through the ignored local `.env` file.
- Kubernetes secrets are created out-of-band and consumed with `secretKeyRef`.
- A committed secret must be revoked or rotated first, then removed from every
  reachable Git ref; deleting it only in a later commit is insufficient.
