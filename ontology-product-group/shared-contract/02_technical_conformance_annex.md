# Shared Product Contract — Technical & Conformance Annex

Annex ID：`shared-contract-technical-profile/0.1`  
状态：Approved/Frozen  
日期：2026-08-18  
批准记录：随 Shared Product Contract v0.1 于 2026-08-19 冻结  
Normative parents：`../02_shared_product_contract.md`、`01_synthetic_trusted_flow_core.md`

## 1. Purpose and Precedence

本 Annex 把 Core 的产品结果变成可复现的 identity、schema、algorithm 和 test obligations。它是 Stage 1 implementation/conformance authority，但不得改变 Core 的产品含义或扩大 Synthetic Profile 的支持范围。

Precedence：Core > Stage Profile > Annex > implementation ADR/code。冲突时高层优先；未知 schema/profile/version fail closed。

本文使用 `MUST` 的内容是 Stage 1 normative；标为 Near-term 的内容只冻结未来兼容语义，不计入 Stage 1 conformance claim。

## 2. Closed Type System

### 2.1 Identifier grammar

Stage 1 identifier MUST match：

```text
^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$
```

版本 MUST 是非空、NFC、无空白的 ASCII label；不得用 `latest`、`current`、`*` 或 range 作为 identity-bearing version。Digest grammar：

```text
^sha-256:[0-9a-f]{64}$
```

### 2.2 Scope types

| Type | Exact fields | Usage |
|---|---|---|
| `GovernanceScopeV1` | `tenant_id`, `workspace_id` | ClearedInput, GSR, SCR |
| `RuntimeScopeV1` | `tenant_id`, `workspace_id`, `environment_id` | payload, VRS, gate subjects |
| `ChannelScopeV1` | `tenant_id`, `workspace_id`, `environment_id`, `channel` | Activation, Eligibility, Execution, Revocation record |

All fields are required canonical identifiers. No wildcard scope exists in Stage 1.

### 2.3 Full reference

`ScopedObjectRefV1` is closed and contains exactly：

| Field | Type |
|---|---|
| `object_type` | canonical identifier |
| `object_id` | canonical identifier |
| `object_version` | canonical version label |
| `contract_version` | `shared-product-contract/0.1` |
| `subject_schema` | canonical schema identifier/version |
| `canonicalization_profile` | `canonical-json-v1.0` |
| `scope` | exact applicable Scope object |
| `subject_digest` | digest grammar above |

Refs used as execution or authority evidence MUST use all fields. An `OpaqueLocatorRef` may hide a source/interaction location but is never integrity or authorization proof.

### 2.4 Decimal and timestamp

Business decimals MUST use closed `DecimalValueV1`：

```text
coefficient: string matching ^(?:0|-?[1-9][0-9]*)$
scale: integer in [0, 18]
```

Value = coefficient × 10^-scale. `-0`, plus sign, exponent, leading zero and implicit scale are forbidden. Scale is semantic: `{"coefficient":"10","scale":1}` and `{"coefficient":"100","scale":2}` may represent the same mathematical value but are different subjects unless an object schema separately normalizes them before subject construction.

Subject timestamps MUST be UTC millisecond RFC3339：

```text
YYYY-MM-DDTHH:mm:ss.SSSZ
```

Offsets including `+00:00`、missing milliseconds、leap seconds、invalid calendar date and year outside 0001–9999 are rejected. Adapters normalize source timestamps before building a DigestSubject；canonicalizer does not guess.

## 3. DigestSubject and Envelope

### 3.1 Base DigestSubject

Every object-specific subject begins with exactly：

| Field | Rule |
|---|---|
| `subject_schema` | exact schema/version from §4 |
| `contract_version` | `shared-product-contract/0.1` |
| `canonicalization_profile` | `canonical-json-v1.0` |
| `object_type` | exact type from §4 |
| `object_id` | stable logical ID |
| `object_version` | explicit immutable version/record sequence label |
| `scope` | exact scope type declared by schema |

Object-specific fields follow. Schemas are closed；unknown field, duplicate key, missing required field or wrong type is rejected before hashing.

### 3.2 DigestEnvelope

The generic envelope contains：

| Field | Digest treatment |
|---|---|
| `subject` | canonicalized and hashed |
| `subject_digest` | calculated result；excluded from subject preimage |
| `created_at` | envelope metadata；excluded from subject digest |
| `created_by_principal_ref` | envelope provenance；excluded from subject digest unless object-specific committed subject references it |
| `storage_locator_ref` | excluded；never authority |
| `signature_refs` | excluded；signatures bind subject digest |
| `audit_index_refs` | excluded；indexes bind committed record |

If an Envelope itself is content-addressed, implementation MUST define a separate `EnvelopeDigestSubject` containing the subject ref/digest plus all committed envelope fields except its own envelope digest/signatures. It MUST NOT reuse the object subject digest as envelope digest.

### 3.3 Domain-separated digest

For subject schema `S` and canonicalization profile `P`：

```text
preimage = UTF8("spc-v0.1")
           || 0x00
           || UTF8(P)
           || 0x00
           || UTF8(S)
           || 0x00
           || canonical_json_bytes(subject)

subject_digest = "sha-256:" + lowercase_hex(SHA256(preimage))
```

`P` and `S` are also fields inside the subject. This deliberate duplication prevents cross-schema/profile substitution and makes the domain boundary auditable.

## 4. Object-Specific Digest Subjects

“Set” means array items MUST already be unique and sorted by their own canonical JSON bytes；unsorted or duplicate input is rejected. “Ordered” means array order is semantic and preserved.

### 4.1 Intake and semantic publish

| Schema / object type / scope | Required object-specific fields | Explicitly excluded |
|---|---|---|
| `cleared-input-proposal-subject/1` / `cleared-input-proposal` / Governance | `classification`, `origin`, `allowed_uses` Set, `safe_content_ref`, `opaque_source_locator_ref`, `limitations` Set | disclosure approval, created/published time |
| `cleared-input-subject/1` / `cleared-input` / Governance | `proposal_ref`, `input_disclosure_authority_decision_ref` | later revocation/expiry view, storage locator, envelope time |
| `gsr-publish-subject/1` / `gsr-publish-subject` / Governance | `semantic_version`, `semantic_schema_ref`, `semantic_content_ref`, `cleared_input_refs` Set, `decision_refs` Set, `required_capability_refs` Set, `binding_requirements_ref`, `policy_requirements_ref`, `disclosure_labels_ref`, `supersedes_ref` nullable | semantic approval, publisher, publish time, GSR digest |
| `governed-semantic-release-subject/1` / `governed-semantic-release` / Governance | `publish_subject_ref`, `semantic_approval_attempt_ref`, `publish_authority_decision_ref` | envelope publisher/time, later deprecation records |

ClearedInput disclosure approval is an ALLOW AuthorityDecision that references the proposal digest；the final ClearedInput subject then references both proposal and decision. This two-step form prevents a cycle while making downstream lineage bind the exact approved pair. It is not one of the five product gates.

### 4.2 Runtime payload and truth/data artifacts

| Schema / object type / scope | Required object-specific fields | Explicitly excluded |
|---|---|---|
| `runtime-snapshot-payload-subject/1` / `runtime-snapshot-payload` / Runtime | `gsr_ref`, `runtime_semantic_projection_ref`, `binding_bundle_ref`, `projection_policy_bundle_ref`, `runtime_capability_manifest_ref`, `data_identity_ref`, `control_manifest_ref`, `suite_manifest_ref`, `reference_manifest_ref`, `oracle_provenance_ref`, `evaluation_runner_manifest_ref`, `compatibility_profile_ref`, `projection_profile_ref` | channel, attempt refs, build/READY/REJECTED status, activation, timestamps |
| `data-identity-subject/1` / `data-identity` / Runtime | `dataset_manifest_ref`, `schema_digest`, `partition_identity_refs` Set, `row_count`, `source_engine_ref`, `transformation_ref`, `policy_scope_ref`, `frozen_at`, `replay_level` | raw rows, credentials, mutable watermark pointer |
| `reference-manifest-subject/1` / `reference-manifest` / Governance | `reference_case_id`, `cleared_input_ref`, `control_manifest_ref`, `suite_manifest_ref`, `oracle_provenance_ref`, `frozen_at` | fixture/runtime outputs |
| `control-manifest-subject/1` / `control-manifest` / Governance | `reference_case_id`, `oracle_class`, `oracle_provenance_refs` Set, `formula_ref`, `period_profile_ref`, `population_profile_ref`, `unit_ref`, `rounding_profile_ref`, `expected_result_refs` Ordered, `tolerance_profile_ref`, `expected_value_author_ref`, `fixture_author_ref`, `reviewer_ref`, `truth_frozen_before_fixture`, `allowed_claims` Set, `limitations` Set, `frozen_at` | actual runtime result |
| `suite-manifest-subject/1` / `suite-manifest` / Governance | `suite_id`, `cases` Ordered, `denominator`, `status_counts`, `mutation_profile_ref`, `frozen_at` | post-run relabel/deletion |

`row_count` and `denominator` are non-negative safe integers. Stage 1 `replay_level` is exactly `evidence_only`.

### 4.3 Gate subjects

| Schema / object type / scope | Exact object-specific fields |
|---|---|
| `semantic-approval-subject/1` / `semantic-approval-subject` / Governance | `gsr_publish_subject_ref`, `semantic_validation_profile_ref` |
| `binding-data-validation-subject/1` / `binding-data-validation-subject` / Runtime | `gsr_binding_requirements_ref`, `runtime_semantic_projection_ref`, `binding_bundle_ref`, `data_identity_ref`, `binding_validation_profile_ref` |
| `disclosure-policy-subject/1` / `disclosure-policy-subject` / Runtime | `gsr_disclosure_labels_ref`, `gsr_policy_requirements_ref`, `runtime_semantic_projection_ref`, `runtime_projection_schema_ref`, `user_projection_schema_ref`, `projection_transformer_ref`, `projection_policy_bundle_ref`, `audience_purpose_profile_ref`, `projection_fidelity_report_ref`, `disclosure_validation_profile_ref` |
| `runtime-capability-subject/1` / `runtime-capability-subject` / Runtime | `gsr_semantic_content_ref`, `gsr_capability_requirements_ref`, `runtime_semantic_projection_ref`, `runtime_capability_manifest_ref`, `provider_build_ref`, `input_schema_ref`, `output_schema_ref`, `failure_contract_ref`, `options_profile_ref`, `policy_obligations_ref`, `compatibility_profile_ref`, `projection_fidelity_report_ref`, `conformance_suite_ref` |
| `control-golden-subject/1` / `control-golden-subject` / Runtime | `runtime_snapshot_payload_ref`, `control_manifest_ref`, `suite_manifest_ref`, `reference_manifest_ref`, `oracle_provenance_ref`, `evaluation_runner_manifest_ref`, `evaluation_profile_ref` |

Gate subject object scope fields supply tenant/workspace/environment where applicable；channel is absent.

### 4.4 Verification, authority and seal

| Schema / object type / scope | Required object-specific fields | Excluded/cycle break |
|---|---|---|
| `gate-evaluation-subject/1` / `gate-evaluation` / gate scope | `gate_type`, `gate_subject_ref`, `outcome`, `evidence_refs` Set, `limitations` Set, `validity_mode`, `issued_at`, `expires_at` nullable | AuthorityDecision ref, own digest |
| `authority-decision-subject/1` / `authority-decision` / action scope | `action`, `trusted_session_ref`, `principal_ref`, `principal_registry_ref`, `role_assignment_ref`, `trust_epoch`, `purpose`, `proposed_action_subject_ref`, `policy_refs` Set, `obligations` Set, `decision`, `reason_codes` Set, `issued_at`, `expires_at` | committed action ref, own digest |
| `policy-decision-subject/1` / `policy-decision` / Channel | `principal_context_ref`, `purpose`, `resource_refs` Set, `policy_refs` Set, `input_context_digest`, `decision`, `reason_codes` Set, `obligations` Set, `evaluated_at`, `valid_until` | mutable policy state, execution/result ref, own digest |
| `verification-attempt-subject/1` / `verification-attempt` / gate scope | `gate_evaluation_ref`, `authority_decision_ref` | later VRS, own digest |
| `vrs-seal-proposal-subject/1` / `vrs-seal-proposal` / Runtime | `runtime_snapshot_payload_ref`, `verification_attempt_refs_by_gate` closed map of exactly five refs | seal AuthorityDecision, VRS digest/status |
| `verified-runtime-snapshot-subject/1` / `verified-runtime-snapshot` / Runtime | `seal_proposal_ref`, `seal_authority_decision_ref`, `seal_status` exactly `SEALED`, `limitations` Set | READY/eligibility/activation/expiry/revocation, envelope time |

`gate_type` is one of exactly：`SEMANTIC_APPROVAL`, `BINDING_DATA_VALIDATION`, `DISCLOSURE_POLICY_CLEARANCE`, `RUNTIME_CAPABILITY_COMPATIBILITY`, `CONTROL_GOLDEN_EVALUATION`.

`validity_mode` is `UNTIL`, `ONE_USE` or `UNTIL_REVOKED`; `UNTIL` requires `expires_at`, others require null. Stage 1 uses finite `UNTIL`; maximum policy duration is 30 days, but the chosen duration is environment policy rather than object identity default.

### 4.5 Lifecycle and execution

| Schema / object type / scope | Required object-specific fields | Excluded/cycle break |
|---|---|---|
| `activation-intent-subject/1` / `activation-intent` / Channel | `action` exactly ACTIVATE, `vrs_ref`, `expected_head_ref` nullable only for empty ledger, `expected_activation_epoch`, `idempotency_key`, `reason_code`, `requested_at` | authority/eligibility/record ref；Core DEACTIVATE is unsupported by this Profile |
| `activation-record-subject/1` / `activation-record` / Channel | `intent_ref`, `eligibility_decision_ref`, `authority_decision_ref`, `sequence`, `previous_record_ref` nullable, `activation_epoch`, `committed_at` | mutable head/cache |
| `revocation-intent-subject/1` / `revocation-intent` / Channel | `target_ref`, `enforcement`, `expected_head_ref` nullable, `expected_revocation_epoch`, `idempotency_key`, `reason_code`, `requested_at` | authority/record ref |
| `revocation-record-subject/1` / `revocation-record` / Channel | `intent_ref`, `authority_decision_ref`, `sequence`, `previous_record_ref` nullable, `new_revocation_epoch`, `committed_at` | UNREVOKE, mutable cache |
| `execution-eligibility-subject/1` / `execution-eligibility-decision` / Channel | `phase`, `purpose`, `vrs_ref`, `runtime_snapshot_payload_ref`, `verification_attempt_refs_by_gate`, `activation_head_ref`, `request_authority_decision_ref`, `policy_decision_ref`, `revocation_scope_epoch`, `observed_revocation_set_digest`, `evaluated_at`, `valid_until`, `decision`, `reason_codes` Set | VRS mutation, future reuse assumption |
| `user-projection-subject/1` / `user-evidence-projection` / Channel | `execution_id`, `projection_schema_ref`, `content_bytes_digest`, `renderer_ref`, `locale`, `timezone`, `unit_profile_ref`, `rounding_profile_ref`, `classification_ref` | raw internal result, network acknowledgement |
| `execution-evidence-subject/1` / `execution-evidence-envelope` / Channel | `execution_id`, `principal_context_ref`, `purpose`, `gsr_ref`, `vrs_ref`, `activation_record_ref`, `pre_query_eligibility_ref`, `policy_decision_ref`, `data_identity_ref`, `plan_ref` nullable, `query_ref` nullable, `operator_refs` Set, `facts_ref` nullable, `claims_ref` nullable, `user_projection_ref` nullable before release, `candidate_status`, `boundary_code` nullable, `query_engine_access_count`, `started_at`, `completed_at`, `replay_level` | raw question, table/column/SQL, release commit ref to avoid cycle |
| `result-release-commit-subject/1` / `result-release-commit` / Channel | `execution_evidence_ref`, `user_projection_ref`, `result_release_eligibility_ref`, `activation_head_ref`, `vrs_ref`, `policy_decision_ref`, `revocation_scope_epoch`, `commit_sequence`, `committed_at` | response delivery acknowledgement |

Stage 1 phases：`ACTIVATE`, `PRE_QUERY`, `RESULT_RELEASE`, `EVIDENCE_READ`. Evidence candidate status：`ANSWER_CANDIDATE`, `CLARIFY`, `REFUSED`, `FAILED_PRECONDITION`, `FAILED_EXECUTION`. `activation_head_ref` may be null only for `ACTIVATE` against a verified empty activation ledger.

For `CLARIFY`/`REFUSED`, `query_engine_access_count=0`, plan/query/facts may be null, claims/projection follow the boundary schema. For `ANSWER_CANDIDATE`, plan/query/facts/claims/user projection are required before release commit. The envelope never contains final `ANSWERED` status：only a valid ResultReleaseCommit that references an `ANSWER_CANDIDATE` evidence subject and its exact projection derives the external Core outcome `ANSWERED`.

### 4.6 SCR

| Schema / object type / scope | Required object-specific fields | Explicitly forbidden/excluded |
|---|---|---|
| `unknown-concept-payload-subject/1` / `proposed-scr-payload` / Governance | `request_type` exactly UNKNOWN_CONCEPT, `safe_term_alias_ref`, `semantic_area_code`, `reason_code`, `safe_context_codes` Set, `safe_detail_artifact_ref`, `interaction_handle_ref`, `observed_gsr_ref`, `observed_vrs_ref`, `boundary_execution_ref`, `requested_action_code` | raw question/hash, value, SQL, physical binding, free text |
| `payload-disclosure-evaluation-subject/1` / `payload-disclosure-evaluation` / Governance | `proposed_payload_ref`, `safe_detail_artifact_ref`, `source_scope`, `destination_scope`, `requester_principal_ref`, `receiving_audience_ref`, `purpose`, `classification`, `allowed_fields` Set, `policy_refs` Set, `obligations` Set, `decision`, `reason_codes` Set, `issued_at`, `expires_at` | disclosure AuthorityDecision and final SCR refs |
| `payload-disclosure-decision-subject/1` / `payload-disclosure-decision` / Governance | `evaluation_ref`, `disclosure_authority_decision_ref` | final SCR ref |
| `scr-enqueue-proposal-subject/1` / `scr-enqueue-proposal` / Governance | `proposed_payload_ref`, `payload_disclosure_decision_ref`, `idempotency_key`, `requested_at`, `limitations` Set | enqueue AuthorityDecision, final SCR ref |
| `semantic-change-request-subject/1` / `semantic-change-request` / Governance | `enqueue_proposal_ref`, `requester_authority_decision_ref` | mutable lifecycle status, Studio truth/candidate ref, own digest |

Safe term/detail values live in separately classified artifacts/refs. Interaction and idempotency handles are random opaque scope-bound tokens, not hashes of human text.

### 4.7 Field-type and enum closure

Unless a row states otherwise：

- singular `*_ref` is `ScopedObjectRefV1`；plural `*_refs` is an array of that type with the declared Set/Ordered semantics；
- `*_digest` follows §2.1 digest grammar；`*_at` follows §2.4 timestamp；
- `*_id` fields are canonical identifiers；code/enum fields use the exact case-sensitive registry values below；epochs、sequence、count、denominator、scale are safe integers；
- fields are non-nullable；only fields explicitly marked nullable may be null；
- map keys are closed by schema, not arbitrary user keys；
- every code/enum must be recognized by the exact Stage Profile/registry tuple；unknown value fails closed。

Primitive closure：`truth_frozen_before_fixture` is boolean and MUST be `true`；`cases` is an Ordered array of `ScopedObjectRefV1`；`locale` is exactly `en-HK` or `zh-HK`；`timezone` is exactly `Asia/Hong_Kong`；`source_scope` and `destination_scope` are exact `GovernanceScopeV1`；`allowed_fields` is a Set drawn only from the four UNKNOWN_CONCEPT fields named below。`idempotency_key` and interaction handles are opaque, scope-bound ASCII tokens of 16–128 characters and MUST NOT be derived from human text。All other unqualified labels are canonical identifiers under §2.1, not free text.

Stage 1 enum closure：

| Field | Accepted values |
|---|---|
| classification | `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`；UNKNOWN is a blocking validation state, not a publishable value |
| ClearedInput origin | `manual_transcription`, `redacted_attachment`, `in_zone_locator`, `synthetic` |
| gate outcome | `PASS`, `FAIL` |
| authority/eligibility/disclosure decision | `ALLOW`, `DENY` |
| activation action | `ACTIVATE` only；Core `DEACTIVATE` requires a later Profile |
| seal status | `SEALED` only |
| oracle class | `CONSTRUCTED_SYNTHETIC`, `INDEPENDENT_DERIVATION`, `EXTERNAL_BUSINESS_REFERENCE` |
| revoke enforcement | `BLOCK_NEW_AND_RESULT_RELEASE` only in Stage 1 |
| eligibility phase | `ACTIVATE`, `PRE_QUERY`, `RESULT_RELEASE`, `EVIDENCE_READ` |
| evidence candidate status | `ANSWER_CANDIDATE`, `CLARIFY`, `REFUSED`, `FAILED_PRECONDITION`, `FAILED_EXECUTION` |
| replay level | `evidence_only` only |
| SCR request type | `UNKNOWN_CONCEPT` only |
| SCR requested action | `REVIEW`, `CLARIFY_DEFINITION`, `ADD_ALIAS` |

`status_counts` is the exact closed map `{ANSWERED, CLARIFY, REFUSED}` and its integer values MUST sum to `denominator`。`verification_attempt_refs_by_gate` is the exact closed five-key map listed in §4.4。Stage 1 command/action registry is exactly the command list in the Synthetic Profile；other actions require a new profile version。

Stage 1 registry closure：

| Field family | Exact accepted values |
|---|---|
| `allowed_uses` | subset of `ontology_build`, `synthetic_demo` |
| `limitations` | subset of `local-authority`, `synthetic-data`, `constructed-target-coupled`, `non-hkex-validation`, `no-raw-question`, `synthetic-scope` |
| `allowed_claims` | `reviewed-constructed-synthetic-conformance` only |
| `purpose` | `ontology-build`, `governed-analysis-demo`, `semantic-change-triage` |
| `obligations` | subset of `ENFORCE_SCOPE`, `WRITE_AUDIT`, `NO_RAW_QUESTION`, `REAUTHORIZE_REFS` |
| Authority action | `APPROVE_CLEARED_INPUT`, `PUBLISH`, `ATTEST`, `SEAL`, `ACTIVATE`, `REVOKE_VRS`, `RESOLVE`, `PRE_QUERY`, `RESULT_RELEASE`, `EVIDENCE_READ`, `SCR_DISCLOSE`, `SCR_ENQUEUE`, `SCR_TRIAGE` |
| Authority reason on ALLOW | `ROLE_AND_SCOPE_MATCH` |
| Policy reason on ALLOW | `POLICY_MATCH` |
| Eligibility reason on ALLOW | subset of `ACTIVE`, `ATTESTATIONS_VALID`, `AUTHORIZED`, `NOT_REVOKED`, `SEALED` |
| Disclosure reason on ALLOW | `MINIMUM_DISCLOSURE_PASS` |
| Activation/revocation intent reason | `INITIAL`, `INTEGRITY` |
| UNKNOWN_CONCEPT reason / semantic area / safe context | `CONCEPT_NOT_BOUND` / `MARKET_METRICS` / `METRIC_TERM` |
| UNKNOWN_CONCEPT `allowed_fields` | subset of `reason_code`, `safe_detail_artifact_ref`, `safe_term_alias_ref`, `semantic_area_code` |
| Suite boundary code | `MISSING_PERIOD`, `UNSUPPORTED_PREDICTION`, `RAW_DETAIL_DENIED`, `ROLE_DENIED`；failed candidates use one stable code from §13 |

No external registry is implicit：the table above plus the Synthetic Profile command list is the unique Stage 1 registry tuple `synthetic-trusted-flow/core@1`。A new value requires a new profile version and vectors.

For a `DENY` Authority、Policy、Eligibility or Disclosure decision，`reason_codes` MUST be one or more applicable stable failure codes from §13；ALLOW codes and DENY codes cannot be mixed。

Candidate/boundary closure：`ANSWER_CANDIDATE` requires `boundary_code=null`；`CLARIFY` or `REFUSED` requires one Suite boundary code；a failed candidate requires one applicable §13 stable failure code。Other combinations fail schema validation.

Scope closure：

| Subject/action family | Exact scope |
|---|---|
| Semantic gate evaluation/attempt；ClearedInput、GSR、SCR decisions/actions | Governance |
| Binding、Disclosure、Runtime、Control gate evaluation/attempt；SEAL | Runtime |
| PolicyDecision；ACTIVATE、REVOKE_VRS、RESOLVE/PRE_QUERY、RESULT_RELEASE、EVIDENCE_READ | Channel |

`AuthorityDecision` uses the protected action's exact scope from this table；`ATTEST` follows its gate subject scope。Every `policy_decision_ref` in §4.5 MUST be a full ref to `policy-decision-subject/1` in the same ChannelScope as the Eligibility/Evidence/ResultRelease subject.

## 5. Canonical JSON v1.0

Canonicalization occurs only after closed-schema validation.

1. Input bytes are UTF-8 without BOM. Invalid UTF-8 is rejected.
2. Duplicate object keys are rejected during parse, including keys that would compare equal after Unicode normalization.
3. Object keys and all string values MUST already be Unicode NFC. Non-NFC and unpaired surrogates are rejected, not silently normalized.
4. Keys are sorted by Unicode code point. Stage 1 schema keys are ASCII snake_case.
5. Serialization uses no insignificant whitespace and no trailing newline.
6. Non-ASCII characters are emitted as UTF-8, not `\u` escapes.
7. Quote and backslash use `\"` and `\\`. U+0008/U+0009/U+000A/U+000C/U+000D use `\b`, `\t`, `\n`, `\f`, `\r`; other U+0000–001F use lowercase `\u00xx`. Slash is not escaped.
8. JSON booleans and null are lowercase.
9. Native JSON numbers are permitted only for integers in `[-9007199254740991, 9007199254740991]`. Binary floats, exponent notation, `-0`, NaN and Infinity are rejected.
10. Business decimal values use `DecimalValueV1`; coefficient/scale are not converted to a native JSON number.
11. Subject timestamps MUST already use exact UTC-millisecond form from §2.4. `+00:00` is rejected at canonicalization boundary.
12. Optional absent and explicit null are distinct. Null is accepted only for fields marked nullable in §4；canonicalizer never applies `exclude_none`.
13. Ordered arrays preserve order. Set arrays MUST arrive unique and sorted by item canonical bytes；otherwise rejected.
14. Unknown fields, unsupported enum, invalid ref, invalid identifier or wrong scope type are rejected before digest.
15. Same scope/type/id/version with another digest is `IDENTITY_CONFLICT`, not a new latest version.

Normative fixture：`fixtures/canonical-json-v1.0-vectors.json`。It contains fixed expected canonical bytes/digests and rejection codes；test implementations MUST NOT regenerate expected values at test time.

The fixture-only `canonical-test-subject/1` is not a product object. It is a closed conformance schema containing the Base DigestSubject plus `chinese_nfc`, `escaped`, `decimal_value`, nullable `nullable`, ordered `ordered_values` and `enabled`; it exists only to isolate byte-level profile behavior.

Each fixed positive vector is intentionally an isolated per-schema canonicalization fixture：its referenced digests may be synthetic and are not proof of a resolvable integrated dependency graph。Even in an isolated vector，every ref's `object_type` / `subject_schema` pair and scope shape MUST match the closed registry。The separate Stage 1 end-to-end fixture/suite MUST build and validate one internally consistent graph whose every full ref resolves to the exact checked subject；isolated vectors cannot satisfy that integration test.

Conformance threshold：

- at least 20 positive vectors and 20 negative vectors；
- every Stage 1 immutable subject schema represented by a schema fixture or field-mutation vector；
- runtime/reference canonicalizer and separately authored verifier agree on 100% positive vectors and reject 100% negative vectors；
- verifier shares neither canonicalization function nor fixture generation path；a second language is preferred, not required；
- every declared subject field mutation changes digest；every envelope-only field mutation leaves subject digest unchanged。

## 6. Five-Gate Dependency and Reuse Matrix

### 6.1 Gate sealing rules

- SemanticApproval PASS is required to form GSR and again referenced by VRS seal set.
- Four environment gates run only against an immutable payload in restricted verification mode.
- Each VerificationAttempt MUST reference an ALLOW AuthorityDecision for its exact GateEvaluation proposed subject.
- Sealer receives exactly one full VerificationAttempt ref per gate；it MUST NOT select latest.
- Attempt must be PASS、scope/profile matching、unexpired、non-revoked、issuer/authority context valid and limitations compatible.
- Control gate has no cross-payload reuse.

### 6.2 Reuse matrix

Reuse means the exact old PASS attempt may be referenced only when its entire subject and validity remain unchanged.

| Changed input | Semantic | Binding | Disclosure | Runtime | Control | Required object action |
|---|---:|---:|---:|---:|---:|---|
| semantic content | rerun | reuse only if its subject unchanged | reuse only if its disclosure subject is unchanged | rerun | rerun | new GSR/payload/VRS |
| lineage/decision only | rerun | reuse | reuse | reuse | rerun because payload/GSR ref changes | new GSR/payload/VRS |
| capability requirements | rerun | reuse | reuse | rerun | rerun | new GSR/payload/VRS |
| binding requirements | rerun | rerun | reuse | rerun only if executable projection/capability subject changes | rerun | new GSR/payload/VRS |
| policy/disclosure requirements | rerun | reuse | rerun | reuse unless obligations change | rerun | new GSR/payload/VRS |
| RuntimeSemanticProjection | reuse semantic | rerun | rerun | rerun | rerun | new payload/VRS |
| BindingBundle | reuse | rerun | reuse | reuse | rerun | new payload/VRS |
| DataIdentity | reuse | rerun | reuse | reuse | rerun | new payload/VRS |
| Projection policy/schema/transformer | reuse | reuse | rerun | rerun if fidelity/runtime subject changes | rerun | new payload/VRS |
| Runtime capability/provider build | reuse | reuse | reuse | rerun | rerun | new payload/VRS |
| Control/Suite/Reference/oracle/runner | reuse | reuse | reuse | reuse unless conformance suite changes | rerun | new payload/VRS |
| environment | semantic reusable in same governance scope | rerun | rerun | rerun | rerun | new payload/VRS |
| channel only | reuse all | reuse | reuse | reuse | reuse | new Activation only |
| attempt expires or issuer authority invalid | payload unchanged | affected gate only | affected gate only | affected gate only | affected gate only | new attempt set and VRS；old VRS stays SEALED but ineligible |
| subject/canonical/profile version | rerun affected gates | affected | affected | affected | rerun | migration + new objects |

Any reuse MUST compare exact canonical subject digest, limitations, validity and trusted authority context. Test evidence reuse is governed separately；an old test blob cannot be silently relabeled as a new authority decision.

Explicit VerificationAttempt-target revocation is not supported by Stage 1。If a future Profile adds it，the affected-gate behavior is the same as expiry/issuer invalidation and requires a new attempt set + VRS；it is not a current Stage 1 test or command.

## 7. AuthorityDecision Check Map

Stage 1 local evaluator inputs come from a read-only principal registry and trusted local session context. Request payload role/scope fields are untrusted.

AuthorityDecision MUST be created and checked at：

| Boundary | Exact protected resource/action |
|---|---|
| ClearedInput approval | proposed ClearedInput subject + allowed use |
| Semantic/Gate approval | exact GateEvaluation proposed subject |
| GSR publish | GSR publish/commit proposed subject |
| VRS seal | VRSSealProposal |
| Activate（Stage 1）；deactivate（Core / future Profile only） | ActivationIntent |
| Revoke | RevocationIntent |
| Resolve/query | request + exact Activation/VRS/purpose |
| Result release | exact execution/projection/final policy context |
| Evidence read/project | exact evidence/projection ref + audience/purpose |
| SCR disclose/enqueue/triage | exact ProposedSCRPayload/final SCR + source/destination audience |

Checks：exact action, scope, purpose, resource digest and policy refs；current trusted session/registry/role/trust epoch；unexpired decision；obligations enforced；cross-scope denial without existence leak。Every privileged committed record references its decision digest.

## 8. Activation Journal and CAS

Stage 1 may use a file-backed single-process journal but MUST implement logical CAS。Activation append、Revocation append and ResultReleaseCommit for one exact ChannelScope share one authority-order lock/domain；separate physical files do not create separate ordering authority：

```text
append_activation(intent, eligibility, authority):
  lock exact ChannelScope
  recover_and_verify_entire_authoritative_tail_or_fail_closed()
  if idempotency key exists:
      same intent digest -> return existing record
      different intent digest -> IDEMPOTENCY_CONFLICT
  require current_head == intent.expected_head
  require current_activation_epoch == intent.expected_activation_epoch
  require eligibility == ALLOW and binds current head/VRS/epoch
  require authority == ALLOW and binds intent
  build record(sequence=head.sequence+1, previous=head, epoch=current_epoch+1)
  append complete framed record + checksum/hash link
  durably synchronize journal
  publish new in-memory/cache head
  return committed record
```

Null expected head is accepted only for verified empty scope. Idempotency lookup occurs under the scope lock after journal recovery but before expected-head comparison, so a retry of an already committed identical command returns its original record even though head has advanced. Two distinct commands with the same expected head MUST yield one commit and one `ACTIVATION_HEAD_CONFLICT`. Gaps、fork、duplicate sequence、hash-link mismatch、partial/corrupt tail cause fail closed until explicit recovery；auto-truncation is forbidden unless recovery produces an auditable repair record outside normal traffic.

The committed ActivationRecord is the lifecycle audit fact. Derived audit/search indexes may lag but cannot be an independent authority whose write failure leaves an activated state unaudited.

## 9. Revocation and Result-Release Linearization

### 9.1 Stage 1 revoke journal

Revocation append uses the same recovery/CAS/idempotency rules and lock ordering as Activation. It atomically appends record and increments `revocation_scope_epoch`. Stage 1 target must be exact VRS ref and enforcement exactly `BLOCK_NEW_AND_RESULT_RELEASE`.

Duplicate same command returns original record because idempotency is resolved before head/epoch comparison under the lock；same key/different intent conflicts。Wrong-scope target, unsupported target/enforcement, UNREVOKE intent, fork or corrupt tail fail closed.

### 9.2 Result release

No streaming. Exact order：

```text
execute and reconcile privately
→ build typed Facts/Claims and allowlisted projection
→ serialize exact candidate response bytes
→ persist immutable evidence/projection artifacts and durably sync
→ acquire shared activation/revocation/release authority-order lock for exact ChannelScope
→ reread current activation head and revocation epoch
→ require current activation head == execution.activation_record_ref == proposed commit.activation_head_ref
→ evaluate final authority/policy/attestation/revocation
→ create RESULT_RELEASE EligibilityDecision
→ append and durably sync ResultReleaseCommit
→ release only the bytes whose digest is in that commit
```

The ResultReleaseCommit append is the linearization point. A revoke ordered first denies commit；a new Activation ordered first changes the head and denies an in-flight execution pinned to the old head；a commit ordered first authorizes that exact persisted projection, while a later Activation affects only work that has not committed。Failure of staging、head reread、policy/eligibility、journal append or durability emits zero answer bytes.

Network delivery acknowledgement is not part of the commit. Retry may only replay exact committed sanitized bytes after an authorized evidence-read check；it may not rerender from mutable state.

## 10. Projection and RuntimePackageView Field Partition

### 10.1 Field classes

| Class | Governance | RuntimePackageView | User Evidence |
|---|---:|---:|---:|
| approved logical IDs/definitions/formula/time/unit | yes | executable subset | disclosed semantic/claim subset |
| lineage/source/decision | authorized full | opaque approved refs only | safe lineage/decision identity |
| draft/gap/conflict/reviewer comment | role-gated | never | never |
| binding handles | authorized | minimum needed by compiler/query boundary | never |
| table/column/join/locator | separately authorized | only inside query boundary, not general runtime DTO | never |
| SQL/params/raw rows | execution review | Query Engine only | never |
| policy rules | authorized | approved inputs/obligations | safe outcome/reason only |
| Fact/Claim | reviewable | typed full | allowlisted principal-specific subset |
| credential/secret | secret system only | handle only | never |

S0 MUST publish a function-by-function field-access matrix for current planner/compiler/calculator/validator/publisher. RuntimePackageView schema is the union of proven executable needs minus governance-only fields；denied fields must be unrepresentable, not merely unused by prompts.

### 10.2 User allowlist and canaries

Ordinary analyze and evidence-read DTOs MUST recursively reject/omit any field or value classified as：table、column、join、SQL、param、raw row、source locator、internal mapping ID、path、stack、prompt、governance comment、credential、secret/canary。

Leak test checks both keys and string values. Acceptance requires forbidden occurrences = 0 and required safe evidence non-empty：claim refs、metric semantic ID、VRS safe identity、DataIdentity safe identity、policy/evidence ref、renderer/projection digest。

Current leak reproduction (`trade_fact`, `executed_value_hkd_mn`, internal mapping IDs) remains a fixed negative regression until closed.

## 11. Data, Render and Replay Identity

DataIdentity MUST resolve exact synthetic data state, not a mutable database name. It binds dataset manifest, schema, partition/row identity, transformation, policy scope, source engine and freeze timestamp；no raw rows or credentials enter contract artifacts.

UserProjection stores or references exact serialized sanitized bytes plus content digest、projection schema/transformer、renderer build、locale、timezone、unit/rounding and classification。ExecutionEvidence binds it along with data/policy/plan/query/operator/Facts/Claims.

Stage 1 replay：

- `evidence_only`：authorized replay of exact committed projection bytes；
- `historical_reexecution`：unsupported；
- `current_data_reexecution`：a new execution, never evidence replay。

## 12. SCR Construction and Triage

```text
boundary ExecutionEnvelope committed
→ in-zone/safe-context projector builds UNKNOWN_CONCEPT ProposedPayload
→ payload digest fixed
→ Disclosure evaluator fixes payload + safe detail + destination audience outcome
→ AuthorityDecision binds that exact proposed evaluation
→ committed PayloadDisclosureDecision binds evaluation + AuthorityDecision
→ build SCREnqueueProposal without authority ref
→ ALLOW AuthorityDecision binds exact EnqueueProposal digest
→ final SCR binds proposal + AuthorityDecision and is committed to idempotent outbox
→ Studio reauthorizes refs and triages only
```

The evaluation directly binds all disclosure inputs；the committed decision binds the exact evaluation plus exact AuthorityDecision and therefore transitively freezes those inputs without duplicating them or creating a digest cycle.

Mutation of payload、safe detail、scope、audience or policy after disclosure invalidates enqueue。Disclosure DENY retains no outbound partial payload。Interaction handle mapping remains in restricted runtime store and needs separate EVIDENCE_READ/CONTEXT_READ authorization.

Five fixtures MUST be rated actionable by a triager without raw question access；owner and disposition correct within two minutes。No safe context produces `DISCLOSURE_BLOCKED`, not an empty SCR.

## 13. Stable Failure Codes

| Code | Boundary | Required result |
|---|---|---|
| `DRAFT_OR_BARE_GSR_NOT_ALLOWED` | resolve | no query |
| `SCOPE_MISMATCH` | any lookup/action | deny without existence leak |
| `UNKNOWN_CONTRACT_PROFILE` | parse/resolve | fail closed |
| `DIGEST_MISMATCH` | any verification | quarantine/fail closed |
| `IDENTITY_CONFLICT` | register/publish | reject same identity/different digest |
| `MISSING_OR_INVALID_ATTESTATION` | seal/eligibility | no seal/execute |
| `ATTESTATION_SUBJECT_MISMATCH` | seal | no seal |
| `AUTHORITY_DENIED_OR_STALE` | privileged boundary | no action |
| `INCOMPATIBLE_CAPABILITY` | seal/eligibility | no seal/execute |
| `SNAPSHOT_NOT_ACTIVE` | resolve | no query |
| `SUBJECT_REVOKED` | pre-query/release | no query or no bytes by ordering |
| `REVOCATION_STATE_INVALID` | recover/check | fail closed |
| `ACTIVATION_HEAD_CONFLICT` | CAS | no append |
| `ACTIVATION_HEAD_CHANGED` | result release final reread | no commit；answer bytes 0 |
| `IDEMPOTENCY_CONFLICT` | command/outbox | no duplicate/overwrite |
| `POLICY_DENIED_OR_UNKNOWN` | query/release/project | safe refusal/no bytes |
| `DATA_IDENTITY_UNAVAILABLE` | execute/evidence | no claims/release |
| `CONTROL_EVALUATION_FAILED` | verification | no seal |
| `EVIDENCE_INCOMPLETE` | release | no answer bytes |
| `PARTIAL_RESULT` | execution/reconcile | discard answer |
| `PROJECTION_LEAKAGE_DETECTED` | project/release | no user projection |
| `SCR_TYPE_UNSUPPORTED` | SCR construct | no enqueue |
| `DISCLOSURE_BLOCKED` | SCR disclosure | no partial outbound payload |
| `JOURNAL_CORRUPT_OR_NOT_DURABLE` | lifecycle/release | no authority success/no bytes |

User messages expose only safe outcome/reason family/correlation ID. Internal details require separate authorization.

## 14. Conformance Matrix

### 14.1 Document/identity freeze tests

- every subject in §4 has one closed field list and no self/cross-cycle；
- fixed vectors satisfy §5 threshold；
- independent verifier agrees 100%；
- every full ref substitution (type/id/version/scope/profile/digest) is detected；
- same identity/different digest conflicts；unknown profile rejects；
- subject-field mutation changes digest；envelope-only mutation does not。

### 14.2 Gate tests

- omit、FAIL、expired、wrong issuer/authority context、wrong subject、wrong scope for each gate；explicit attempt-target revocation is a near-term profile test, not Stage 1；
- owned dependency mutation invalidates correct gate；unrelated mutation reuses only where §6 permits；
- Control never reuses across payload；
- attempt-set ambiguity requires exact caller selection；
- payload excludes attempts；VRS seal includes exact five refs。

### 14.3 Lifecycle/fault tests

- 100 repeated same-head activation races: exactly one successor each；
- idempotent same command returns original；different command conflicts；
- journal partial append/hash-link/fork/gap/durability failure fails closed；
- revoke before query: Query Engine access 0；
- revoke racing release commit: exactly one legal ordered outcome；never post-revoke commit；
- evidence/audit/durability/final-policy fault: answer bytes 0；
- no revoked VRS through latest/pin/cache/rollback/fallback。

### 14.4 Runtime/product tests

- existing 33 automated tests and 33 validation checks remain green；
- one `adt.tracer.v1.suite` passes in pre-seal and active API；
- 4 Answered + 1 Clarify + 3 Refused status/Facts/Claims parity；
- displayed numeric/direction/ranking/limitation direct Claim coverage 100%；
- ordinary API/evidence canary leakage 0 with required safe fields non-empty；
- RuntimePackageView cannot represent governance-only fields；
- exact evidence replay digest equals originally committed projection digest。

### 14.5 SCR/control tests

- five UNKNOWN_CONCEPT fixtures 5/5 actionable and zero forbidden fields；
- raw question/hash and extra variant fields reject；
- disclosure-bound payload mutation rejects；idempotency correct；
- SCR cannot auto-confirm/publish；
- role-combination validator enforces oracle claim ceiling；
- fixture/runtime cannot import expected targets；suite denominator mutation creates new digest；
- all reports visibly state synthetic/simulated/non-HKEX-validation limitation。

## 15. Migration and Recovery Requirements

S0 creates a field-access/change map before implementation. Legacy OntologyPackage and manifest are read-only migration sources；new objects receive new digests and lineage. Dual-publish/shadow compare is allowed；after Activation cutover, legacy latest pointer is non-authoritative.

Local journal recovery must distinguish complete verified tail、partial tail、hash mismatch、fork and gap。Normal traffic never repairs silently。A documented operator recovery may copy the last verified state into a new repair ledger with explicit provenance/Decision；it cannot delete a committed revoke or make a revoked digest eligible。

Implementation can replace files with a transactional database later if it preserves exact CAS、audit-fact、idempotency、ordering and recovery outcomes。

## 16. P1 Ownership after Contract Freeze

| P1 | Owner | Required by | Acceptance |
|---|---|---|---|
| RuntimePackageView exact field-access matrix | Shared Contract / Runtime DRI | before V1 | current call sites mapped；8-case parity；governance fields unrepresentable |
| ordinary API physical-binding leak fix | Agent/API DRI | before external demo | recursive key/value canary 0；safe evidence non-empty |
| local journal physical protocol and crash runbook | Shared Contract Owner | before V2 | CAS/fork/partial-tail/durability tests pass |
| DataIdentity/render DTO implementation | Agent Domain Owner | before V3 | exact projection replay digest and required identities |
| live console API wiring | Agent/Console DRI | before V3 exit | no static alternate fact engine；only allowlisted API |
| component/GSR transitive revoke extension | Shared Contract Owner | near-term target environment | sealed dependency graph + strictness/epoch tests |
| production IAM/policy/audit mapping | Target Platform Owner | Stage 3 | separate target-environment design and evidence |

None of these P1s permit weakening Core. Unsupported behavior fails closed until its profile is approved.
