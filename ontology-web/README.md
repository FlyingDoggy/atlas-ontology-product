# Atlas Ontology Products Web

React/Vite desktop shell for the two user-visible products:

- `/ontology-agent/`
- `/ontology-studio/`

The browser owns no semantic or release authority. It validates the backend-owned
`ProductContextV1` with Zod, renders only safe typed fields, and fails visibly when the
PostgreSQL active index or exact S3 artifact cannot be verified.

The Studio route additionally reads `/control/solutions` and the selected solution's
`/control/workspaces/{id}/editor` contract. It renders the latest exact registration,
four closed component classes and a descriptor-driven draft editor. Field paths, labels,
controls and closed options come from the verified Authoring Profile; React contains no
ADT formula or physical-field branch. Saving uses expected-revision operations, validation
is backend-owned, and publication never activates a runtime snapshot.

The same selector now drives the Agent route through `/api/solutions/{solution_id}`.
Each installed solution contributes its own question family, active ontology, runtime identity
and scenario adapter. The first two packages are ADT and Cash Trading; adding a third package
must not require a new React calculation branch.

## Local checks

Use Node 24:

```bash
npm ci
npm test
npm run build
```

The production image uses the static Kubernetes Nginx configuration. The local Compose
profile mounts `nginx.compose.conf` so recreated containers are re-resolved through
Docker DNS. Its probe-only port 8081 traverses runtime readiness and is never published
by the public Service/host mapping.

The end-to-end test expects the real durable-lifecycle Compose stack at
`127.0.0.1:18080`. It
checks the login redirect, issues a test-only signed session inside the auth container,
loads the exact PostgreSQL/S3 context, follows Agent→Studio navigation, verifies the
durable editor contract and rejects browser console errors.
