# Ontology Common Product Helm chart

This chart reproduces the ADT and Cash Trading solution catalog, durable workspace editors and
lifecycle tracers on a single-node k3s or standard Kubernetes cluster. React is the public shell, PostgreSQL
owns the Studio registration/workspace plus active context/runtime head, S3/MinIO stores
their exact-version artifacts, and the Python services select deterministic semantic and
analytic implementations through explicit scenario adapters.

The chart also deploys the exact-pinned Semantica proposal worker when
`semantica.enabled=true`. The worker is an internal Studio dependency: it has no
database/S3 credentials and cannot write Draft, Decision, Release, or Agent runtime
state. Studio records its output as unreviewed candidates only.

It is deliberately a demo deployment profile: one runtime replica, shared filesystem
cache/compatibility volumes, and shared demo authentication. PostgreSQL/S3 remain the
authority when the local cache is present. HA and enterprise IAM are later vertical slices,
not hidden claims of this chart. The two installed packages demonstrate package-driven
extension; they do not claim arbitrary-document ontology compilation.

## Required secrets

Create `ontology-product-state` with these keys:

- `ONTOLOGY_DATABASE_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `POSTGRES_PASSWORD` (only when the in-cluster PostgreSQL profile is enabled)
- `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` (only when MinIO is enabled)

Create `ontology-demo-auth` with the environment keys documented by
`ontology_agent.demo_auth.AuthSettings`. Store only the PBKDF2 verifier, never a cleartext
password.

Create `ontology-qwen` with key `ONTOLOGY_QWEN_API_KEY`. The key is mounted
only into the internal model-gateway pod; it is not present in Runtime,
Studio, Agent-control, Web, bootstrap or browser code. Runtime sends only an
exact registered constructed-synthetic question projection to that gateway.
Set `llm.enabled=false` for a deterministic-only deployment.

## Install

Build and publish the two ARM64-compatible images, create the secrets, then install the
chart in its own namespace. Set `ingress.host` and `ingress.tlsSecretName` for the final
HTTPS endpoint. For AWS S3, disable MinIO and set `productState.s3EndpointUrl` to an empty
string; the application will use the standard AWS endpoint and exact object versions.
For managed PostgreSQL/S3, enable `networkPolicy.externalServiceEgress` and narrow its
CIDRs to the VPC endpoints before release.

The demo default permits model-gateway HTTPS egress using `0.0.0.0/0` because
provider IP ranges are not stable. Narrow `llm.providerEgressCidrs` through an
approved egress proxy before using this chart outside the isolated PoC account.

Use `values-managed.yaml` as the starting overlay for managed PostgreSQL and AWS S3.
The included `10.0.0.0/8` is only a syntactically valid private-network placeholder and
must be replaced by exact target CIDRs.

The chart fails readiness when PostgreSQL or an exact S3 object version cannot be read.
