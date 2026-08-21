# Atlas ADT Demo Edition

Single-host Docker Compose release for a constructed synthetic ADT demonstration. It is a demo product surface, not an HKEX-validated system and not a production security baseline.

## Product surfaces

- `/ontology-agent/` — ADT decision dashboard and governed question answering.
- `/ontology-studio/` — ontology governance plus an AI-assisted source-to-decision review workbench.
- `/` — redirects to `/ontology-agent/`; it does not host a third product surface.
- `/api/*` — governed analytic Agent runtime.
- `/control/*` — Studio draft, validation and release control plane.
- `/agent-control/*` — prepare, certify, activate and verify control plane.

## Analysis engine and LLM status

This release has two deliberately different analysis paths:

- **ADT overview** is deterministic: ontology-bound analysis contract → governed SQL/operator execution → claims/evidence → dashboard. It does not depend on Qwen.
- **Ask the Agent** uses Alibaba Cloud Model Studio `qwen3.8-max` to bind a registered natural-language question to a closed goal and choose the next permitted tool. All numbers and factual clauses still come from snapshot-bound deterministic tools and a closed answer renderer.

Ontology Studio has a third, deliberately non-analytic model task:

- **AI intake review** sends four approved fragments from the constructed-synthetic ADT transcription to `qwen3.8-max` under a five-slot manifest. The result is an immutable `ObservationSet`, not ontology truth. A named human reviewer must accept, edit or reject every slot before a single CAS-protected draft revision can be created. Validation, publication, runtime preparation and activation remain separate actions; there is no LLM publish route.

The public Engineering Demo accepts four server-registered, constructed-synthetic question cases only. Arbitrary pasted text is not sent to Qwen. Answers are held in a private buffer and become visible only after profile, rollout, snapshot, egress and obligation checks complete and an `EngineeringDemoResponseCommit` is written. Provider/schema/tool/deadline/revocation failures release no partial analytic bytes.

The Qwen key is mounted only into the internal `model-gateway` container. It is absent from the browser, Console, runtime, Studio, Agent-control, bootstrap and auth services; port 8794 is not published. Agent model input excludes SQL, physical table/column names, mappings, source locators, credentials and raw rows. Studio model input contains only the four approved text fragments, their approved source anchors, current typed values and the five-slot contract; registered SQL, data model and data dictionary files are never projected.

The exact release label is: **LLM Engineering Demo — constructed-synthetic ADT; bounded engineering controls; not Stage 1 governed-evidence conformant; not HKEX validated; not production-ready.**

All browser calls use the same public origin. The Console binds only to host loopback, the Python services remain on the Compose network, and an outbound Cloudflare Quick Tunnel provides the temporary public HTTPS address. A mobile-friendly sign-in page exchanges the shared credential for a signed `Secure`, `HttpOnly`, `SameSite=Lax` session cookie. Nginx verifies that session before serving either product or any of the three API surfaces.

## Start

```bash
cp .env.example .env
mkdir -p secrets/llm
cp config/llm/qwen.env.example secrets/llm/qwen.env
# Replace the placeholder in secrets/llm/qwen.env, then chmod 600 it.
docker compose build
docker compose up -d --wait
docker compose ps
```

`secrets/` is ignored by source control. Each active LLM task requires its exact egress decision, run profile, frozen evaluation manifest and rollout record under `config/llm/`; a missing, expired or mismatched artifact fails closed. Studio additionally pins the prompt manifest, projection policy and five-slot manifest by digest.

The one-shot `bootstrap` service creates and certifies the base ADT snapshot only when no active snapshot exists. A later Studio release is never semantically rolled back. If a software upgrade makes the existing runtime build incompatible, bootstrap prepares the same active semantic release with the new adapter build and atomically switches to that rebuilt snapshot.

For a target host with restricted or very slow PyPI access, the release pipeline can pre-download the lockfile's platform wheels into `ontology-agent-poc/wheelhouse/` and build with `ontology-agent-poc/Dockerfile.offline`. The target build then performs no package-index access. The wheelhouse is a generated release artifact, not source material.

On a host whose installed Compose expects a newer Buildx plugin, build the two tagged images without changing the host-wide Docker installation, then let Compose start them without rebuilding:

```bash
DOCKER_BUILDKIT=0 docker build \
  -f ../../ontology-agent-poc/Dockerfile.offline \
  -t ontology-adt-demo-backend:${ONTOLOGY_DEMO_VERSION:-0.3.0-studio-llm-demo.1} \
  ../../ontology-agent-poc
DOCKER_BUILDKIT=0 docker build \
  -t ontology-adt-demo-console:${ONTOLOGY_DEMO_VERSION:-0.3.0-studio-llm-demo.1} \
  ../../ontology-console
docker compose up -d --no-build --wait
```

No EC2 web ingress rule is required. This is important for an AWS China Internal Access Account, where common public internet ports are blocked until ICP recordal is complete. The tunnel uses outbound connectivity instead of exposing the origin IP.

Get the current public hostname from the tunnel log:

```bash
docker compose logs --no-color tunnel \
  | sed -nE 's#.*(https://[a-z0-9-]+\.trycloudflare\.com).*#\1#p' \
  | tail -1
```

Quick Tunnel is suitable for this PoC, but its hostname changes if the tunnel container is recreated and it has no uptime SLA. A stable customer-facing URL requires a named tunnel with a controlled domain, a non-China public ingress, or completion of the relevant ICP process.

## Verify

```bash
curl --fail http://127.0.0.1:${ONTOLOGY_DEMO_LOCAL_PORT:-8080}/healthz
cookie_jar=$(mktemp)
curl --fail --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"$ONTOLOGY_DEMO_USERNAME\",\"password\":\"$ONTOLOGY_DEMO_PASSWORD\"}" \
  "$ONTOLOGY_DEMO_PUBLIC_URL/auth/login"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/api/readyz"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/api/llm/status"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/api/llm/questions"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/control/readyz"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/control/workspaces/workspace.adt.reference/llm/status"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/control/workspaces/workspace.adt.reference/llm/observations"
curl --fail --cookie "$cookie_jar" "$ONTOLOGY_DEMO_PUBLIC_URL/agent-control/readyz"
```

The non-mutating browser release check can be run from a workstation that has Playwright installed:

```bash
ONTOLOGY_CONSOLE_URL="$ONTOLOGY_DEMO_PUBLIC_URL/ontology-agent/" \
  ONTOLOGY_UNAVAILABLE_API="$ONTOLOGY_DEMO_PUBLIC_URL/unavailable-runtime" \
  ONTOLOGY_DEMO_USERNAME="$ONTOLOGY_DEMO_USERNAME" \
  ONTOLOGY_DEMO_PASSWORD="$ONTOLOGY_DEMO_PASSWORD" \
  node ../../ontology-console/deployment_smoke_test.mjs
```

The Studio LLM smoke intentionally creates one immutable ObservationSet, rejects all five proposals and verifies that the ontology draft did not change:

```bash
ONTOLOGY_CONSOLE_URL="$ONTOLOGY_DEMO_PUBLIC_URL" \
  ONTOLOGY_DEMO_USERNAME="$ONTOLOGY_DEMO_USERNAME" \
  ONTOLOGY_DEMO_PASSWORD="$ONTOLOGY_DEMO_PASSWORD" \
  python ../../ontology-console/tests/studio_deployment_smoke.py
```

## Operate

```bash
docker compose logs --tail=200
docker compose restart model-gateway runtime studio agent-control auth console
docker compose run --rm --no-deps bootstrap
docker compose down
```

Restarting the `tunnel` service assigns a new public hostname, so do that only when a URL change is acceptable. To stop model traffic immediately, set the rollout to `off` or stop `model-gateway`; the deterministic dashboard remains independent. The bootstrap recheck must report `ALREADY_INITIALIZED` or `PRESERVED_EXISTING_ACTIVE`; it must never roll back a later active release. `docker compose down` preserves the three named volumes. Do not add `--volumes` unless intentionally resetting all demo releases, Studio revisions and execution evidence.

## Deliberately out of scope

- individual IAM, SSO, MFA and per-user audit
- stable public-domain ownership and production ingress SLA
- customer data connectors or HKEX environment approval
- arbitrary public free-text egress or customer material sent to Qwen
- generic document upload/parsing, customer-material egress or automatic ontology publication
- multi-node replicas and distributed state
- full Shared Contract VRS/ResultReleaseCommit conformance
- claims that the constructed ADT logic is HKEX-confirmed

The fixed `MarketAnalyst` role demonstrates ontology policy behavior only. The demo should be exposed for controlled sessions, not treated as an internet-facing production application.
