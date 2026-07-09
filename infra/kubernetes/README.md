# Kubernetes

This folder contains a Kustomize-compatible starter deployment for DayPilot Enterprise.

```bash
kubectl apply -k infra/kubernetes
```

The manifests use safe defaults: write execution disabled, dry-run enabled, and human approval required.
Replace image names under each service manifest with your CI-published registry tags.
