# Atlas Ontology Product

Atlas is an ontology-based enterprise analytics product group with two independent products:

- **Ontology Studio** builds, reviews, validates, releases, and activates governed ontology solutions.
- **Ontology Analytic Agent** consumes active runtime snapshots for governed query, analysis, attribution, and exploration.

ADT and Cash Trading are installed reference solutions and regression cases. They are not prerequisites of the generic product core.

## Repository layout

- `ontology-agent-poc/` — Python/FastAPI control plane, runtime, contracts, workers, and tests.
- `ontology-web/` — React/TypeScript Studio and Analytic Agent web application.
- `semantica-worker/` — isolated Semantica proposal worker.
- `deploy/common-product/` — Docker Compose and Kubernetes deployment assets.
- `ontology-product-group/` — product and architecture decision documents.
- `plans/ontology-studio-product-reset-v3.md` — current candidate product reset baseline.

## Local verification

```bash
cd ontology-agent-poc
.venv/bin/python -m pytest -q

cd ../ontology-web
npm test -- --run
npm run build

cd ../semantica-worker
uv run --python 3.12 --with pytest python -m pytest -q
```

## Local deployment

See [`deploy/common-product/README.md`](deploy/common-product/README.md). The deployable product targets Docker/Kubernetes on ARM64 and x86_64. EC2 deployment is performed only after explicit product-owner approval.

## Security boundary

This repository intentionally excludes customer inputs, cloud credentials, model API keys, runtime state, generated artifacts, recordings, and local deployment secrets.

## Public demo data

Customer-specific labels and local environment paths have been generalized. The
reference cases remain explicitly constructed-synthetic and do not claim customer
validation. Generated release bundles are excluded from source control; create fresh
ones from the sanitized source using the lifecycle commands in
[`ontology-agent-poc/README.md`](ontology-agent-poc/README.md).
