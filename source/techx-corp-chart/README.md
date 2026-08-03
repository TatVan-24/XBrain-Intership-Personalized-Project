# TechX Corp Platform - Helm Chart

Helm chart to deploy the TechX Corp platform on Kubernetes: application
microservices, AI review service + LLM, and the bundled observability stack
(collector, metrics, logs, traces, dashboards).

## Install
```sh
kubectl create namespace techx-corp --dry-run=client -o yaml | kubectl apply -f -
kubectl -n techx-corp create secret generic flagd-ui-secret \
  --from-literal=secret-key-base='<PRIVATE_RANDOM_VALUE>'
helm install techx-corp ./ -n techx-corp --create-namespace
```

Do not store the real `secret-key-base` value in a values file or in Git.

## License
Apache License 2.0.
