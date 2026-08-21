# Common Ontology Product + ADT Solution — Vertical-Slice Implementation Plan

Status: Approved for implementation — Phase 1 and Phase 2 local tracers complete; generic Studio slice next; target k3s smoke pending

Decision source: `ontology-product-group/17_architecture_approval_and_stack_decision.md`

## Objective

Turn the current ADT-specific demo into one deployable common product build plus independently delivered solution components. The same build must first preserve ADT, then be falsified by a materially different synthetic Listing scenario.

The implementation baseline is fixed:

- Frontend: TypeScript strict, React, Vite, React Router, TanStack Query, Zod boundary validation;
- Backend: Python, FastAPI, Pydantic;
- Product state: PostgreSQL 17, SQLAlchemy 2, Alembic, psycopg 3;
- Immutable artifacts: S3-compatible exact-version storage; MinIO for local/test and AWS S3-compatible configuration for deployment;
- Fact analytics: content-addressed Parquet and DuckDB, or a future `QueryEnginePort` adapter;
- Deployment: Kubernetes; k3s for the current single-EC2 demo and Helm-compatible configuration for standard Kubernetes;
- LLM: internal model gateway and Qwen `qwen3.8-max` under the existing closed projection/profile/commit boundaries.

## Durable decisions

- User-visible products remain Ontology Studio and Ontology Analytic Agent. Operator APIs and the shared kernel are not third products.
- PostgreSQL stores product state and evidence metadata, not customer fact tables.
- S3 versioning and digest prove artifact identity, not semantic truth or release authority.
- Browser authority is zero. React renders backend-owned state and typed safe descriptors.
- Scenario code/config may define domain vocabulary, metrics, mappings, controls and presentation descriptors; it may not inject arbitrary executable code, system prompts or policy.
- The current ADT calculator, oracle, release lifecycle and answer path remain the regression baseline. No second truth path is permitted.
- Compose, filesystem and SQLite are compatibility/migration paths only. New product authority is PostgreSQL + S3-compatible storage.
- A Kubernetes deployment is not a claim of HA, SLA, IAM or HKEX production readiness.

## Phase 1 — New-infrastructure ADT tracer

### User outcome

A desktop user logs in, opens `/ontology-agent/`, sees the exact active ADT context/snapshot, and can jump to `/ontology-studio/`. The page is served by the new React build; the context is read from the real backend; product state is persisted in PostgreSQL; the referenced immutable context artifact is stored and read back through S3/MinIO; the same deployment can run on local Compose for development and k3s for the EC2 demo.

### Work

- [x] Characterize current `/api/runtime/active`, `/api/ontology`, login and cross-product navigation responses.
- [x] Create the React/Vite TypeScript application without deleting the legacy console.
- [x] Add `/ontology-agent/` and `/ontology-studio/` route shells plus a shared safe navigation component.
- [x] Add typed `ProductContextV1` client boundary; reject unknown/missing required fields rather than guessing.
- [x] Add SQLAlchemy/Alembic infrastructure and PostgreSQL health/readiness integration.
- [x] Add minimal Alembic schema, solution registration, immutable context version and active-context read model.
- [x] Add repository ports with PostgreSQL implementations; retain the existing file path only as an explicit legacy-compatibility source.
- [x] Add `ArtifactStorePort` with S3/MinIO implementation: digest/size verify, versioning, exact-version read-back and committed reference.
- [x] Import the existing active ADT context into PostgreSQL/S3 idempotently; do not modify the existing release/runtime files.
- [x] Add MinIO/PostgreSQL to the development deployment and Kubernetes manifests/Helm-compatible values for web/API/PostgreSQL/MinIO dependencies.
- [x] Preserve current public route prefixes and keep operator/model services non-public.

### Acceptance

- [x] Existing backend tests and ADT validator remain green.
- [x] A clean environment imports ADT exactly once; repeated import is idempotent.
- [x] PostgreSQL restart and API restart preserve the same active context.
- [x] Object read-back verifies exact version, digest and size; mismatch is fail-closed.
- [x] React build, typecheck and desktop E2E pass against real APIs with browser fallback/calculation count zero.
- [x] Local container stack becomes healthy; self-contained and managed-service Kubernetes renderings pass strict static validation.
- [ ] Run and record the same chart on the target EC2/k3s ingress without replacing the currently shared demo unintentionally.
- [x] Failure of PostgreSQL or object storage shows a typed degraded/unavailable state and does not invent an active context.
- [x] The legacy console and its deployment remain untouched and independently deployable.
- [ ] Rehearse the explicit target-environment rollback operation before replacing the shared demo.

### Phase 1 evidence — 2026-08-20

- Backend: 126 tests passed; the one warning is an upstream Starlette/httpx deprecation.
- Semantic package: all 33 validation checks passed.
- Frontend: 3 contract tests, TypeScript check and production build passed.
- Browser: anonymous login redirect, authenticated Agent view, exact PostgreSQL/S3 context, Studio link and zero console errors passed against the real Compose stack.
- Persistence: repeat bootstrap remained idempotent with table counts `1|1|1`; PostgreSQL, MinIO and runtime restarts retained subject checksum `050d1c73…310d262a` and exact object version `b14d036c…688744`.
- Failure behavior: PostgreSQL outage returned typed 503 in 0.07s; object-store outage returned typed 503 in 2.12s; both recovered to the same exact context.
- Deployment: ARM64 backend and web images built; Helm lint passed; Kubernetes 1.34 strict schemas passed for 20 self-contained resources and 16 managed-service resources.
- Upgrade path: after a runtime container/IP replacement, Docker DNS re-resolution and desktop E2E passed without recreating the web container.

## Phase 2 — PostgreSQL/S3 release lifecycle tracer

### User outcome

An operator can publish, prepare, activate and roll back an ADT release while the user sees only the committed active version. A failed candidate never replaces the previous active version.

### Work

- [x] Persist solution/release/runtime/activation envelopes and heads in PostgreSQL with an exact expected-current CAS.
- [x] Store release/runtime bytes in versioned S3-compatible storage with digest/size/exact-version read-back before database commit.
- [x] Add Alembic migrations, capture the initial import as release/snapshot/context plus activation event, and cut active-head authority to one PostgreSQL mode switch.
- [x] Port existing `release -> prepare -> certify -> activate` APIs behind repositories without changing their external semantics.
- [x] Implement explicit rollback and stale-expected-head conflicts.
- [x] Add dry-run-first orphan cleanup with a shared/exclusive commit-GC lock and minimum lease window so committed or in-flight artifacts cannot be removed.

### Acceptance

- [x] Clean, retry, crash-between-object-and-DB classification, stale CAS and rollback tests pass.
- [x] Exact previous active remains serviceable after candidate failure.
- [x] There is one active-head authority; filesystem/SQLite cannot silently win after cutover.
- [x] ADT 8-case golden suite, 33 package checks and current execution/evidence outputs remain equivalent.

### Phase 2 evidence — 2026-08-20

- The lifecycle schema is defined through Alembic `20260820_0003`; the running demo contains four exact releases, four exact snapshots, one active head and an append-only activation journal. The lifecycle head and active product context are transactionally aligned.
- The same active release and snapshot were reconstructed from PostgreSQL refs plus exact S3 versions into an empty local cache; filesystem active pointers are ignored in durable mode.
- A real API round trip switched from `1.2.0` to `1.2.1` and rolled back to the exact original snapshot; a stale expected-current request returned HTTP 409 and did not change the head.
- Two concurrent activations with one expected head produced one winner and one conflict. The original snapshot was restored afterwards.
- MinIO and PostgreSQL outage probes each returned typed HTTP 503; recovery returned the same snapshot and generation rather than falling back to local state.
- Artifact GC dry-run classified 8 exact lifecycle versions as committed, 0 leased and 0 orphaned, and deleted 0. Unit coverage also verifies the crash-window case: recent uncommitted versions remain leased and old unreferenced versions alone become candidates.
- The ADT suite returned 8/8 PASS, including four answered cases and four boundary outcomes. The semantic package remained 33/33 PASS, desktop browser E2E passed, and default/managed Kubernetes renderings remained 20/20 and 16/16 valid.

## Phase 3 — Generic Studio tracer

### User outcome

A Studio user opens the ADT solution, reviews registered source material, accepts/edits/rejects observations, updates a draft and publishes a portable semantic release without any ADT-specific branch in Studio product code.

### Work

- [x] Add a non-authoritative exact solution registration and closed four-class component inventory; verify component bytes and cross-component semantic identity before catalog commit.
- [x] Persist the selected workspace head and immutable draft revisions through PostgreSQL CAS plus exact S3 artifacts; keep legacy files only as an isolated-test/migration adapter.
- [ ] Promote component bytes to independently addressable artifacts and add the non-authoritative distribution manifest/install boundary.
- [ ] Move ADT intake registry, vocabulary, metrics, mappings, controls and safe descriptors into the ADT solution area.
- [ ] Replace fixed workspace constants with solution/workspace repositories and typed component resolution.
- [ ] Keep LLM output as observations/proposals tied to exact allowed sources and human decisions.
- [x] Add a solution-aware catalog API and React Studio view using only backend-owned, Zod-validated registrations.
- [x] Add solution-aware workspace/editor routes and descriptor-driven React forms over the repository boundary.

### Acceptance

- [ ] Product code has no ADT metric/formula/field constants outside explicit compatibility tests.
- [ ] Missing/unknown component versions fail before publication.
- [ ] Observation provenance, human decisions, draft CAS and release digest are persisted and reviewable.
- [ ] ADT Studio flow reaches the same semantic result as the current reference path.

### Phase 3 slice 1 evidence — 2026-08-20

- `ontology-solution-registration/v1` registers the ADT solution, workspace and exact `authoring_profile`, `semantic_source`, `agent_experience` and `reference_evaluation` component descriptors. It explicitly has no release or activation authority.
- Alembic `20260820_0004` persists the registration in PostgreSQL and its canonical subject as an exact S3 version. Repeated bootstrap is idempotent and exact read-back is mandatory.
- The catalog gate verifies each component digest and joins solution ID, solution version, scenario identity and bilingual display name back to the semantic source. A real mismatched scenario identity was detected during E2E and converted into a permanent regression test.
- `/control/solutions` and the React Studio page now render the installed component set without ADT formula/field logic in the browser. Desktop E2E validates the backend catalog, exact artifact and Agent↔Studio navigation.
- PostgreSQL or S3 loss returns Studio HTTP 503 and web readiness 503; recovery returns the same exact registration. Intake assets and ADT draft translation remain scenario/filesystem-specific, so Phase 3 is not complete.

### Phase 3 slice 2 evidence — 2026-08-20

- Alembic `20260820_0005` adds a PostgreSQL workspace head/generation and immutable draft-revision index. Canonical state/revision subjects are stored as exact S3 versions and read back before use.
- `studio-editor-descriptor/v1` is the exact ADT Authoring Profile. Its five fields close the existing semantic-slot manifest; labels, controls, allowed values and operations are no longer embedded in React.
- Solution registration `1.3.0` explicitly binds semantic source `1.2.0`, fixing the previous identity overload: Authoring Profile evolution no longer claims the semantic source changed. Prior exact registration remains history and the UI selects only the newest registration.
- The real PostgreSQL 17/MinIO flow opened revision 1, committed revision 2, rejected a stale revision-1 operation with HTTP 409, validated PASS and published semantic release `1.2.4` without activation. PostgreSQL showed generation 4 and two immutable draft revisions.
- Studio restart preserved the exact workspace head. PostgreSQL and MinIO outage probes each returned Studio HTTP 503 and failed web readiness; recovery restored the identical head.
- Integrated evidence is now 143/143 backend tests, 33/33 semantic/data/SHACL checks, 7/7 frontend contract tests, TypeScript/build PASS, 8/8 ADT cases and desktop E2E PASS with zero console errors.

## Phase 4 — Generic Agent tracer

### User outcome

The Agent renders an ADT Dashboard and answers registered ADT questions using a scenario-neutral product path, with typed claims and evidence.

### Work

- [ ] Define bounded `AgentExperienceProfile`, dashboard and question-family descriptors.
- [ ] Make Dashboard, Ask and Evidence views descriptor-driven.
- [ ] Route analysis through capability/operator resolution, not solution-name branching.
- [ ] Keep deterministic SQL/numbers/claims in backend; LLM performs only allowed goal/tool selection and wording realization.
- [ ] Add explicit unsupported/clarify/refused UI outcomes.

### Acceptance

- [ ] React source contains no ADT physical fields, formula or browser calculator.
- [ ] Model-off deterministic path and active Qwen registered-question path both pass.
- [ ] No-partial behavior, evidence projection and secret/error redaction pass.
- [ ] Legacy UI parity is proven and the rollback switch can be retired deliberately.

## Phase 5 — Listing falsifier

### User outcome

The same product images install and open a materially different synthetic Listing SLA/Backlog solution. Its priority analysis either succeeds through existing common capabilities or returns a precise pre-query `MissingCapability` result.

### Work

- [ ] Preregister the Listing business question, truth/control, data identity and legal outcomes before fixture implementation.
- [ ] Build Listing solution components without modifying common code during the first run.
- [ ] Run install, Studio context, Dashboard and one priority Ask path.
- [ ] Record all proposed common changes in a scenario/common diff ledger.

### Acceptance

- [ ] Same frozen product build runs both solutions.
- [ ] A missing capability causes query/model invocation count zero and does not weaken policy.
- [ ] No Listing-specific branch appears in product code.
- [ ] Portability remains unproven if either scenario requires hidden common changes.

## Phase 6 — Dual-scenario factorization

### User outcome

Maintainers can add or change either solution without modifying the other, and only demonstrated shared primitives exist in the kernel.

### Work

- [ ] Promote only primitives required by both ADT and Listing.
- [ ] Freeze component schemas, compatibility rules and migration behavior.
- [ ] Add solution scaffold/lint/build/diff/test commands for core engineers.
- [ ] Add two-solution conformance and clean-build matrix.

### Acceptance

- [ ] ADT and Listing install/run independently from exact components.
- [ ] Unknown component/schema/capability fails closed with actionable path-specific errors.
- [ ] The same component bytes yield deterministic canonical outputs.
- [ ] No raw solution bundle is reachable by Agent runtime identity.

## Phase 7 — Kubernetes release slice

### User outcome

The approved engineering demo is repeatably deployable to the current EC2/k3s environment at stable `/ontology-studio/` and `/ontology-agent/` paths with HTTPS/shared demo login and documented rollback.

### Work

- [ ] Package services and configuration as Helm-compatible Kubernetes resources.
- [ ] Define migration job ordering, secret references, network policy, service accounts, probes and resource budgets.
- [ ] Rehearse clean install, in-place upgrade, database migration, object-store failure, process restart and rollback.
- [ ] Run desktop end-to-end tests through the public ingress.
- [ ] Produce operator runbook and exact engineering-demo claim text.

### Acceptance

- [ ] Clean install and in-place upgrade yield the same active solution and checksums.
- [ ] Failed migration/image/readiness does not switch public traffic to an invalid version.
- [ ] Rollback restores the previous image and exact active solution without reverting to stale authority.
- [ ] Public routes, login, Studio↔Agent links and registered ADT flow pass desktop E2E.
- [ ] Release label remains constructed-synthetic Engineering Demo; HA/SLA/IAM/HKEX readiness are explicitly excluded.

## First implementation boundary

Phase 1/2 and the first two Phase 3 slices now provide the infrastructure, durable lifecycle, exact solution catalog and a real durable Studio editor without creating a second ADT truth path. The next implementation boundary remains Phase 3: move intake/observation/decision state behind the same product repositories, finish adapter-owned semantic compilation, then add independently promoted/installable component artifacts. Target EC2/k3s replacement remains a separate, explicit deployment action.
