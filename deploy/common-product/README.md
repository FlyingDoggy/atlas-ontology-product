# Common Product — Solution-aware Ontology Products

This deployment runs two constructed-synthetic release-to-answer paths on the same
product kernel:

- ADT reference analytics;
- Cash-market order and trading activity monitoring compiled from the External Review Team
  transcription, with every correction, assumption and open confirmation retained.

Both use:

- React/Vite web shell;
- FastAPI backend;
- PostgreSQL product-state, release, snapshot, activation-head and event indexes;
- exact-version S3-compatible release, snapshot and context artifacts in MinIO;
- exact PostgreSQL/S3 Studio solution registrations with four independently
  identified component classes per solution;
- a mutable PostgreSQL solution directory for display metadata and lifecycle,
  deliberately separated from immutable ontology package versions;
- exact template cloning with new package, scenario, workspace and solution identities,
  followed by full resource-inventory and checksum regeneration;
- a descriptor-driven Studio editor whose workspace head, generations and immutable
  draft revisions are held in PostgreSQL plus exact-version S3 artifacts;
- scenario adapters selected by the registered package identity; React contains no
  ADT or Cash Trading calculation branch.
- an internal Qwen `qwen3.8-max` gateway that accepts only exact registered
  constructed-synthetic questions and returns a closed intent/tool goal;
- a shared Agent flow in which the bound goal enters the selected scenario adapter,
  while every number, fact, answer clause and evidence record remains deterministic
  and snapshot-bound.

It is a constructed-synthetic engineering tracer, not a production/customer readiness claim.

## Local run

```bash
cp .env.example .env
# replace the PostgreSQL and MinIO values in .env
docker compose --env-file .env config --quiet
docker compose --env-file .env up --build --wait
```

Open `http://127.0.0.1:18080/ontology-agent/` or
`http://127.0.0.1:18080/ontology-studio/`. The auth and Qwen env-file paths may point to
the existing ADT demo secret files or independently managed files. The Qwen key is
loaded only by `model-gateway`; Runtime, Studio, Web and the browser never receive it.

Selecting one of the eight registered questions triggers one Qwen grounding call. An
edited or arbitrary question is never sent to Qwen and stays on the deterministic
closed-semantic path. If the gateway fails after an exact case is selected, the service
restarts from the trusted package-owned case goal and releases no partial model output.
For the ADT package, Studio exposes a bounded Qwen observation workflow: approved input
projection → exactly five source-bound observations → human accept/edit/reject → revision-CAS
Draft update. The model has no publish route. Other packages remain fully usable through
deterministic typed authoring and clearly show that no Studio LLM profile is installed.

The runtime and Studio containers share only the immutable Semantic Change Request inbox
volume. This permits an Agent execution to submit an evidence-bound proposed request and
lets Studio display it without giving Runtime any ontology mutation authority.

The solution selector preserves the chosen package across both products. Direct Cash
Trading links are:

- `/ontology-agent/?solution=ontology.exchange_analytics.cash_trading`
- `/ontology-studio/?solution=ontology.exchange_analytics.cash_trading`

External Reviewer confirmations are deliberately non-blocking for this PoC. A later answer is
recorded as a new source/decision and produces a new candidate version; it never silently
changes the active snapshot.

The expected bootstrap order is fixed: PostgreSQL migration → all installed synthetic
semantic releases build → exact release/snapshot S3 publish and read-back → PostgreSQL registration →
atomic active-head/context commit → solution component/identity verification → exact
solution registration commit → PostgreSQL/S3 workspace bootstrap and exact read-back →
API readiness → web traffic. MinIO must be healthy before the lifecycle bootstrap starts.

The Compose profile mounts `nginx.compose.conf`, which re-resolves recreated service
containers through Docker DNS. The image-default `nginx.conf` is retained for Kubernetes,
where stable Service ClusterIPs provide the upstream boundary. Web readiness traverses
both runtime-context and Studio-workspace checks; a static-page-only 200 is not considered
ready.

Alembic `20260820_0005` adds one mutable `studio_workspace_head` and immutable
`studio_draft_revision` history. The head uses an exact expected-subject CAS. Each state
transition writes canonical bytes to S3 and only then advances PostgreSQL authority; a
database or exact-object read failure returns HTTP 503 rather than falling back to the
legacy workspace file.

Alembic `20260820_0007` adds the separate mutable solution directory. It supports
rename/description/owner edits plus archive, restore and delete-tombstone transitions.
Archiving is refused while the solution has an active runtime; deletion is allowed only
after archive and only when no release history exists. Immutable packages, exact
artifacts and audit history are never silently rewritten or erased by directory actions.

The current catalog registration is `1.3.0`, while its semantic source remains `1.2.0`.
Those identities are deliberately separate: changing the Authoring Profile/editor must
not pretend the semantic source changed. Prior exact registrations remain retained as
history but the product view opens only the latest registration.

## Stop

```bash
docker compose --env-file .env down
```

Do not use `down --volumes` unless the product-state and artifact data are intentionally disposable.

## Lifecycle operations

The operator surface keeps publication, preparation and activation separate. Activation
uses an exact expected-current compare-and-swap; rollback is the same operation with an
older exact snapshot as the target. PostgreSQL is the only active-head authority when
`ONTOLOGY_LIFECYCLE_STATE_MODE=postgresql-s3`; a stale filesystem pointer cannot win.

Artifact cleanup is dry-run by default and preserves both committed exact versions and
recent uncommitted versions inside the one-hour minimum lease window:

```bash
docker compose --env-file .env exec agent-control \
  ontology-agent gc-lifecycle-artifacts --grace-seconds 86400
# Add --delete only after reviewing orphan_candidates.
```

## Kubernetes

The Helm chart is in `chart/`. Its default values are the single-node, self-contained
demo profile with PostgreSQL and MinIO. `chart/values-managed.yaml` disables both
StatefulSets, uses the exact database URL and AWS S3 credentials from the product-state
Secret, and permits only explicitly configured external egress. Replace its example
private CIDR with the actual VPC endpoint CIDRs before deployment.

The chart includes the internal model-gateway, solution activation ConfigMap and a
gateway-only HTTPS egress policy. The default provider CIDR is intentionally broad for
the isolated PoC and must be replaced by an approved egress proxy or exact ranges for a
client environment. Static chart checks are not an EC2/k3s installation or rollback
rehearsal.
