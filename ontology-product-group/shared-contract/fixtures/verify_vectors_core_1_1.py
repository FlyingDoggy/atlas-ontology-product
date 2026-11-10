#!/usr/bin/env python3
"""Independent verifier for the checked-in core@1.1 conformance fixture.

This module intentionally imports neither fixture generator nor product code. It
independently parses, canonicalizes, hashes, validates closed schemas, resolves
the integrated graph, checks R-01 semantics, and exercises every negative case.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable


CONTRACT = "shared-product-contract/0.1"
STAGE_PROFILE = "synthetic-trusted-flow/core@1.1"
ANNEX_PROFILE = "shared-contract-technical-profile/0.1.1"
CANONICAL_PROFILE = "canonical-json-v1.0"
SAFE_INT = 9_007_199_254_740_991
BASE_FIELDS = {
    "subject_schema",
    "contract_version",
    "canonicalization_profile",
    "object_type",
    "object_id",
    "object_version",
    "scope",
}
FULL_REF_FIELDS = {
    "object_type",
    "object_id",
    "object_version",
    "contract_version",
    "subject_schema",
    "canonicalization_profile",
    "scope",
    "subject_digest",
}
SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
DIGEST_RE = re.compile(r"^sha-256:[0-9a-f]{64}$")
DECIMAL_COEFFICIENT_RE = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")
RESERVED_VERSIONS = {"latest", "current", "*"}
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?$")
OPAQUE_TOKEN_RE = re.compile(r"^opaque-[a-z0-9-]{9,121}$")

BASE_DIR = Path(__file__).resolve().parent
CONFORMANCE_PATH = BASE_DIR / "core-profile-conformance-manifest-1.1.json"
CONFORMANCE = json.loads(CONFORMANCE_PATH.read_text(encoding="utf-8"))
_primitive = CONFORMANCE["primitive_contract"]
if _primitive != {
    "identifier_pattern": SAFE_ID_RE.pattern,
    "version_pattern": VERSION_RE.pattern,
    "reserved_versions": sorted(RESERVED_VERSIONS),
    "digest_pattern": DIGEST_RE.pattern,
    "timestamp_pattern": TIMESTAMP_RE.pattern,
    "opaque_token_pattern": OPAQUE_TOKEN_RE.pattern,
    "decimal_coefficient_pattern": DECIMAL_COEFFICIENT_RE.pattern,
    "safe_integer_min": -SAFE_INT,
    "safe_integer_max": SAFE_INT,
}:
    raise RuntimeError("primitive contract/verifier mismatch")
MACHINE_SCHEMAS: dict[str, dict[str, Any]] = CONFORMANCE["schema_contract"]["schemas"]
PRODUCT_SCHEMAS = {
    schema_id
    for schema_id, definition in MACHINE_SCHEMAS.items()
    if definition.get("acceptance_class") == "product"
}
CONFORMANCE_ONLY_SCHEMAS = set(MACHINE_SCHEMAS) - PRODUCT_SCHEMAS
MACHINE_TYPE_SCHEMA: dict[str, str] = CONFORMANCE["compatibility"][
    "accepted_schema_by_object_type"
]
EXTERNAL_BY_REF: dict[str, dict[str, Any]] = {}
EXTERNAL_MANIFEST: dict[str, Any] = {}
EXTERNAL_CLASS_TYPE_SCHEMA = {
    "BUILD_SCHEMA": ("build-schema-leaf", "build-schema-leaf/1"),
    "EVIDENCE": ("evidence-leaf", "evidence-leaf/1"),
    "INTEGRITY": ("integrity-leaf", "integrity-leaf/1"),
    "PRINCIPAL": ("principal-leaf", "principal-leaf/1"),
    "PRINCIPAL_CONTEXT": ("principal-context-leaf", "principal-context-leaf/1"),
    "PRINCIPAL_REGISTRY": ("principal-registry-leaf", "principal-registry-leaf/1"),
    "REQUEST": ("request-leaf", "request-leaf/1"),
    "SEMANTIC_DECISION": ("semantic-decision-leaf", "semantic-decision-leaf/1"),
    "ROLE_ASSIGNMENT": ("role-assignment-leaf", "role-assignment-leaf/1"),
    "SAFE_HANDLE": ("safe-handle-leaf", "safe-handle-leaf/1"),
    "STATIC_POLICY": ("static-policy-leaf", "static-policy-leaf/1"),
    "SUITE_CASE": ("suite-case-leaf", "suite-case-leaf/1"),
    "TRUSTED_SESSION": ("trusted-session-leaf", "trusted-session-leaf/1"),
}
RULE_LAYER = {
    "cleared-input-authority": "integrated",
    "concept-resolution-evidence": "subject+integrated",
    "control-gate-selected-lineage": "integrated",
    "control-manifest": "subject+integrated",
    "execution-eligibility": "integrated",
    "execution-evidence-boundary": "subject+integrated",
    "execution-evidence-concept": "subject+integrated",
    "gate-evaluation": "subject+integrated",
    "generic-authority-decision": "subject+integrated",
    "gsr-publish-authority": "integrated",
    "gsr-selected-lineage": "integrated",
    "oracle-provenance": "subject+integrated",
    "payload-disclosure-decision": "integrated",
    "payload-disclosure-evaluation": "integrated",
    "policy-decision": "subject+integrated",
    "reference-candidate": "integrated",
    "reference-candidate-set": "subject+integrated",
    "reference-manifest-final": "integrated",
    "reference-reselection-transition": "subject+logical",
    "reference-selection-authority": "subject+integrated",
    "reference-selection-proposal": "integrated",
    "reference-selection-receipt": "subject+integrated+logical",
    "result-release-commit": "integrated",
    "runtime-payload-selected-lineage": "integrated",
    "scr-enqueue-proposal": "integrated",
    "seal-proposal": "integrated",
    "semantic-change-request": "integrated",
    "semantic-content-lineage": "integrated",
    "suite-denominator": "subject+integrated",
    "unknown-concept-payload": "integrated",
    "user-projection": "subject+integrated",
    "verification-attempt": "subject+integrated",
    "verified-runtime-snapshot": "integrated",
}
MANIFEST_RULE_IDS = {
    rule_id
    for definition in MACHINE_SCHEMAS.values()
    for rule_id in definition["rule_ids"]
}
if set(RULE_LAYER) != MANIFEST_RULE_IDS:
    raise RuntimeError(
        "rule implementation registry mismatch: "
        f"missing={sorted(MANIFEST_RULE_IDS - set(RULE_LAYER))} "
        f"extra={sorted(set(RULE_LAYER) - MANIFEST_RULE_IDS)}"
    )

RULE_EVIDENCE = {
    "cleared-input-authority": ("I03-truth-selection-chain", "G100-cleared-input-authority-deny"),
    "concept-resolution-evidence": ("I10-concept-not-bound-immutable-evidence", "G50-concept-not-well-formed"),
    "control-gate-selected-lineage": ("I06-selected-identity-downstream", "G112-control-gate-aux-oracle"),
    "control-manifest": ("I03-truth-selection-chain", "G116-control-author-reviewer-collapse"),
    "execution-eligibility": ("I07-gsr-vrs-activation-chain", "G105-activation-wrong-attempt"),
    "execution-evidence-boundary": ("I08-five-outcomes-release", "G135-concept-evidence-status-mismatch"),
    "execution-evidence-concept": ("I10-concept-not-bound-immutable-evidence", "G55-concept-evidence-ref-omitted"),
    "gate-evaluation": ("I07-gsr-vrs-activation-chain", "G36-gate-semantic-future-issued"),
    "generic-authority-decision": ("I04-authority-trust-roots", "G129-publish-wrong-purpose"),
    "gsr-publish-authority": ("I06-selected-identity-downstream", "G101-publish-authority-deny"),
    "gsr-selected-lineage": ("I06-selected-identity-downstream", "G70-gsr-unselected-manifest"),
    "oracle-provenance": ("I03-truth-selection-chain", "G117-oracle-author-reviewer-collapse"),
    "payload-disclosure-decision": ("I12-scr-chain-requires-release", "G134-disclosure-decision-wrong-authority"),
    "payload-disclosure-evaluation": ("I12-scr-chain-requires-release", "G59-disclosure-evaluation-deny"),
    "policy-decision": ("I08-five-outcomes-release", "G122-activation-policy-deny"),
    "reference-candidate": ("I03-truth-selection-chain", "G118-selected-candidate-wrong-control"),
    "reference-candidate-set": ("I03-truth-selection-chain", "G133-candidate-set-denominator-drift"),
    "reference-manifest-final": ("I03-truth-selection-chain", "G120-final-manifest-wrong-control"),
    "reference-reselection-transition": ("I03-truth-selection-chain", "G113-successor-false-changed-ref"),
    "reference-selection-authority": ("I03-truth-selection-chain", "G05-selection-trust-epoch"),
    "reference-selection-proposal": ("I03-truth-selection-chain", "G119-selected-proposal-nonmember"),
    "reference-selection-receipt": ("I05-committed-selection-receipt", "G102-selection-key-digest-forged"),
    "result-release-commit": ("I08-five-outcomes-release", "G126-release-wrong-projection"),
    "runtime-payload-selected-lineage": ("I06-selected-identity-downstream", "G111-payload-aux-oracle"),
    "scr-enqueue-proposal": ("I12-scr-chain-requires-release", "G110-scr-enqueue-wrong-resource"),
    "seal-proposal": ("I07-gsr-vrs-activation-chain", "G131-seal-attempt-alias"),
    "semantic-change-request": ("I12-scr-chain-requires-release", "G61-enqueue-authority-deny"),
    "semantic-content-lineage": ("I06-selected-identity-downstream", "G72-gsr-unselected-semantic-content"),
    "suite-denominator": ("I13-adt-suite-denominator-unchanged", "G121-suite-denominator-drift"),
    "unknown-concept-payload": ("I12-scr-chain-requires-release", "G56-unreleased-boundary-substitution"),
    "user-projection": ("I08-five-outcomes-release", "G127-projection-execution-mismatch"),
    "verification-attempt": ("I07-gsr-vrs-activation-chain", "G124-verification-attempt-wrong-authority"),
    "verified-runtime-snapshot": ("I07-gsr-vrs-activation-chain", "G125-vrs-wrong-seal-authority"),
}
if set(RULE_EVIDENCE) != MANIFEST_RULE_IDS:
    raise RuntimeError(
        "rule evidence registry mismatch: "
        f"missing={sorted(MANIFEST_RULE_IDS - set(RULE_EVIDENCE))} "
        f"extra={sorted(set(RULE_EVIDENCE) - MANIFEST_RULE_IDS)}"
    )


# Predecessor raw/canonical negative-vector vocabulary only.  None of these
# maps participates in core@1.1 subject or graph acceptance; MACHINE_SCHEMAS is
# the sole core@1.1 contract authority.  They remain only so the frozen core@1
# parser-edge vectors can be replayed unchanged in this independent process.
def fields(*names: str) -> set[str]:
    return BASE_FIELDS | set(names)


LEGACY_SCHEMA_FIELDS: dict[str, set[str]] = {
    "cleared-input-proposal-subject/1": fields("classification", "origin", "allowed_uses", "safe_content_ref", "opaque_source_locator_ref", "limitations"),
    "cleared-input-subject/1": fields("proposal_ref", "input_disclosure_authority_decision_ref"),
    "gsr-publish-subject/1": fields("semantic_version", "semantic_schema_ref", "semantic_content_ref", "cleared_input_refs", "decision_refs", "required_capability_refs", "binding_requirements_ref", "policy_requirements_ref", "disclosure_labels_ref", "supersedes_ref"),
    "governed-semantic-release-subject/1": fields("publish_subject_ref", "semantic_approval_attempt_ref", "publish_authority_decision_ref"),
    "runtime-snapshot-payload-subject/1": fields("gsr_ref", "runtime_semantic_projection_ref", "binding_bundle_ref", "projection_policy_bundle_ref", "runtime_capability_manifest_ref", "data_identity_ref", "control_manifest_ref", "suite_manifest_ref", "reference_manifest_ref", "oracle_provenance_ref", "evaluation_runner_manifest_ref", "compatibility_profile_ref", "projection_profile_ref"),
    "data-identity-subject/1": fields("dataset_manifest_ref", "schema_digest", "partition_identity_refs", "row_count", "source_engine_ref", "transformation_ref", "policy_scope_ref", "frozen_at", "replay_level"),
    "reference-candidate-subject/1": fields("reference_case_id", "cleared_input_ref", "control_manifest_ref", "suite_manifest_ref", "oracle_provenance_ref", "verification_criteria_ref", "limitations", "frozen_at"),
    "reference-candidate-set-subject/1": fields("candidate_refs", "shared_suite_manifest_ref", "selection_policy_ref", "denominator", "frozen_at"),
    "reference-selection-proposal-subject/1": fields("candidate_set_ref", "selected_candidate_ref", "selected_reference_case_id", "limitations"),
    "reference-manifest-subject/1": fields("reference_case_id", "cleared_input_ref", "control_manifest_ref", "suite_manifest_ref", "oracle_provenance_ref", "frozen_at", "selection_proposal_ref", "selection_authority_decision_ref"),
    "control-manifest-subject/1": fields("reference_case_id", "oracle_class", "oracle_provenance_refs", "formula_ref", "period_profile_ref", "population_profile_ref", "unit_ref", "rounding_profile_ref", "expected_result_refs", "tolerance_profile_ref", "expected_value_author_ref", "fixture_author_ref", "reviewer_ref", "truth_frozen_before_fixture", "allowed_claims", "limitations", "frozen_at"),
    "suite-manifest-subject/1": fields("suite_id", "cases", "denominator", "status_counts", "mutation_profile_ref", "frozen_at"),
    "semantic-approval-subject/1": fields("gsr_publish_subject_ref", "semantic_validation_profile_ref"),
    "binding-data-validation-subject/1": fields("gsr_binding_requirements_ref", "runtime_semantic_projection_ref", "binding_bundle_ref", "data_identity_ref", "binding_validation_profile_ref"),
    "disclosure-policy-subject/1": fields("gsr_disclosure_labels_ref", "gsr_policy_requirements_ref", "runtime_semantic_projection_ref", "runtime_projection_schema_ref", "user_projection_schema_ref", "projection_transformer_ref", "projection_policy_bundle_ref", "audience_purpose_profile_ref", "projection_fidelity_report_ref", "disclosure_validation_profile_ref"),
    "runtime-capability-subject/1": fields("gsr_semantic_content_ref", "gsr_capability_requirements_ref", "runtime_semantic_projection_ref", "runtime_capability_manifest_ref", "provider_build_ref", "input_schema_ref", "output_schema_ref", "failure_contract_ref", "options_profile_ref", "policy_obligations_ref", "compatibility_profile_ref", "projection_fidelity_report_ref", "conformance_suite_ref"),
    "control-golden-subject/1": fields("runtime_snapshot_payload_ref", "control_manifest_ref", "suite_manifest_ref", "reference_manifest_ref", "oracle_provenance_ref", "evaluation_runner_manifest_ref", "evaluation_profile_ref"),
    "gate-evaluation-subject/1": fields("gate_type", "gate_subject_ref", "outcome", "evidence_refs", "limitations", "validity_mode", "issued_at", "expires_at"),
    "authority-decision-subject/1": fields("action", "trusted_session_ref", "principal_ref", "principal_registry_ref", "role_assignment_ref", "trust_epoch", "purpose", "proposed_action_subject_ref", "policy_refs", "obligations", "decision", "reason_codes", "issued_at", "expires_at"),
    "policy-decision-subject/1": fields("principal_context_ref", "purpose", "resource_refs", "policy_refs", "input_context_digest", "decision", "reason_codes", "obligations", "evaluated_at", "valid_until"),
    "verification-attempt-subject/1": fields("gate_evaluation_ref", "authority_decision_ref"),
    "vrs-seal-proposal-subject/1": fields("runtime_snapshot_payload_ref", "verification_attempt_refs_by_gate"),
    "verified-runtime-snapshot-subject/1": fields("seal_proposal_ref", "seal_authority_decision_ref", "seal_status", "limitations"),
    "activation-intent-subject/1": fields("action", "vrs_ref", "expected_head_ref", "expected_activation_epoch", "idempotency_key", "reason_code", "requested_at"),
    "activation-record-subject/1": fields("intent_ref", "eligibility_decision_ref", "authority_decision_ref", "sequence", "previous_record_ref", "activation_epoch", "committed_at"),
    "revocation-intent-subject/1": fields("target_ref", "enforcement", "expected_head_ref", "expected_revocation_epoch", "idempotency_key", "reason_code", "requested_at"),
    "revocation-record-subject/1": fields("intent_ref", "authority_decision_ref", "sequence", "previous_record_ref", "new_revocation_epoch", "committed_at"),
    "execution-eligibility-subject/1": fields("phase", "purpose", "vrs_ref", "runtime_snapshot_payload_ref", "verification_attempt_refs_by_gate", "activation_head_ref", "request_authority_decision_ref", "policy_decision_ref", "revocation_scope_epoch", "observed_revocation_set_digest", "evaluated_at", "valid_until", "decision", "reason_codes"),
    "user-projection-subject/1": fields("execution_id", "projection_schema_ref", "content_bytes_digest", "renderer_ref", "locale", "timezone", "unit_profile_ref", "rounding_profile_ref", "classification_ref"),
    "execution-evidence-subject/1": fields("execution_id", "principal_context_ref", "purpose", "gsr_ref", "vrs_ref", "activation_record_ref", "pre_query_eligibility_ref", "policy_decision_ref", "data_identity_ref", "plan_ref", "query_ref", "operator_refs", "facts_ref", "claims_ref", "user_projection_ref", "candidate_status", "boundary_code", "query_engine_access_count", "started_at", "completed_at", "replay_level"),
    "result-release-commit-subject/1": fields("execution_evidence_ref", "user_projection_ref", "result_release_eligibility_ref", "activation_head_ref", "vrs_ref", "policy_decision_ref", "revocation_scope_epoch", "commit_sequence", "committed_at"),
    "unknown-concept-payload-subject/1": fields("request_type", "safe_term_alias_ref", "semantic_area_code", "reason_code", "safe_context_codes", "safe_detail_artifact_ref", "interaction_handle_ref", "observed_gsr_ref", "observed_vrs_ref", "boundary_execution_ref", "requested_action_code"),
    "payload-disclosure-evaluation-subject/1": fields("proposed_payload_ref", "safe_detail_artifact_ref", "source_scope", "destination_scope", "requester_principal_ref", "receiving_audience_ref", "purpose", "classification", "allowed_fields", "policy_refs", "obligations", "decision", "reason_codes", "issued_at", "expires_at"),
    "payload-disclosure-decision-subject/1": fields("evaluation_ref", "disclosure_authority_decision_ref"),
    "scr-enqueue-proposal-subject/1": fields("proposed_payload_ref", "payload_disclosure_decision_ref", "idempotency_key", "requested_at", "limitations"),
    "semantic-change-request-subject/1": fields("enqueue_proposal_ref", "requester_authority_decision_ref"),
    "canonical-test-subject/1": fields("chinese_nfc", "escaped", "decimal_value", "nullable", "ordered_values", "enabled"),
}

SCHEMA_OBJECT_TYPE = {
    "cleared-input-proposal-subject/1": "cleared-input-proposal",
    "cleared-input-subject/1": "cleared-input",
    "gsr-publish-subject/1": "gsr-publish-subject",
    "governed-semantic-release-subject/1": "governed-semantic-release",
    "runtime-snapshot-payload-subject/1": "runtime-snapshot-payload",
    "data-identity-subject/1": "data-identity",
    "reference-candidate-subject/1": "reference-candidate",
    "reference-candidate-set-subject/1": "reference-candidate-set",
    "reference-selection-proposal-subject/1": "reference-selection-proposal",
    "reference-manifest-subject/1": "reference-manifest",
    "control-manifest-subject/1": "control-manifest",
    "suite-manifest-subject/1": "suite-manifest",
    "semantic-approval-subject/1": "semantic-approval-subject",
    "binding-data-validation-subject/1": "binding-data-validation-subject",
    "disclosure-policy-subject/1": "disclosure-policy-subject",
    "runtime-capability-subject/1": "runtime-capability-subject",
    "control-golden-subject/1": "control-golden-subject",
    "gate-evaluation-subject/1": "gate-evaluation",
    "authority-decision-subject/1": "authority-decision",
    "policy-decision-subject/1": "policy-decision",
    "verification-attempt-subject/1": "verification-attempt",
    "vrs-seal-proposal-subject/1": "vrs-seal-proposal",
    "verified-runtime-snapshot-subject/1": "verified-runtime-snapshot",
    "activation-intent-subject/1": "activation-intent",
    "activation-record-subject/1": "activation-record",
    "revocation-intent-subject/1": "revocation-intent",
    "revocation-record-subject/1": "revocation-record",
    "execution-eligibility-subject/1": "execution-eligibility-decision",
    "user-projection-subject/1": "user-evidence-projection",
    "execution-evidence-subject/1": "execution-evidence-envelope",
    "result-release-commit-subject/1": "result-release-commit",
    "unknown-concept-payload-subject/1": "proposed-scr-payload",
    "payload-disclosure-evaluation-subject/1": "payload-disclosure-evaluation",
    "payload-disclosure-decision-subject/1": "payload-disclosure-decision",
    "scr-enqueue-proposal-subject/1": "scr-enqueue-proposal",
    "semantic-change-request-subject/1": "semantic-change-request",
    "canonical-test-subject/1": "canonical-test",
}
TYPE_SCHEMA = {value: key for key, value in SCHEMA_OBJECT_TYPE.items()}

SET_FIELDS: dict[str, set[str]] = {
    "cleared-input-proposal-subject/1": {"allowed_uses", "limitations"},
    "gsr-publish-subject/1": {"cleared_input_refs", "decision_refs", "required_capability_refs"},
    "data-identity-subject/1": {"partition_identity_refs"},
    "reference-candidate-subject/1": {"limitations"},
    "reference-candidate-set-subject/1": {"candidate_refs"},
    "reference-selection-proposal-subject/1": {"limitations"},
    "control-manifest-subject/1": {"oracle_provenance_refs", "allowed_claims", "limitations"},
    "gate-evaluation-subject/1": {"evidence_refs", "limitations"},
    "authority-decision-subject/1": {"policy_refs", "obligations", "reason_codes"},
    "policy-decision-subject/1": {"resource_refs", "policy_refs", "reason_codes", "obligations"},
    "verified-runtime-snapshot-subject/1": {"limitations"},
    "execution-eligibility-subject/1": {"reason_codes"},
    "execution-evidence-subject/1": {"operator_refs"},
    "unknown-concept-payload-subject/1": {"safe_context_codes"},
    "payload-disclosure-evaluation-subject/1": {"allowed_fields", "policy_refs", "obligations", "reason_codes"},
    "scr-enqueue-proposal-subject/1": {"limitations"},
}

NULLABLE_FIELDS: dict[str, set[str]] = {
    "gsr-publish-subject/1": {"supersedes_ref"},
    "gate-evaluation-subject/1": {"expires_at"},
    "activation-intent-subject/1": {"expected_head_ref"},
    "activation-record-subject/1": {"previous_record_ref"},
    "revocation-intent-subject/1": {"expected_head_ref"},
    "revocation-record-subject/1": {"previous_record_ref"},
    "execution-eligibility-subject/1": {"activation_head_ref"},
    "execution-evidence-subject/1": {"plan_ref", "query_ref", "facts_ref", "claims_ref", "user_projection_ref", "boundary_code"},
    "canonical-test-subject/1": {"nullable"},
}

GOVERNANCE_SCHEMAS = {
    "cleared-input-proposal-subject/1", "cleared-input-subject/1", "gsr-publish-subject/1",
    "governed-semantic-release-subject/1", "reference-candidate-subject/1",
    "reference-candidate-set-subject/1", "reference-selection-proposal-subject/1",
    "reference-manifest-subject/1", "control-manifest-subject/1", "suite-manifest-subject/1",
    "semantic-approval-subject/1", "unknown-concept-payload-subject/1",
    "payload-disclosure-evaluation-subject/1", "payload-disclosure-decision-subject/1",
    "scr-enqueue-proposal-subject/1", "semantic-change-request-subject/1", "canonical-test-subject/1",
}
RUNTIME_SCHEMAS = {
    "runtime-snapshot-payload-subject/1", "data-identity-subject/1",
    "binding-data-validation-subject/1", "disclosure-policy-subject/1",
    "runtime-capability-subject/1", "control-golden-subject/1",
    "vrs-seal-proposal-subject/1", "verified-runtime-snapshot-subject/1",
}
CHANNEL_SCHEMAS = {
    "policy-decision-subject/1", "activation-intent-subject/1", "activation-record-subject/1",
    "revocation-intent-subject/1", "revocation-record-subject/1",
    "execution-eligibility-subject/1", "user-projection-subject/1",
    "execution-evidence-subject/1", "result-release-commit-subject/1",
}

ACTIONS = {
    "APPROVE_CLEARED_INPUT", "SELECT_REFERENCE", "PUBLISH", "ATTEST", "SEAL", "ACTIVATE",
    "REVOKE_VRS", "RESOLVE", "PRE_QUERY", "RESULT_RELEASE", "EVIDENCE_READ", "SCR_DISCLOSE",
    "SCR_ENQUEUE", "SCR_TRIAGE",
}
FIVE_GATES = {
    "SEMANTIC_APPROVAL", "BINDING_DATA_VALIDATION", "DISCLOSURE_POLICY_CLEARANCE",
    "RUNTIME_CAPABILITY_COMPATIBILITY", "CONTROL_GOLDEN_EVALUATION",
}


class VectorError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def pairs_to_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        normalized_key = unicodedata.normalize("NFC", key)
        if key in output or normalized_key in normalized:
            raise VectorError("DUPLICATE_KEY")
        output[key] = value
        normalized.add(normalized_key)
    return output


def reject_constant(_: str) -> Any:
    raise VectorError("NON_FINITE_FORBIDDEN")


def parse(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=pairs_to_object, parse_constant=reject_constant)
    except VectorError:
        raise
    except UnicodeDecodeError as exc:
        raise VectorError("INVALID_UTF8") from exc
    except json.JSONDecodeError as exc:
        raise VectorError("INVALID_JSON") from exc


def quote(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise VectorError("NON_NFC")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise VectorError("UNPAIRED_SURROGATE")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        if not -SAFE_INT <= value <= SAFE_INT:
            raise VectorError("INTEGER_OUT_OF_RANGE")
        return str(value)
    if isinstance(value, float):
        raise VectorError("FLOAT_FORBIDDEN")
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, list):
        return "[" + ",".join(render(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if unicodedata.normalize("NFC", key) != key:
                raise VectorError("NON_NFC_KEY")
        return "{" + ",".join(quote(key) + ":" + render(value[key]) for key in sorted(value)) + "}"
    raise VectorError("UNSUPPORTED_TYPE")


def subject_digest(schema: str, canonical_json: str) -> str:
    preimage = b"\x00".join(
        [b"spc-v0.1", CANONICAL_PROFILE.encode(), schema.encode(), canonical_json.encode("utf-8")]
    )
    return "sha-256:" + hashlib.sha256(preimage).hexdigest()


def validate_timestamp(value: str) -> None:
    if not TIMESTAMP_RE.fullmatch(value):
        raise VectorError("TIMESTAMP_NOT_UTC_MILLISECOND_Z")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise VectorError("INVALID_TIMESTAMP") from exc


def expected_scope_keys(kind: str) -> set[str]:
    keys = {"tenant_id", "workspace_id"}
    if kind in {"runtime", "channel"}:
        keys.add("environment_id")
    if kind == "channel":
        keys.add("channel")
    return keys


def scope_kind(scope: dict[str, Any]) -> str:
    keys = set(scope)
    if keys == expected_scope_keys("governance"):
        return "governance"
    if keys == expected_scope_keys("runtime"):
        return "runtime"
    if keys == expected_scope_keys("channel"):
        return "channel"
    raise VectorError("INVALID_SCOPE_SHAPE")


def scope_coordinates_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Require every coordinate represented on both sides to agree."""
    return all(
        left[key] == right[key]
        for key in ("tenant_id", "workspace_id", "environment_id", "channel")
        if key in left and key in right
    )


def validate_sorted_set(values: list[Any]) -> None:
    rendered = [render(item) for item in values]
    if len(set(rendered)) != len(rendered):
        raise VectorError("SET_DUPLICATE")
    if rendered != sorted(rendered):
        raise VectorError("SET_NOT_CANONICALLY_SORTED")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure_external_manifest(document: dict[str, Any]) -> None:
    global EXTERNAL_BY_REF, EXTERNAL_MANIFEST
    metadata = document.get("external_leaf_manifest", {})
    path = BASE_DIR / metadata.get("filename", "")
    if not path.is_file() or sha256_file(path) != metadata.get("sha256"):
        raise VectorError("PINNED_MANIFEST_MISMATCH")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_schema") != "external-leaf-manifest/1"
        or manifest.get("stage_profile_id") != STAGE_PROFILE
        or manifest.get("caller_supplied") is not False
        or manifest.get("entry_count") != len(manifest.get("entries", []))
        or manifest.get("entry_count") != metadata.get("entry_count")
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    by_ref: dict[str, dict[str, Any]] = {}
    for entry in manifest["entries"]:
        if set(entry) != {"leaf_class", "object_id", "object_version", "scope", "facts", "ref"}:
            raise VectorError("EXTERNAL_MANIFEST_INVALID")
        ref_value = entry["ref"]
        validate_full_ref_syntax(ref_value)
        if (
            entry["object_id"] != ref_value["object_id"]
            or entry["object_version"] != ref_value["object_version"]
            or not same(entry["scope"], ref_value["scope"])
        ):
            raise VectorError("EXTERNAL_MANIFEST_INVALID")
        body = {key: entry[key] for key in ("leaf_class", "object_id", "object_version", "scope", "facts")}
        expected_digest = "sha-256:" + hashlib.sha256(
            b"spc-external-leaf-v1\x00" + render(body).encode("utf-8")
        ).hexdigest()
        if ref_value["subject_digest"] != expected_digest:
            raise VectorError("EXTERNAL_LEAF_DIGEST_MISMATCH")
        validate_external_entry(entry)
        key = render(ref_value)
        if key in by_ref:
            raise VectorError("IDENTITY_CONFLICT")
        by_ref[key] = entry
    EXTERNAL_MANIFEST = manifest
    EXTERNAL_BY_REF = by_ref


def validate_external_entry(entry: dict[str, Any]) -> None:
    facts = entry["facts"]
    class_code = entry["leaf_class"]
    required_common = {"classification", "dependency_free", "scope_kind", "status"}
    if not required_common.issubset(facts) or facts["dependency_free"] is not True or facts["status"] != "ACTIVE":
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if facts["scope_kind"] != scope_kind(entry["scope"]):
        raise VectorError("SCOPE_MISMATCH")
    required_by_class = {
        "TRUSTED_SESSION": {"principal_object_id", "trust_epoch", "issued_at", "expires_at"},
        "PRINCIPAL_REGISTRY": {"snapshot_digest", "trust_epoch"},
        "PRINCIPAL": {"registry_object_id"},
        "PRINCIPAL_CONTEXT": {"principal_object_id", "purpose"},
        "ROLE_ASSIGNMENT": {
            "principal_object_id",
            "role_code",
            "allowed_actions",
            "trust_epoch",
            "issued_at",
            "expires_at",
        },
        "STATIC_POLICY": {
            "allowed_actions",
            "allowed_purposes",
            "effective_at",
            "expires_at",
            "policy_version",
        },
        "REQUEST": {"request_family", "allowed_purpose"},
        "SEMANTIC_DECISION": {
            "decision_profile",
            "decision_kind",
            "source_cleared_input_subject_digest",
            "candidate_subject_digest",
            "trace_subject_digest",
            "decision_outcome",
        },
        "SAFE_HANDLE": {"raw_value_present", "handle_kind"},
        "SUITE_CASE": {"suite_id"},
        "EVIDENCE": {"evidence_profile"},
        "BUILD_SCHEMA": {"build_or_schema_identity"},
        "INTEGRITY": {"allowed_slot_family"},
    }
    required = required_by_class.get(class_code)
    if required is None or set(facts) != required_common | required:
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    expected_type_schema = EXTERNAL_CLASS_TYPE_SCHEMA.get(class_code)
    if expected_type_schema is None or (
        entry["ref"]["object_type"], entry["ref"]["subject_schema"]
    ) != expected_type_schema:
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if facts["classification"] not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    for timestamp_field in ("issued_at", "effective_at", "expires_at"):
        if timestamp_field in facts:
            validate_timestamp(facts[timestamp_field])
    if "snapshot_digest" in facts and not DIGEST_RE.fullmatch(facts["snapshot_digest"]):
        raise VectorError("INVALID_DIGEST")
    identifier_fields = {
        "principal_object_id",
        "registry_object_id",
        "role_code",
        "request_family",
        "build_or_schema_identity",
        "evidence_profile",
    }
    if any(
        field in facts
        and (
            not isinstance(facts[field], str)
            or not SAFE_ID_RE.fullmatch(facts[field])
        )
        for field in identifier_fields
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "trust_epoch" in facts and (
        type(facts["trust_epoch"]) is not int
        or not 0 <= facts["trust_epoch"] <= SAFE_INT
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "policy_version" in facts and (
        not isinstance(facts["policy_version"], str)
        or facts["policy_version"] in RESERVED_VERSIONS
        or not VERSION_RE.fullmatch(facts["policy_version"])
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "issued_at" in facts and not (
        parse_time(facts["issued_at"]) < parse_time(facts["expires_at"])
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "effective_at" in facts and not (
        parse_time(facts["effective_at"]) < parse_time(facts["expires_at"])
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "SAFE_HANDLE" and facts["raw_value_present"] is not False:
        raise VectorError("RAW_INPUT_LEAK")
    if class_code == "SAFE_HANDLE" and facts["handle_kind"] != "opaque-safe-handle":
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "SUITE_CASE" and facts["suite_id"] != "adt.tracer.v1.suite":
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "INTEGRITY" and facts["allowed_slot_family"] != "integrity":
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "EVIDENCE" and facts["evidence_profile"] != "deterministic-synthetic":
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "SEMANTIC_DECISION" and (
        facts["decision_profile"] != CONFORMANCE["profile_contract"]["semantic_decision_profile"]
        or facts["decision_kind"] != "scope-period-rounding"
        or facts["decision_outcome"] != "ACCEPTED"
        or any(
            not DIGEST_RE.fullmatch(facts[field])
            for field in (
                "source_cleared_input_subject_digest",
                "candidate_subject_digest",
                "trace_subject_digest",
            )
        )
    ):
        raise VectorError("SEMANTIC_DECISION_INVALID")
    for set_field in ("allowed_actions", "allowed_purposes"):
        if set_field in facts:
            if not isinstance(facts[set_field], list):
                raise VectorError("EXTERNAL_MANIFEST_INVALID")
            validate_sorted_set(facts[set_field])
    allowed_actions = set(CONFORMANCE["profile_contract"]["generic_authority_actions"]) | {
        CONFORMANCE["profile_contract"]["selection_authority_action"]
    }
    allowed_purposes = {
        purpose
        for contract in CONFORMANCE["profile_contract"]["authority_action_contract"].values()
        for purpose in contract["purposes"]
    } | {"ontology-build"}
    if "allowed_actions" in facts and not set(facts["allowed_actions"]).issubset(
        allowed_actions
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "allowed_purposes" in facts and not set(facts["allowed_purposes"]).issubset(
        allowed_purposes
    ):
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if "allowed_purpose" in facts and facts["allowed_purpose"] not in allowed_purposes:
        raise VectorError("EXTERNAL_MANIFEST_INVALID")
    if class_code == "PRINCIPAL_CONTEXT" and facts["purpose"] not in allowed_purposes:
        raise VectorError("EXTERNAL_MANIFEST_INVALID")


def validate_scope_value(value: Any, allowed_kinds: list[str]) -> None:
    if not isinstance(value, dict):
        raise VectorError("TYPE_MISMATCH")
    kind = scope_kind(value)
    if kind not in allowed_kinds:
        raise VectorError("SCOPE_MISMATCH")
    fixed = CONFORMANCE["profile_contract"]["fixed_scope"]
    for key in expected_scope_keys(kind):
        if value.get(key) != fixed[key]:
            raise VectorError("SCOPE_MISMATCH")


def validate_full_ref_syntax(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != FULL_REF_FIELDS:
        raise VectorError("INVALID_FULL_REF")
    if value["contract_version"] != CONTRACT or value["canonicalization_profile"] != CANONICAL_PROFILE:
        raise VectorError("UNKNOWN_CONTRACT_PROFILE")
    if not isinstance(value["object_type"], str) or not isinstance(value["subject_schema"], str):
        raise VectorError("TYPE_MISMATCH")
    if not isinstance(value["object_id"], str) or not SAFE_ID_RE.fullmatch(value["object_id"]):
        raise VectorError("INVALID_IDENTIFIER")
    if not isinstance(value["object_version"], str) or not VERSION_RE.fullmatch(value["object_version"]):
        raise VectorError("RESERVED_VERSION")
    validate_scope_value(value["scope"], ["governance", "runtime", "channel"])
    if not isinstance(value["subject_digest"], str) or not DIGEST_RE.fullmatch(value["subject_digest"]):
        raise VectorError("INVALID_DIGEST")


def resolve_external(value: dict[str, Any], classes: list[str]) -> dict[str, Any]:
    entry = EXTERNAL_BY_REF.get(render(value))
    if entry is None:
        raise VectorError("UNRESOLVED_FULL_REF")
    if entry["leaf_class"] not in classes:
        raise VectorError("REF_TARGET_MISMATCH")
    return entry


def validate_value(value: Any, spec: dict[str, Any]) -> None:
    kind = spec["kind"]
    if kind == "nullable":
        if value is None:
            return
        validate_value(value, spec["item"])
        return
    if value is None:
        raise VectorError("NULL_NOT_ALLOWED")
    if kind == "fixed":
        if value != spec["value"]:
            raise VectorError("UNKNOWN_CONTRACT_PROFILE")
        return
    if kind in {"identifier", "version", "nonempty_string", "timestamp", "digest", "opaque_token", "string"}:
        if not isinstance(value, str):
            raise VectorError("TYPE_MISMATCH")
        if unicodedata.normalize("NFC", value) != value:
            raise VectorError("NON_NFC")
        if kind == "identifier" and not SAFE_ID_RE.fullmatch(value):
            raise VectorError("INVALID_IDENTIFIER")
        if kind == "version" and (value in RESERVED_VERSIONS or not VERSION_RE.fullmatch(value)):
            raise VectorError("RESERVED_VERSION")
        if kind == "nonempty_string" and not value:
            raise VectorError("EMPTY_STRING")
        if kind == "timestamp":
            validate_timestamp(value)
        if kind == "digest" and not DIGEST_RE.fullmatch(value):
            raise VectorError("INVALID_DIGEST")
        if kind == "opaque_token" and not OPAQUE_TOKEN_RE.fullmatch(value):
            raise VectorError("INVALID_OPAQUE_TOKEN")
        if "enum" in spec and value not in spec["enum"]:
            raise VectorError("UNKNOWN_CONTRACT_PROFILE")
        return
    if kind == "integer":
        if type(value) is not int:
            raise VectorError("TYPE_MISMATCH")
        if not -SAFE_INT <= value <= SAFE_INT or value < spec.get("minimum", -SAFE_INT):
            raise VectorError("INTEGER_OUT_OF_RANGE")
        return
    if kind == "boolean":
        if type(value) is not bool:
            raise VectorError("TYPE_MISMATCH")
        return
    if kind == "scope":
        validate_scope_value(value, spec["allowed_kinds"])
        return
    if kind == "opaque_locator":
        if not isinstance(value, dict) or set(value) != {"locator_handle", "scope", "classification"}:
            raise VectorError("INVALID_OPAQUE_LOCATOR")
        if not isinstance(value["locator_handle"], str) or not OPAQUE_TOKEN_RE.fullmatch(value["locator_handle"]):
            raise VectorError("INVALID_OPAQUE_LOCATOR")
        validate_scope_value(value["scope"], ["governance"])
        if value["classification"] not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
            raise VectorError("INVALID_OPAQUE_LOCATOR")
        return
    if kind == "full_ref":
        validate_full_ref_syntax(value)
        if value["subject_schema"] in spec.get("targets", []):
            expected = MACHINE_SCHEMAS[value["subject_schema"]]["object_type"]
            if value["object_type"] != expected:
                raise VectorError("TYPE_SCHEMA_MISMATCH")
            return
        classes = spec.get("external_classes", [])
        if classes:
            resolve_external(value, classes)
            return
        raise VectorError("REF_TARGET_MISMATCH")
    if kind in {"set", "ordered"}:
        if not isinstance(value, list):
            raise VectorError("TYPE_MISMATCH")
        if not spec.get("min_items", 0) <= len(value):
            raise VectorError("COLLECTION_CARDINALITY")
        if spec.get("max_items") is not None and len(value) > spec["max_items"]:
            raise VectorError("COLLECTION_CARDINALITY")
        if kind == "set":
            validate_sorted_set(value)
        for item in value:
            validate_value(item, spec["item"])
        return
    if kind == "closed_integer_map":
        if not isinstance(value, dict) or set(value) != set(spec["keys"]):
            raise VectorError("UNKNOWN_OR_MISSING_FIELD")
        for item in value.values():
            if type(item) is not int or item < spec.get("minimum", 0):
                raise VectorError("TYPE_MISMATCH")
        return
    if kind == "closed_ref_map":
        if not isinstance(value, dict) or set(value) != set(spec["keys"]):
            raise VectorError("UNKNOWN_OR_MISSING_FIELD")
        target_spec = {"kind": "full_ref", "targets": spec["targets"]}
        for item in value.values():
            validate_value(item, target_spec)
        return
    if kind == "decimal_value":
        if not isinstance(value, dict) or set(value) != {"coefficient", "scale"}:
            raise VectorError("INVALID_DECIMAL")
        if not isinstance(value["coefficient"], str) or not DECIMAL_COEFFICIENT_RE.fullmatch(value["coefficient"]):
            raise VectorError("INVALID_DECIMAL_COEFFICIENT")
        if type(value["scale"]) is not int or not 0 <= value["scale"] <= 18:
            raise VectorError("INVALID_DECIMAL_SCALE")
        return
    raise VectorError("UNKNOWN_CONTRACT_PROFILE")


def validate_closed_subject(subject: dict[str, Any], *, allow_conformance_only: bool = False) -> None:
    if not isinstance(subject, dict):
        raise VectorError("TYPE_MISMATCH")
    schema_id = subject.get("subject_schema")
    if not isinstance(schema_id, str):
        raise VectorError("TYPE_MISMATCH")
    definition = MACHINE_SCHEMAS.get(schema_id)
    if definition is None:
        raise VectorError("UNKNOWN_CONTRACT_PROFILE")
    if definition.get("acceptance_class") != "product" and not allow_conformance_only:
        raise VectorError("CONFORMANCE_ONLY_SCHEMA")
    fields = definition["fields"]
    if set(subject) != set(fields):
        raise VectorError("UNKNOWN_OR_MISSING_FIELD")
    for field_name, field_spec in fields.items():
        validate_value(subject[field_name], field_spec)
    validate_subject_rules(subject, definition["rule_ids"])


def validate_subject_rules(subject: dict[str, Any], rule_ids: list[str]) -> None:
    schema_id = subject["subject_schema"]
    if any(rule_id not in RULE_LAYER for rule_id in rule_ids):
        raise VectorError("UNKNOWN_CONTRACT_PROFILE")
    if "suite-denominator" in rule_ids:
        counts = subject["status_counts"]
        expected = CONFORMANCE["profile_contract"]["suite"]
        if (
            subject["suite_id"] != expected["suite_id"]
            or subject["denominator"] != expected["denominator"]
            or counts != expected["status_counts"]
            or sum(counts.values()) != subject["denominator"]
        ):
            raise VectorError("SUITE_DENOMINATOR_INVALID")
    if "control-manifest" in rule_ids:
        if subject["truth_frozen_before_fixture"] is not True:
            raise VectorError("REFERENCE_FINAL_REQUIRED")
        if subject["expected_value_author_ref"]["object_id"] != subject["fixture_author_ref"]["object_id"]:
            raise VectorError("ROLE_ASSIGNMENT_INVALID")
        if subject["expected_value_author_ref"]["object_id"] == subject["reviewer_ref"]["object_id"]:
            raise VectorError("ROLE_SEPARATION_REQUIRED")
        if subject["fixture_author_ref"]["object_id"] == subject["reviewer_ref"]["object_id"]:
            raise VectorError("ROLE_SEPARATION_REQUIRED")
    if "oracle-provenance" in rule_ids:
        if subject["author_ref"]["object_id"] == subject["reviewer_ref"]["object_id"]:
            raise VectorError("ROLE_SEPARATION_REQUIRED")
    if "reference-candidate-set" in rule_ids:
        if subject["denominator"] != 2 or len(subject["candidate_refs"]) != 2:
            raise VectorError("REFERENCE_CANDIDATE_SET_INVALID")
    if "reference-selection-receipt" in rule_ids:
        predecessor = subject["predecessor_receipt_ref"]
        transition = subject["transition_ref"]
        if (predecessor is None) != (transition is None):
            raise VectorError("REFERENCE_RESELECTION_INVALID")
    if "concept-resolution-evidence" in rule_ids:
        if not (
            subject["term_well_formed"] is True
            and subject["semantic_area_status"] == "KNOWN"
            and subject["resolution_completed"] is True
            and subject["binding_count"] == 0
            and subject["authorization_classification"] == "ELIGIBLE"
            and subject["query_engine_access_count"] == 0
        ):
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    if "execution-evidence-boundary" in rule_ids:
        validate_boundary_subject(subject)
    if "execution-evidence-concept" in rule_ids:
        concept_ref = subject["concept_resolution_evidence_ref"]
        if subject["boundary_code"] == "CONCEPT_NOT_BOUND":
            if concept_ref is None:
                raise VectorError("CONCEPT_EVIDENCE_REQUIRED")
        elif concept_ref is not None:
            raise VectorError("CONCEPT_EVIDENCE_FORBIDDEN")
    if "generic-authority-decision" in rule_ids:
        validate_generic_authority_shape(subject)
    if "reference-selection-authority" in rule_ids:
        if (
            subject["action"] != "SELECT_REFERENCE"
            or subject["purpose"] != "ontology-build"
            or not same(subject["scope"], subject["proposed_action_subject_ref"]["scope"])
            or parse_time(subject["issued_at"]) >= parse_time(subject["expires_at"])
        ):
            raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if "gate-evaluation" in rule_ids:
        if (
            not same(subject["scope"], subject["gate_subject_ref"]["scope"])
            or parse_time(subject["issued_at"]) >= parse_time(subject["expires_at"])
        ):
            raise VectorError("SCOPE_MISMATCH")
    if "verification-attempt" in rule_ids:
        if not (
            same(subject["scope"], subject["gate_evaluation_ref"]["scope"])
            and same(subject["scope"], subject["authority_decision_ref"]["scope"])
        ):
            raise VectorError("SCOPE_MISMATCH")
    if "execution-eligibility" in rule_ids:
        if parse_time(subject["evaluated_at"]) >= parse_time(subject["valid_until"]):
            raise VectorError("ELIGIBILITY_INVALID")
        if subject["decision"] == "ALLOW" and subject["reason_codes"] != [
            "ACTIVE",
            "ATTESTATIONS_VALID",
            "AUTHORIZED",
            "NOT_REVOKED",
            "SEALED",
        ]:
            raise VectorError("ELIGIBILITY_INVALID")
    if "payload-disclosure-evaluation" in rule_ids:
        if parse_time(subject["issued_at"]) >= parse_time(subject["expires_at"]):
            raise VectorError("DISCLOSURE_BLOCKED")
    if schema_id == "policy-decision-subject/1":
        if (
            parse_time(subject["evaluated_at"]) >= parse_time(subject["valid_until"])
            or (subject["decision"] == "ALLOW" and subject["reason_codes"] != ["POLICY_MATCH"])
        ):
            raise VectorError("POLICY_DECISION_INVALID")


def validate_generic_authority_shape(subject: dict[str, Any]) -> None:
    action = subject["action"]
    contract = CONFORMANCE["profile_contract"]["authority_action_contract"].get(action)
    if contract is None:
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    resource_ref = subject["proposed_action_subject_ref"]
    expected_kind = (
        scope_kind(resource_ref["scope"])
        if contract["scope_kind"] == "same_as_resource"
        else contract["scope_kind"]
    )
    if scope_kind(subject["scope"]) != expected_kind or not same(subject["scope"], resource_ref["scope"]):
        raise VectorError("SCOPE_MISMATCH")
    if subject["purpose"] not in contract["purposes"]:
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    target_schema_ok = resource_ref["subject_schema"] in contract.get("target_schemas", [])
    target_external_ok = False
    if contract.get("target_external_classes"):
        target_external_ok = (
            resolve_external(resource_ref, contract["target_external_classes"])["leaf_class"]
            in contract["target_external_classes"]
        )
    if not (target_schema_ok or target_external_ok):
        raise VectorError("AUTHORITY_RESOURCE_INVALID")
    if parse_time(subject["issued_at"]) >= parse_time(subject["expires_at"]):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if subject["decision"] == "ALLOW" and subject["reason_codes"] != ["ROLE_AND_SCOPE_MATCH"]:
        raise VectorError("AUTHORITY_DENIED_OR_STALE")


def walk_full_refs(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if FULL_REF_FIELDS.issubset(value):
            yield value
            return
        for child in value.values():
            yield from walk_full_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_full_refs(child)


def validate_embedded_refs(subject: dict[str, Any]) -> None:
    for ref_value in walk_full_refs(subject):
        validate_full_ref_syntax(ref_value)


def validate_boundary_subject(subject: dict[str, Any]) -> None:
    status = subject["candidate_status"]
    code = subject["boundary_code"]
    count = subject["query_engine_access_count"]
    if status == "ANSWER_CANDIDATE":
        if code is not None or count < 1:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    elif status == "CLARIFY":
        if code != "MISSING_PERIOD" or count != 0:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    elif status == "REFUSED":
        if code not in {"UNSUPPORTED_PREDICTION", "RAW_DETAIL_DENIED", "ROLE_DENIED", "CONCEPT_NOT_BOUND"} or count != 0:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    elif status == "FAILED_PRECONDITION":
        if code is None:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    elif status == "FAILED_EXECUTION":
        if code is None:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    else:
        raise VectorError("BOUNDARY_MAPPING_INVALID")


def verify_positive(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for vector in document["positive"]:
        try:
            subject = parse(vector["input_json"])
            validate_closed_subject(subject, allow_conformance_only=True)
            actual = render(subject)
            digest = subject_digest(vector["subject_schema"], actual)
            if actual != vector["canonical_json"]:
                failures.append(f"{vector['id']}: canonical bytes differ")
            if digest != vector["subject_digest"]:
                failures.append(f"{vector['id']}: digest differs")
        except Exception as exc:
            failures.append(f"{vector['id']}: unexpected {type(exc).__name__}: {exc}")
    return failures


def exercise_legacy_negative(vector: dict[str, Any]) -> None:
    validation = vector["validation"]
    if "raw_utf8_hex" in vector:
        raw = bytes.fromhex(vector["raw_utf8_hex"])
        if raw.startswith(b"\xef\xbb\xbf"):
            raise VectorError("UTF8_BOM_FORBIDDEN")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VectorError("INVALID_UTF8") from exc
        parse(text)
        return
    if validation == "registry":
        case = vector["registry_case"]
        if case["existing_digest"] != case["incoming_digest"]:
            raise VectorError("IDENTITY_CONFLICT")
        return
    text = vector["input_json"]
    if validation == "raw-number" and re.search(r":-0(?:[,}])", text):
        raise VectorError("NEGATIVE_ZERO_FORBIDDEN")
    parsed = parse(text)
    if validation in {"raw-json", "canonical"}:
        render(parsed)
        return
    if validation == "timestamp":
        validate_timestamp(parsed["issued_at"])
        return
    if validation == "base-subject":
        if parsed.get("subject_schema") is None:
            raise VectorError("NULL_NOT_ALLOWED")
        return
    if validation == "canonical-test-schema":
        if set(parsed) - LEGACY_SCHEMA_FIELDS["canonical-test-subject/1"]:
            raise VectorError("UNKNOWN_FIELD")
        return
    if validation in {"set", "ref-set"}:
        validate_sorted_set(parsed["limitations"] if validation == "set" else parsed["refs"])
        return
    if validation == "digest":
        if not DIGEST_RE.fullmatch(parsed["subject_digest"]):
            raise VectorError("INVALID_DIGEST")
        return
    if validation == "version":
        if parsed["object_version"] in RESERVED_VERSIONS:
            raise VectorError("RESERVED_VERSION")
        return
    if validation == "decimal":
        value = parsed["decimal_value"]
        if not DECIMAL_COEFFICIENT_RE.fullmatch(value["coefficient"]):
            raise VectorError("INVALID_DECIMAL_COEFFICIENT")
        if type(value["scale"]) is not int or not 0 <= value["scale"] <= 18:
            raise VectorError("INVALID_DECIMAL_SCALE")
        return
    if validation == "runtime-scope":
        if set(parsed["scope"]) != expected_scope_keys("runtime"):
            raise VectorError("INVALID_SCOPE_SHAPE")
        return
    raise AssertionError(f"unhandled legacy validation {validation}")


def same(left: Any, right: Any) -> bool:
    return render(left) == render(right)


def domain_digest(domain: str, value: Any) -> str:
    return "sha-256:" + hashlib.sha256(
        domain.encode("utf-8") + b"\x00" + render(value).encode("utf-8")
    ).hexdigest()


def expected_selection_key_digest(scope: dict[str, Any], candidate_set_ref: dict[str, Any]) -> str:
    return domain_digest(
        "spc-reference-selection-key-v1",
        {
            "scope": copy.deepcopy(scope),
            "candidate_set_subject_digest": candidate_set_ref["subject_digest"],
        },
    )


def expected_request_identity_digest(receipt: dict[str, Any]) -> str:
    return domain_digest(
        "spc-reference-selection-request-v1",
        {
            "candidate_set_ref": copy.deepcopy(receipt["candidate_set_ref"]),
            "selection_proposal_ref": copy.deepcopy(receipt["selection_proposal_ref"]),
            "selection_authority_decision_ref": copy.deepcopy(
                receipt["selection_authority_decision_ref"]
            ),
            "reference_manifest_ref": copy.deepcopy(receipt["reference_manifest_ref"]),
        },
    )


def expected_journal_record_digest(receipt: dict[str, Any]) -> str:
    return domain_digest(
        "spc-reference-selection-logical-record-v1",
        {
            key: copy.deepcopy(value)
            for key, value in receipt.items()
            if key not in BASE_FIELDS | {"journal_record_digest"}
        },
    )


def fixture_evaluation_time() -> dt.datetime:
    return parse_time(CONFORMANCE["conformance_contract"]["fixture_evaluation_time"])


def validate_candidate_set(case: dict[str, Any]) -> None:
    refs = case["candidate_refs"]
    ids = case["candidate_case_ids"]
    suites = case["candidate_suite_refs"]
    if len(refs) != 2 or len({render(ref) for ref in refs}) != 2:
        raise VectorError("REFERENCE_CANDIDATE_SET_INVALID")
    if len(ids) != 2 or len(set(ids)) != 2 or case["denominator"] != len(refs):
        raise VectorError("REFERENCE_CANDIDATE_SET_INVALID")
    if len(suites) != 2 or any(not same(item, case["shared_suite_manifest_ref"]) for item in suites):
        raise VectorError("REFERENCE_CANDIDATE_SET_INVALID")


def validate_selection_proposal(case: dict[str, Any]) -> None:
    selected = case["selected_candidate_ref"]
    if not any(same(selected, member) for member in case["set_members"]):
        raise VectorError("REFERENCE_SELECTED_CANDIDATE_INVALID")
    if case["selected_reference_case_id"] != case["selected_candidate_case_id"]:
        raise VectorError("REFERENCE_SELECTED_CANDIDATE_INVALID")


def parse_time(value: str) -> dt.datetime:
    validate_timestamp(value)
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")


def validate_selection_authority(case: dict[str, Any]) -> None:
    if scope_kind(case["scope"]) != "governance":
        raise VectorError("SCOPE_MISMATCH")
    if case["action"] != "SELECT_REFERENCE" or case["decision"] != "ALLOW":
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if case["purpose"] != "ontology-build" or not same(case["proposed_action_subject_ref"], case["expected_proposal_ref"]):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if (
        case["trusted_principal_id"] != "principal.reference-truth-owner"
        or case["trusted_role_id"]
        != "role-assignment.reference-truth-owner.reference-truth-owner"
    ):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if case["trust_epoch"] != case["current_trust_epoch"]:
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if parse_time(case["evaluated_at"]) >= parse_time(case["expires_at"]):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")


def validate_final_reference(case: dict[str, Any]) -> None:
    if case["selection_authority_decision_ref"] is None:
        raise VectorError("REFERENCE_FINAL_INVALID")
    if not same(case["selection_proposal_ref"], case["expected_proposal_ref"]):
        raise VectorError("REFERENCE_FINAL_INVALID")
    if not same(case["selected_tuple"], case["final_tuple"]):
        raise VectorError("REFERENCE_FINAL_INVALID")
    if case["decision_action"] != "SELECT_REFERENCE" or case["decision_outcome"] != "ALLOW":
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if not same(case["decision_proposed_action_subject_ref"], case["selection_proposal_ref"]):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")


def selection_key(scope: dict[str, Any], candidate_set_digest: str) -> tuple[str, str]:
    return render(scope), candidate_set_digest


def commit_selection(
    journal: dict[tuple[str, str], dict[str, Any]],
    scope: dict[str, Any],
    candidate_set_digest: str,
    attempt: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    key = selection_key(scope, candidate_set_digest)
    current = journal.get(key)
    identity = {
        "proposal_ref": attempt["proposal_ref"],
        "decision_ref": attempt["decision_ref"],
        "final_digest": attempt["final_digest"],
    }
    if current is not None:
        if same(current["identity"], identity):
            return "RETRY", current
        raise VectorError("REFERENCE_SELECTION_CONFLICT")
    record = {"identity": copy.deepcopy(identity), "manifest_id": attempt["manifest_id"], "manifest_version": attempt["manifest_version"]}
    journal[key] = record
    return "COMMITTED", record


def validate_commit_sequence(case: dict[str, Any]) -> None:
    journal: dict[tuple[str, str], dict[str, Any]] = {}
    for attempt in case["attempts"]:
        commit_selection(journal, case["scope"], case["candidate_set_digest"], attempt)


def validate_fixture_timeline(case: dict[str, Any]) -> None:
    if not case["reference_manifest_committed"] and case["fixture_write_count"]:
        raise VectorError("REFERENCE_FINAL_REQUIRED")


def validate_downstream(case: dict[str, Any]) -> None:
    if not same(case["payload_reference_manifest_ref"], case["selected_reference_manifest_ref"]):
        raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
    if not same(case["control_gate_reference_manifest_ref"], case["selected_reference_manifest_ref"]):
        raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
    if not same(case["payload_control_ref"], case["selected_control_ref"]):
        raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
    if not same(case["control_gate_control_ref"], case["selected_control_ref"]):
        raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")


def validate_boundary_case(case: dict[str, Any]) -> None:
    status = case["candidate_status"]
    code = case["boundary_code"]
    if code == "CONCEPT_NOT_BOUND":
        if status != "REFUSED" or case["query_engine_access_count"] != 0:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
        if not case["well_formed_term"] or not case["known_semantic_area"]:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
        if case["allowed_alias_binding_count"] != 0 or not case["role_authorized"]:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
    elif status == "CLARIFY" and code != "MISSING_PERIOD":
        raise VectorError("BOUNDARY_MAPPING_INVALID")


def validate_feedback(case: dict[str, Any]) -> None:
    if case["reported_outcome"] != case["persisted_outcome"]:
        raise VectorError("ANALYTIC_OUTCOME_MUTATED")
    if case["feedback_state"] in {"DISCLOSURE_DENIED", "OUTBOX_FAILED"} and case["scr_count"] != 0:
        raise VectorError("DISCLOSURE_BLOCKED")


SEMANTIC_VALIDATORS = {
    "candidate-set": validate_candidate_set,
    "selection-proposal": validate_selection_proposal,
    "selection-authority": validate_selection_authority,
    "final-reference": validate_final_reference,
    "selection-commit-sequence": validate_commit_sequence,
    "fixture-timeline": validate_fixture_timeline,
    "downstream-selection": validate_downstream,
    "boundary-mapping": validate_boundary_case,
    "feedback-isolation": validate_feedback,
}


def verify_negative(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for vector in document["negative"]:
        try:
            if vector["validation"] in SEMANTIC_VALIDATORS:
                SEMANTIC_VALIDATORS[vector["validation"]](vector["case"])
            else:
                exercise_legacy_negative(vector)
        except VectorError as exc:
            if exc.code != vector["expected_error"]:
                failures.append(f"{vector['id']}: expected {vector['expected_error']}, got {exc.code}")
        except Exception as exc:
            failures.append(f"{vector['id']}: unexpected {type(exc).__name__}: {exc}")
        else:
            failures.append(f"{vector['id']}: accepted but expected {vector['expected_error']}")
    return failures


def mutate_schema_sample(subject: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(subject)
    field = mutation["field"]
    operation = mutation["operation"]
    if operation == "remove":
        result.pop(field)
    elif operation == "wrong_type":
        value = result[field]
        if type(value) is bool:
            result[field] = 0
        elif type(value) is int:
            result[field] = False
        elif isinstance(value, str):
            result[field] = {}
        elif isinstance(value, list):
            result[field] = {}
        elif isinstance(value, dict):
            result[field] = []
        else:
            result[field] = {}
    elif operation == "unknown_enum":
        result[field] = (
            ["__UNKNOWN_CONTRACT_VALUE__"]
            if isinstance(result[field], list)
            else "__UNKNOWN_CONTRACT_VALUE__"
        )
    elif operation == "invalid_ref_target":
        value = result[field]
        if isinstance(value, list):
            nested = copy.deepcopy(value[0]) if value else copy.deepcopy(EXTERNAL_MANIFEST["entries"][0]["ref"])
            nested["object_type"] = "unknown-object"
            nested["subject_schema"] = "unknown-subject/9"
            result[field] = [nested]
        elif isinstance(value, dict) and set(value) != FULL_REF_FIELDS:
            first_key = next(iter(value))
            nested = copy.deepcopy(value[first_key])
            nested["object_type"] = "unknown-object"
            nested["subject_schema"] = "unknown-subject/9"
            value[first_key] = nested
            result[field] = value
        else:
            if not isinstance(value, dict):
                value = copy.deepcopy(EXTERNAL_MANIFEST["entries"][0]["ref"])
            value["object_type"] = "unknown-object"
            value["subject_schema"] = "unknown-subject/9"
            result[field] = value
    elif operation == "noncanonical_set":
        value = result[field]
        if isinstance(value, list) and value:
            result[field] = [copy.deepcopy(value[0]), copy.deepcopy(value[0])]
        else:
            result[field] = ["duplicate", "duplicate"]
    elif operation == "malformed_timestamp":
        result[field] = "2026-08-19T00:00:00Z"
    elif operation == "nonascii_version":
        result[field] = "版本一"
    elif operation == "invalid_identifier":
        result[field] = "INVALID ID"
    elif operation == "wildcard_scope":
        result[field]["tenant_id"] = "*"
    elif operation == "locator_path_injection":
        result[field]["raw_path"] = "/restricted/source.pdf"
    elif operation == "remove_map_key":
        result[field].pop(next(iter(result[field])))
    elif operation == "invalid_decimal":
        result[field]["coefficient"] = "+01"
    else:
        raise VectorError("UNKNOWN_MUTATION_OPERATION")
    return result


def verify_schema_mutations(document: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    passed: list[str] = []
    mutations = document.get("schema_mutations", [])
    if document.get("schema_mutation_count") != len(mutations):
        failures.append("schema mutation count mismatch")
    positives = {vector["id"]: vector for vector in document.get("positive", [])}
    coverage: set[tuple[str, str, str]] = set()
    ids: set[str] = set()

    def unwrap(spec: dict[str, Any]) -> dict[str, Any]:
        return spec["item"] if spec["kind"] == "nullable" else spec

    def contains_kind(spec: dict[str, Any], wanted: str) -> bool:
        spec = unwrap(spec)
        if spec["kind"] == wanted:
            return True
        if spec["kind"] in {"set", "ordered"}:
            return contains_kind(spec["item"], wanted)
        return wanted == "full_ref" and spec["kind"] == "closed_ref_map"

    def contains_enum(spec: dict[str, Any]) -> bool:
        spec = unwrap(spec)
        if spec.get("enum"):
            return True
        return spec["kind"] in {"set", "ordered"} and contains_enum(spec["item"])
    for mutation in mutations:
        mutation_id = mutation.get("id")
        if mutation_id in ids:
            failures.append(f"duplicate mutation id {mutation_id}")
            continue
        ids.add(mutation_id)
        vector = positives.get(mutation.get("positive_id"))
        if vector is None or vector.get("subject_schema") != mutation.get("subject_schema"):
            failures.append(f"{mutation_id}: positive/schema binding invalid")
            continue
        coverage.add((mutation["subject_schema"], mutation["field"], mutation["operation"]))
        try:
            subject = parse(vector["input_json"])
            mutated = mutate_schema_sample(subject, mutation)
            validate_closed_subject(mutated, allow_conformance_only=True)
        except VectorError:
            passed.append(mutation_id)
        except Exception as exc:
            failures.append(f"{mutation_id}: unexpected {type(exc).__name__}: {exc}")
        else:
            failures.append(f"{mutation_id}: accepted invalid mutation")
    for schema_id, definition in MACHINE_SCHEMAS.items():
        if not any(vector.get("subject_schema") == schema_id for vector in positives.values()):
            failures.append(f"schema positive missing {schema_id}")
        for field, raw_spec in definition["fields"].items():
            for operation in ("remove", "wrong_type"):
                if (schema_id, field, operation) not in coverage:
                    failures.append(f"mutation coverage missing {schema_id}.{field}.{operation}")
            spec = unwrap(raw_spec)
            if contains_enum(raw_spec) and (schema_id, field, "unknown_enum") not in coverage:
                failures.append(f"enum mutation missing {schema_id}.{field}")
            if contains_kind(raw_spec, "full_ref") and (schema_id, field, "invalid_ref_target") not in coverage:
                failures.append(f"ref mutation missing {schema_id}.{field}")
    return failures, passed


def identity_key(value: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        render(value["scope"]), value["object_type"], value["object_id"], value["object_version"],
        value["contract_version"], value["canonicalization_profile"],
    )


class IntegratedGraph:
    def __init__(self, block: dict[str, Any]):
        self.context = block["context"]
        self.by_key: dict[str, dict[str, Any]] = {}
        self.by_identity: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
        self.record_by_identity: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
        for record in block["subjects"]:
            if set(record) != {
                "key",
                "subject_schema",
                "input_json",
                "canonical_json",
                "subject_digest",
            }:
                raise VectorError("UNKNOWN_OR_MISSING_FIELD")
            if record["key"] in self.by_key:
                raise VectorError("IDENTITY_CONFLICT")
            subject = parse(record["input_json"])
            validate_closed_subject(subject)
            if record["subject_schema"] != subject["subject_schema"]:
                raise VectorError("TYPE_SCHEMA_MISMATCH")
            canonical = render(subject)
            digest = subject_digest(subject["subject_schema"], canonical)
            if canonical != record["canonical_json"] or digest != record["subject_digest"]:
                raise VectorError("DIGEST_MISMATCH")
            key = identity_key(subject)
            if key in self.by_identity:
                raise VectorError("IDENTITY_CONFLICT")
            self.by_key[record["key"]] = subject
            self.by_identity[key] = subject
            self.record_by_identity[key] = record

    def resolve(self, ref: dict[str, Any]) -> dict[str, Any]:
        validate_full_ref_syntax(ref)
        external_entry = EXTERNAL_BY_REF.get(render(ref))
        if external_entry is not None:
            return external_entry
        expected_schema = MACHINE_TYPE_SCHEMA.get(ref["object_type"])
        if expected_schema is None or expected_schema != ref["subject_schema"]:
            raise VectorError("TYPE_SCHEMA_MISMATCH")
        target = self.by_identity.get(identity_key(ref))
        if target is None:
            raise VectorError("UNRESOLVED_FULL_REF")
        record = self.record_by_identity[identity_key(ref)]
        if record["subject_digest"] != ref["subject_digest"] or target["subject_schema"] != ref["subject_schema"] or not same(target["scope"], ref["scope"]):
            raise VectorError("DIGEST_MISMATCH")
        return target

    def walk_refs(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            if FULL_REF_FIELDS.issubset(value):
                yield value
                return
            for child in value.values():
                yield from self.walk_refs(child)
        elif isinstance(value, list):
            for child in value:
                yield from self.walk_refs(child)

    def validate_all_refs(self) -> None:
        for subject in self.by_key.values():
            for ref in self.walk_refs(subject):
                if not scope_coordinates_match(subject["scope"], ref["scope"]):
                    raise VectorError("SCOPE_MISMATCH")
                self.resolve(ref)

    def validate_acyclic(self) -> None:
        state: dict[tuple[str, str, str, str, str, str], int] = {}

        def visit(subject: dict[str, Any]) -> None:
            key = identity_key(subject)
            if state.get(key) == 1:
                raise VectorError("DEPENDENCY_CYCLE")
            if state.get(key) == 2:
                return
            state[key] = 1
            for ref in self.walk_refs(subject):
                resolved = self.resolve(ref)
                if resolved.get("subject_schema") in MACHINE_SCHEMAS:
                    visit(resolved)
            state[key] = 2

        for subject in self.by_key.values():
            visit(subject)


def ref_tuple(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "reference_case_id": candidate["reference_case_id"],
        "cleared_input_ref": candidate["cleared_input_ref"],
        "control_manifest_ref": candidate["control_manifest_ref"],
        "suite_manifest_ref": candidate["suite_manifest_ref"],
        "oracle_provenance_ref": candidate["oracle_provenance_ref"],
    }


def validate_authority_use(
    graph: IntegratedGraph,
    decision_ref: dict[str, Any],
    action: str,
    resource_ref: dict[str, Any],
    purpose: str,
    at_time: dt.datetime,
) -> dict[str, Any]:
    decision = graph.resolve(decision_ref)
    if decision["subject_schema"] not in {
        "authority-decision-subject/1",
        "reference-selection-authority-decision-subject/1",
    }:
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if not (
        decision["action"] == action
        and decision["purpose"] == purpose
        and decision["decision"] == "ALLOW"
        and same(decision["proposed_action_subject_ref"], resource_ref)
        and same(decision["scope"], resource_ref["scope"])
        and parse_time(decision["issued_at"]) <= at_time < parse_time(decision["expires_at"])
    ):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    session = graph.resolve(decision["trusted_session_ref"])
    principal = graph.resolve(decision["principal_ref"])
    registry = graph.resolve(decision["principal_registry_ref"])
    assignment = graph.resolve(decision["role_assignment_ref"])
    if any(
        not same(item["scope"], decision["scope"])
        for item in (session, principal, registry, assignment)
    ):
        raise VectorError("SCOPE_MISMATCH")
    session_facts = session["facts"]
    principal_facts = principal["facts"]
    registry_facts = registry["facts"]
    assignment_facts = assignment["facts"]
    if not (
        session["leaf_class"] == "TRUSTED_SESSION"
        and principal["leaf_class"] == "PRINCIPAL"
        and registry["leaf_class"] == "PRINCIPAL_REGISTRY"
        and assignment["leaf_class"] == "ROLE_ASSIGNMENT"
        and session_facts["principal_object_id"] == decision["principal_ref"]["object_id"]
        and principal_facts["registry_object_id"] == decision["principal_registry_ref"]["object_id"]
        and assignment_facts["principal_object_id"] == decision["principal_ref"]["object_id"]
        and action in assignment_facts["allowed_actions"]
        and session_facts["trust_epoch"] == decision["trust_epoch"]
        and registry_facts["trust_epoch"] == decision["trust_epoch"]
        and assignment_facts["trust_epoch"] == decision["trust_epoch"]
        and parse_time(session_facts["issued_at"]) <= at_time < parse_time(session_facts["expires_at"])
        and parse_time(assignment_facts["issued_at"]) <= at_time < parse_time(assignment_facts["expires_at"])
    ):
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    if action == "SELECT_REFERENCE" and assignment_facts["role_code"] != "reference-truth-owner":
        raise VectorError("AUTHORITY_DENIED_OR_STALE")
    for policy_ref in decision["policy_refs"]:
        policy = graph.resolve(policy_ref)
        facts = policy["facts"]
        if not (
            policy["leaf_class"] == "STATIC_POLICY"
            and same(policy["scope"], decision["scope"])
            and action in facts["allowed_actions"]
            and purpose in facts["allowed_purposes"]
            and parse_time(facts["effective_at"]) <= at_time < parse_time(facts["expires_at"])
        ):
            raise VectorError("AUTHORITY_DENIED_OR_STALE")
    return decision


def validate_policy_use(
    graph: IntegratedGraph,
    policy_decision_ref: dict[str, Any],
    resource_ref: dict[str, Any],
    purpose: str,
    action: str,
    at_time: dt.datetime,
) -> dict[str, Any]:
    decision = graph.resolve(policy_decision_ref)
    if not (
        decision["subject_schema"] == "policy-decision-subject/1"
        and decision["decision"] == "ALLOW"
        and decision["purpose"] == purpose
        and decision["resource_refs"] == [resource_ref]
        and parse_time(decision["evaluated_at"]) <= at_time < parse_time(decision["valid_until"])
    ):
        raise VectorError("POLICY_DECISION_INVALID")
    principal_context = graph.resolve(decision["principal_context_ref"])
    if not (
        principal_context["leaf_class"] == "PRINCIPAL_CONTEXT"
        and same(principal_context["scope"], decision["scope"])
        and principal_context["facts"]["purpose"] == purpose
    ):
        raise VectorError("POLICY_DECISION_INVALID")
    for policy_ref in decision["policy_refs"]:
        policy = graph.resolve(policy_ref)
        facts = policy["facts"]
        if not (
            policy["leaf_class"] == "STATIC_POLICY"
            and same(policy["scope"], decision["scope"])
            and action in facts["allowed_actions"]
            and purpose in facts["allowed_purposes"]
            and parse_time(facts["effective_at"]) <= at_time < parse_time(facts["expires_at"])
        ):
            raise VectorError("POLICY_DECISION_INVALID")
    return decision


GATE_SUBJECT_SCHEMAS = {
    "SEMANTIC_APPROVAL": "semantic-approval-subject/1",
    "BINDING_DATA_VALIDATION": "binding-data-validation-subject/1",
    "DISCLOSURE_POLICY_CLEARANCE": "disclosure-policy-subject/1",
    "RUNTIME_CAPABILITY_COMPATIBILITY": "runtime-capability-subject/1",
    "CONTROL_GOLDEN_EVALUATION": "control-golden-subject/1",
}


def validate_gate_attempt(
    graph: IntegratedGraph,
    gate_name: str,
    attempt_ref: dict[str, Any],
    at_time: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = graph.resolve(attempt_ref)
    evaluation = graph.resolve(attempt["gate_evaluation_ref"])
    gate_subject = graph.resolve(evaluation["gate_subject_ref"])
    if not (
        evaluation["gate_type"] == gate_name
        and evaluation["outcome"] == "PASS"
        and gate_subject["subject_schema"] == GATE_SUBJECT_SCHEMAS[gate_name]
        and same(evaluation["scope"], gate_subject["scope"])
        and same(attempt["scope"], evaluation["scope"])
        and parse_time(evaluation["issued_at"]) <= at_time < parse_time(evaluation["expires_at"])
    ):
        raise VectorError("MISSING_OR_INVALID_ATTESTATION")
    validate_authority_use(
        graph,
        attempt["authority_decision_ref"],
        "ATTEST",
        attempt["gate_evaluation_ref"],
        "governed-analysis-demo",
        at_time,
    )
    return evaluation, gate_subject


def validate_receipt_derivations(graph: IntegratedGraph, receipt: dict[str, Any]) -> None:
    candidate_set = graph.resolve(receipt["candidate_set_ref"])
    proposal = graph.resolve(receipt["selection_proposal_ref"])
    authority = graph.resolve(receipt["selection_authority_decision_ref"])
    manifest = graph.resolve(receipt["reference_manifest_ref"])
    commit_time = parse_time(receipt["committed_at"])
    if not (
        receipt["commit_status"] == "COMMITTED"
        and same(proposal["candidate_set_ref"], receipt["candidate_set_ref"])
        and same(manifest["selection_proposal_ref"], receipt["selection_proposal_ref"])
        and same(
            manifest["selection_authority_decision_ref"],
            receipt["selection_authority_decision_ref"],
        )
        and receipt["authority_trust_epoch"] == authority["trust_epoch"]
        and any(
            same(receipt["authority_policy_snapshot_ref"], policy_ref)
            for policy_ref in authority["policy_refs"]
        )
        and authority["policy_refs"] == [candidate_set["selection_policy_ref"]]
        and same(
            receipt["authority_policy_snapshot_ref"],
            candidate_set["selection_policy_ref"],
        )
        and receipt["selection_key_digest"]
        == expected_selection_key_digest(receipt["scope"], receipt["candidate_set_ref"])
        and receipt["request_identity_digest"] == expected_request_identity_digest(receipt)
        and receipt["journal_record_digest"] == expected_journal_record_digest(receipt)
        and parse_time(candidate_set["frozen_at"])
        <= parse_time(authority["issued_at"])
        <= parse_time(manifest["frozen_at"])
        <= commit_time
    ):
        raise VectorError("REFERENCE_RECEIPT_DERIVATION_INVALID")
    validate_authority_use(
        graph,
        receipt["selection_authority_decision_ref"],
        "SELECT_REFERENCE",
        receipt["selection_proposal_ref"],
        "ontology-build",
        commit_time,
    )


def expected_empty_revocation_digest(scope: dict[str, Any], epoch: int) -> str:
    return domain_digest(
        "spc-revocation-set-v1",
        {"scope": copy.deepcopy(scope), "epoch": epoch, "active_revocation_refs": []},
    )


def validate_eligibility(
    graph: IntegratedGraph,
    eligibility_ref: dict[str, Any],
    expected_phase: str,
) -> dict[str, Any]:
    eligibility = graph.resolve(eligibility_ref)
    at_time = parse_time(eligibility["evaluated_at"])
    seal = graph.by_key["seal_proposal"]
    vrs = graph.by_key["vrs"]
    expected_head = None if expected_phase == "ACTIVATE" else graph.context["activation_record_ref"]
    if not (
        eligibility["phase"] == expected_phase
        and eligibility["purpose"] == "governed-analysis-demo"
        and eligibility["decision"] == "ALLOW"
        and at_time < parse_time(eligibility["valid_until"])
        and same(eligibility["vrs_ref"], graph.context["vrs_ref"])
        and same(
            eligibility["runtime_snapshot_payload_ref"],
            graph.context["runtime_payload_ref"],
        )
        and eligibility["verification_attempt_refs_by_gate"]
        == seal["verification_attempt_refs_by_gate"]
        and same(eligibility["activation_head_ref"], expected_head)
        and eligibility["revocation_scope_epoch"] == 0
        and eligibility["observed_revocation_set_digest"]
        == expected_empty_revocation_digest(eligibility["scope"], 0)
        and vrs["seal_status"] == "SEALED"
    ):
        raise VectorError("ELIGIBILITY_INVALID")
    for gate_name, attempt_ref in eligibility["verification_attempt_refs_by_gate"].items():
        validate_gate_attempt(graph, gate_name, attempt_ref, at_time)
    action = expected_phase
    authority = graph.resolve(eligibility["request_authority_decision_ref"])
    authority_resource = authority["proposed_action_subject_ref"]
    validate_authority_use(
        graph,
        eligibility["request_authority_decision_ref"],
        action,
        authority_resource,
        eligibility["purpose"],
        at_time,
    )
    if expected_phase == "ACTIVATE":
        if not same(authority_resource, graph.by_key["activation_record"]["intent_ref"]):
            raise VectorError("ELIGIBILITY_INVALID")
        policy_resource = eligibility["vrs_ref"]
    else:
        activation_record = graph.resolve(eligibility["activation_head_ref"])
        activation_intent = graph.resolve(activation_record["intent_ref"])
        if not (
            activation_record["subject_schema"] == "activation-record-subject/1"
            and activation_intent["subject_schema"] == "activation-intent-subject/1"
            and activation_intent["action"] == "ACTIVATE"
            and same(activation_intent["vrs_ref"], eligibility["vrs_ref"])
            and parse_time(activation_record["committed_at"]) <= at_time
        ):
            raise VectorError("SNAPSHOT_NOT_ACTIVE")
    if expected_phase == "PRE_QUERY":
        request = graph.resolve(authority_resource)
        if request["leaf_class"] != "REQUEST":
            raise VectorError("ELIGIBILITY_INVALID")
        policy_resource = eligibility["vrs_ref"]
    elif expected_phase != "ACTIVATE":
        evidence = graph.resolve(authority_resource)
        if evidence["subject_schema"] != "execution-evidence-subject/2":
            raise VectorError("ELIGIBILITY_INVALID")
        policy_resource = authority_resource
    validate_policy_use(
        graph,
        eligibility["policy_decision_ref"],
        policy_resource,
        eligibility["purpose"],
        expected_phase,
        at_time,
    )
    return eligibility


def validate_result_release_commit(
    graph: IntegratedGraph,
    commit_ref: dict[str, Any],
    evidence_ref: dict[str, Any],
) -> dict[str, Any]:
    commit = graph.resolve(commit_ref)
    evidence = graph.resolve(evidence_ref)
    eligibility = validate_eligibility(
        graph, commit["result_release_eligibility_ref"], "RESULT_RELEASE"
    )
    projection_ref = evidence["user_projection_ref"]
    committed_at = parse_time(commit["committed_at"])
    if not (
        projection_ref is not None
        and same(commit["execution_evidence_ref"], evidence_ref)
        and same(commit["user_projection_ref"], projection_ref)
        and same(commit["activation_head_ref"], graph.context["activation_record_ref"])
        and same(commit["vrs_ref"], graph.context["vrs_ref"])
        and same(commit["policy_decision_ref"], eligibility["policy_decision_ref"])
        and commit["revocation_scope_epoch"] == eligibility["revocation_scope_epoch"]
        and parse_time(evidence["completed_at"])
        <= parse_time(eligibility["evaluated_at"])
        <= committed_at
        < parse_time(eligibility["valid_until"])
    ):
        raise VectorError("RESULT_RELEASE_INVALID")
    return commit


def verify_integrated(document: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    passed: list[str] = []
    try:
        graph = IntegratedGraph(document["integrated_graph"])
    except Exception as exc:
        return [f"integrated graph load: {type(exc).__name__}: {exc}"], passed

    def check(name: str, fn: Any) -> None:
        try:
            fn()
            passed.append(name)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    def refs_for_schema(schema_id: str) -> set[str]:
        refs: set[str] = set()
        for subject in graph.by_key.values():
            if subject["subject_schema"] != schema_id:
                continue
            record = graph.record_by_identity[identity_key(subject)]
            refs.add(
                render(ref_from_record_subject(subject, record["subject_digest"]))
            )
        return refs

    check("I01-all-full-refs-resolve", graph.validate_all_refs)
    check("I02-dependency-graph-acyclic", graph.validate_acyclic)

    def truth_chain() -> None:
        candidate_set = graph.by_key["candidate_set"]
        predecessor_set = graph.by_key["candidate_set_predecessor"]
        members = [graph.resolve(ref) for ref in candidate_set["candidate_refs"]]
        validate_candidate_set(
            {
                "candidate_refs": candidate_set["candidate_refs"],
                "candidate_case_ids": [item["reference_case_id"] for item in members],
                "candidate_suite_refs": [item["suite_manifest_ref"] for item in members],
                "shared_suite_manifest_ref": candidate_set["shared_suite_manifest_ref"],
                "denominator": candidate_set["denominator"],
            }
        )
        for candidate in members:
            control = graph.resolve(candidate["control_manifest_ref"])
            cleared_input = graph.resolve(candidate["cleared_input_ref"])
            oracle = graph.resolve(candidate["oracle_provenance_ref"])
            input_proposal = graph.resolve(cleared_input["proposal_ref"])
            validate_authority_use(
                graph,
                cleared_input["input_disclosure_authority_decision_ref"],
                "APPROVE_CLEARED_INPUT",
                cleared_input["proposal_ref"],
                "ontology-build",
                parse_time(candidate["frozen_at"]),
            )
            if not (
                control["reference_case_id"] == candidate["reference_case_id"]
                and oracle["reference_case_id"] == candidate["reference_case_id"]
                and same(oracle["cleared_input_ref"], candidate["cleared_input_ref"])
                and same(input_proposal["scope"], candidate["scope"])
                and same(
                    input_proposal["opaque_source_locator_ref"]["scope"],
                    input_proposal["scope"],
                )
                and input_proposal["opaque_source_locator_ref"]["classification"]
                == input_proposal["classification"]
                and control["oracle_provenance_refs"] == [candidate["oracle_provenance_ref"]]
            ):
                raise VectorError("REFERENCE_CANDIDATE_SET_INVALID")
        proposal = graph.by_key["selection_proposal"]
        selected_candidate = graph.resolve(proposal["selected_candidate_ref"])
        validate_selection_proposal(
            {
                "set_members": candidate_set["candidate_refs"],
                "selected_candidate_ref": proposal["selected_candidate_ref"],
                "selected_candidate_case_id": selected_candidate["reference_case_id"],
                "selected_reference_case_id": proposal["selected_reference_case_id"],
            }
        )
        authority = graph.by_key["selection_authority"]
        manifest = graph.by_key["reference_manifest"]
        validate_final_reference(
            {
                "selected_tuple": ref_tuple(selected_candidate),
                "final_tuple": {key: manifest[key] for key in ref_tuple(selected_candidate)},
                "selection_proposal_ref": manifest["selection_proposal_ref"],
                "expected_proposal_ref": graph.context["selection_proposal_ref"],
                "selection_authority_decision_ref": manifest["selection_authority_decision_ref"],
                "decision_action": authority["action"], "decision_outcome": authority["decision"],
                "decision_proposed_action_subject_ref": authority["proposed_action_subject_ref"],
            }
        )
        predecessor_members = [
            graph.resolve(ref) for ref in predecessor_set["candidate_refs"]
        ]
        validate_candidate_set(
            {
                "candidate_refs": predecessor_set["candidate_refs"],
                "candidate_case_ids": [
                    item["reference_case_id"] for item in predecessor_members
                ],
                "candidate_suite_refs": [
                    item["suite_manifest_ref"] for item in predecessor_members
                ],
                "shared_suite_manifest_ref": predecessor_set["shared_suite_manifest_ref"],
                "denominator": predecessor_set["denominator"],
            }
        )
        predecessor_proposal = graph.by_key["selection_proposal_predecessor"]
        predecessor_selected = graph.resolve(
            predecessor_proposal["selected_candidate_ref"]
        )
        validate_selection_proposal(
            {
                "set_members": predecessor_set["candidate_refs"],
                "selected_candidate_ref": predecessor_proposal["selected_candidate_ref"],
                "selected_candidate_case_id": predecessor_selected["reference_case_id"],
                "selected_reference_case_id": predecessor_proposal[
                    "selected_reference_case_id"
                ],
            }
        )
        predecessor_manifest = graph.by_key["reference_manifest_predecessor"]
        predecessor_authority = graph.resolve(
            predecessor_manifest["selection_authority_decision_ref"]
        )
        validate_final_reference(
            {
                "selected_tuple": ref_tuple(predecessor_selected),
                "final_tuple": {
                    key: predecessor_manifest[key]
                    for key in ref_tuple(predecessor_selected)
                },
                "selection_proposal_ref": predecessor_manifest[
                    "selection_proposal_ref"
                ],
                "expected_proposal_ref": graph.context[
                    "predecessor_selection_proposal_ref"
                ],
                "selection_authority_decision_ref": predecessor_manifest[
                    "selection_authority_decision_ref"
                ],
                "decision_action": predecessor_authority["action"],
                "decision_outcome": predecessor_authority["decision"],
                "decision_proposed_action_subject_ref": predecessor_authority[
                    "proposed_action_subject_ref"
                ],
            }
        )
        transition = graph.resolve(proposal["reselection_transition_ref"])
        predecessor_receipt = graph.by_key["selection_receipt_predecessor"]
        current_receipt = graph.by_key["selection_receipt"]
        actual_changed: list[dict[str, Any]] = []
        if candidate_set["candidate_refs"] != predecessor_set["candidate_refs"]:
            prior = {render(item) for item in predecessor_set["candidate_refs"]}
            actual_changed.extend(
                item for item in candidate_set["candidate_refs"] if render(item) not in prior
            )
        if not same(
            candidate_set["shared_suite_manifest_ref"],
            predecessor_set["shared_suite_manifest_ref"],
        ):
            actual_changed.append(candidate_set["shared_suite_manifest_ref"])
        if not same(candidate_set["selection_policy_ref"], predecessor_set["selection_policy_ref"]):
            actual_changed.append(candidate_set["selection_policy_ref"])
        if not (
            candidate_set["object_id"] == predecessor_set["object_id"]
            and candidate_set["object_version"] != predecessor_set["object_version"]
            and predecessor_proposal["reselection_transition_ref"] is None
            and same(
                proposal["reselection_transition_ref"],
                current_receipt["transition_ref"],
            )
            and same(transition["predecessor_candidate_set_ref"], graph.context["predecessor_candidate_set_ref"])
            and same(
                transition["predecessor_reference_manifest_ref"],
                graph.context["predecessor_reference_manifest_ref"],
            )
            and same(
                transition["predecessor_commit_receipt_ref"],
                graph.context["predecessor_selection_receipt_ref"],
            )
            and transition["change_reason_code"] == "POLICY_CHANGE"
            and transition["changed_component_refs"] == sorted(actual_changed, key=render)
            and parse_time(predecessor_receipt["committed_at"])
            <= parse_time(transition["evaluated_at"])
            <= parse_time(current_receipt["committed_at"])
            and same(current_receipt["predecessor_receipt_ref"], graph.context["predecessor_selection_receipt_ref"])
            and same(current_receipt["transition_ref"], graph.context["selection_transition_ref"])
            and current_receipt["commit_sequence"] == predecessor_receipt["commit_sequence"] + 1
            and same(current_receipt["candidate_set_ref"], graph.context["candidate_set_ref"])
            and same(current_receipt["reference_manifest_ref"], graph.context["reference_manifest_ref"])
            and same(predecessor_manifest["selection_proposal_ref"], graph.context["predecessor_selection_proposal_ref"])
        ):
            raise VectorError("REFERENCE_RESELECTION_INVALID")
        validate_receipt_derivations(graph, predecessor_receipt)
        validate_receipt_derivations(graph, current_receipt)
        receipts = [
            subject
            for subject in graph.by_key.values()
            if subject["subject_schema"] == "reference-selection-commit-receipt-subject/1"
        ]
        selection_keys = [item["selection_key_digest"] for item in receipts]
        receipt_refs = {
            render(
                ref_from_record_subject(
                    item,
                    graph.record_by_identity[identity_key(item)]["subject_digest"],
                )
            )
            for item in receipts
        }
        expected_receipt_refs = {
            render(graph.context["predecessor_selection_receipt_ref"]),
            render(graph.context["selection_receipt_ref"]),
        }
        if (
            len(selection_keys) != len(set(selection_keys))
            or receipt_refs != expected_receipt_refs
        ):
            raise VectorError("REFERENCE_SELECTION_CONFLICT")

    check("I03-truth-selection-chain", truth_chain)

    def authority_roots() -> None:
        observed_actions: set[str] = set()
        for key, decision in graph.by_key.items():
            if decision["subject_schema"] not in {
                "authority-decision-subject/1",
                "reference-selection-authority-decision-subject/1",
            }:
                continue
            observed_actions.add(decision["action"])
            record = graph.record_by_identity[identity_key(decision)]
            decision_ref = ref_from_record_subject(decision, record["subject_digest"])
            validate_authority_use(
                graph,
                decision_ref,
                decision["action"],
                decision["proposed_action_subject_ref"],
                decision["purpose"],
                parse_time(decision["issued_at"]),
            )
        expected_actions = set(CONFORMANCE["profile_contract"]["generic_authority_actions"]) | {
            CONFORMANCE["profile_contract"]["selection_authority_action"]
        }
        if observed_actions != expected_actions:
            raise VectorError(
                f"AUTHORITY_ACTION_COVERAGE_INVALID:{sorted(expected_actions - observed_actions)}"
            )

    check("I04-authority-trust-roots", authority_roots)

    def committed_selection_receipt() -> None:
        context = graph.context
        receipt = graph.resolve(context["selection_receipt_ref"])
        if not (
            receipt["commit_status"] == "COMMITTED"
            and receipt["commit_sequence"] == 2
            and same(receipt["predecessor_receipt_ref"], context["predecessor_selection_receipt_ref"])
            and same(receipt["transition_ref"], context["selection_transition_ref"])
            and same(receipt["candidate_set_ref"], context["candidate_set_ref"])
            and same(receipt["selection_proposal_ref"], context["selection_proposal_ref"])
            and same(receipt["selection_authority_decision_ref"], context["selection_authority_ref"])
            and same(receipt["reference_manifest_ref"], context["reference_manifest_ref"])
        ):
            raise VectorError("REFERENCE_FINAL_INVALID")
        validate_receipt_derivations(graph, receipt)

    check("I05-committed-selection-receipt", committed_selection_receipt)

    def downstream() -> None:
        context = graph.context
        payload = graph.by_key["runtime_payload"]
        control_gate = graph.by_key["control_gate_subject"]
        validate_downstream(
            {
                "selected_reference_manifest_ref": context["reference_manifest_ref"],
                "selected_control_ref": context["selected_control_ref"],
                "payload_reference_manifest_ref": payload["reference_manifest_ref"],
                "payload_control_ref": payload["control_manifest_ref"],
                "control_gate_reference_manifest_ref": control_gate["reference_manifest_ref"],
                "control_gate_control_ref": control_gate["control_manifest_ref"],
            }
        )
        gsr = graph.by_key["gsr"]
        publish = graph.resolve(gsr["publish_subject_ref"])
        receipt = graph.resolve(publish["selection_commit_receipt_ref"])
        manifest = graph.resolve(publish["selected_reference_manifest_ref"])
        semantic_content = graph.resolve(publish["semantic_content_ref"])
        semantic_decision = graph.resolve(publish["decision_refs"][0])
        runtime_gate = graph.by_key["runtime_gate_subject"]
        selected_tuple = {
            "control_manifest_ref": context["selected_control_ref"],
            "suite_manifest_ref": context["selected_suite_ref"],
            "reference_manifest_ref": context["reference_manifest_ref"],
            "oracle_provenance_ref": context["selected_oracle_ref"],
        }
        if not (
            same(publish["selected_reference_manifest_ref"], context["reference_manifest_ref"])
            and same(receipt["reference_manifest_ref"], context["reference_manifest_ref"])
            and same(receipt["selection_proposal_ref"], context["selection_proposal_ref"])
            and same(receipt["selection_authority_decision_ref"], context["selection_authority_ref"])
            and same(receipt["candidate_set_ref"], context["candidate_set_ref"])
            and same(semantic_content["reference_manifest_ref"], context["reference_manifest_ref"])
            and same(
                publish["semantic_schema_ref"],
                semantic_content["semantic_schema_ref"],
            )
            and parse_time(receipt["committed_at"])
            <= parse_time(semantic_content["built_at"])
            and same(runtime_gate["gsr_semantic_content_ref"], publish["semantic_content_ref"])
            and publish["cleared_input_refs"] == [context["selected_input_ref"]]
            and publish["decision_refs"] == [context["semantic_decision_ref"]]
            and semantic_decision["leaf_class"] == "SEMANTIC_DECISION"
            and semantic_decision["facts"]["decision_profile"]
            == CONFORMANCE["profile_contract"]["semantic_decision_profile"]
            and semantic_decision["facts"]["source_cleared_input_subject_digest"]
            == context["selected_input_ref"]["subject_digest"]
            and semantic_decision["facts"]["candidate_subject_digest"]
            == context["selected_candidate_ref"]["subject_digest"]
            and all(
                same(manifest[field], ref)
                for field, ref in selected_tuple.items()
                if field != "reference_manifest_ref"
            )
            and all(same(payload[field], ref) for field, ref in selected_tuple.items())
            and all(same(control_gate[field], ref) for field, ref in selected_tuple.items())
        ):
            raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
        gsr = graph.by_key["gsr"]
        validate_authority_use(
            graph,
            gsr["publish_authority_decision_ref"],
            "PUBLISH",
            gsr["publish_subject_ref"],
            "governed-analysis-demo",
            fixture_evaluation_time(),
        )
        label = context["demo_label"]
        if label["reference_case_id"] != context["selected_case_id"] or not same(label["reference_manifest_ref"], context["reference_manifest_ref"]):
            raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
        if "non-customer-validation" not in label["limitations"]:
            raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")
        forbidden = [
            context["unselected_candidate_ref"], context["unselected_input_ref"],
            context["unselected_control_ref"], context["unselected_oracle_ref"],
        ]
        downstream_started = False
        for key, subject in graph.by_key.items():
            downstream_started = downstream_started or key == "gsr_publish"
            if not downstream_started:
                continue
            for nested_ref in graph.walk_refs(subject):
                if any(same(nested_ref, blocked) for blocked in forbidden):
                    raise VectorError("REFERENCE_DOWNSTREAM_MISMATCH")

    check("I06-selected-identity-downstream", downstream)

    def gsr_vrs_chain() -> None:
        seal = graph.by_key["seal_proposal"]
        vrs = graph.by_key["vrs"]
        selection_receipt = graph.by_key["selection_receipt"]
        data_identity = graph.by_key["data_identity"]
        attempts = seal["verification_attempt_refs_by_gate"]
        if set(attempts) != FIVE_GATES:
            raise VectorError("MISSING_OR_INVALID_ATTESTATION")
        for gate_name, attempt_ref in attempts.items():
            evaluation, _gate_subject = validate_gate_attempt(
                graph, gate_name, attempt_ref, fixture_evaluation_time()
            )
            if parse_time(selection_receipt["committed_at"]) > parse_time(
                evaluation["issued_at"]
            ):
                raise VectorError("MISSING_OR_INVALID_ATTESTATION")
            if gate_name == "SEMANTIC_APPROVAL" and parse_time(
                graph.by_key["semantic_content"]["built_at"]
            ) > parse_time(evaluation["issued_at"]):
                raise VectorError("MISSING_OR_INVALID_ATTESTATION")
            if gate_name in {
                "BINDING_DATA_VALIDATION",
                "CONTROL_GOLDEN_EVALUATION",
            } and parse_time(data_identity["frozen_at"]) > parse_time(
                evaluation["issued_at"]
            ):
                raise VectorError("MISSING_OR_INVALID_ATTESTATION")
            if not set(evaluation["limitations"]).issubset(set(vrs["limitations"])):
                raise VectorError("MISSING_OR_INVALID_ATTESTATION")
        publish = graph.by_key["gsr_publish"]
        payload = graph.by_key["runtime_payload"]
        semantic_subject = graph.by_key["semantic_gate_subject"]
        binding_subject = graph.by_key["binding_gate_subject"]
        disclosure_subject = graph.by_key["disclosure_gate_subject"]
        runtime_subject = graph.by_key["runtime_gate_subject"]
        control_subject = graph.by_key["control_gate_subject"]
        if not (
            same(semantic_subject["gsr_publish_subject_ref"], graph.by_key["gsr"]["publish_subject_ref"])
            and same(payload["gsr_ref"], graph.context["gsr_ref"])
            and same(seal["runtime_snapshot_payload_ref"], graph.context["runtime_payload_ref"])
            and same(binding_subject["gsr_binding_requirements_ref"], publish["binding_requirements_ref"])
            and same(binding_subject["runtime_semantic_projection_ref"], payload["runtime_semantic_projection_ref"])
            and same(binding_subject["binding_bundle_ref"], payload["binding_bundle_ref"])
            and same(binding_subject["data_identity_ref"], payload["data_identity_ref"])
            and same(disclosure_subject["gsr_disclosure_labels_ref"], publish["disclosure_labels_ref"])
            and same(disclosure_subject["gsr_policy_requirements_ref"], publish["policy_requirements_ref"])
            and same(disclosure_subject["runtime_semantic_projection_ref"], payload["runtime_semantic_projection_ref"])
            and same(disclosure_subject["projection_policy_bundle_ref"], payload["projection_policy_bundle_ref"])
            and same(runtime_subject["gsr_semantic_content_ref"], publish["semantic_content_ref"])
            and same(runtime_subject["runtime_semantic_projection_ref"], payload["runtime_semantic_projection_ref"])
            and same(runtime_subject["runtime_capability_manifest_ref"], payload["runtime_capability_manifest_ref"])
            and same(runtime_subject["compatibility_profile_ref"], payload["compatibility_profile_ref"])
            and same(runtime_subject["projection_fidelity_report_ref"], disclosure_subject["projection_fidelity_report_ref"])
            and same(control_subject["runtime_snapshot_payload_ref"], graph.context["runtime_payload_ref"])
            and same(control_subject["control_manifest_ref"], payload["control_manifest_ref"])
            and same(control_subject["suite_manifest_ref"], payload["suite_manifest_ref"])
            and same(control_subject["reference_manifest_ref"], payload["reference_manifest_ref"])
            and same(control_subject["oracle_provenance_ref"], payload["oracle_provenance_ref"])
            and same(control_subject["evaluation_runner_manifest_ref"], payload["evaluation_runner_manifest_ref"])
        ):
            raise VectorError("GATE_SUBJECT_LINEAGE_INVALID")
        gsr = graph.by_key["gsr"]
        if not same(gsr["semantic_approval_attempt_ref"], attempts["SEMANTIC_APPROVAL"]):
            raise VectorError("MISSING_OR_INVALID_ATTESTATION")
        seal_authority = graph.resolve(vrs["seal_authority_decision_ref"])
        if (
            vrs["seal_status"] != "SEALED"
            or not same(vrs["seal_proposal_ref"], graph.context["seal_proposal_ref"])
        ):
            raise VectorError("MISSING_OR_INVALID_ATTESTATION")
        validate_authority_use(
            graph,
            vrs["seal_authority_decision_ref"],
            "SEAL",
            vrs["seal_proposal_ref"],
            "governed-analysis-demo",
            fixture_evaluation_time(),
        )
        activation = validate_eligibility(
            graph, graph.by_key["activation_record"]["eligibility_decision_ref"], "ACTIVATE"
        )
        activation_record = graph.by_key["activation_record"]
        activation_intent = graph.by_key["activation_intent"]
        if (
            refs_for_schema("activation-record-subject/1")
            != {render(graph.context["activation_record_ref"])}
            or refs_for_schema("revocation-record-subject/1")
        ):
            raise VectorError("SNAPSHOT_NOT_ACTIVE")
        if not (
            same(activation, graph.by_key["activation_eligibility"])
            and same(activation_record["intent_ref"], graph.by_key["activation_authority"]["proposed_action_subject_ref"])
            and same(activation_record["authority_decision_ref"], activation["request_authority_decision_ref"])
            and activation_record["sequence"] == 1
            and activation_record["previous_record_ref"] is None
            and activation_record["activation_epoch"] == 1
            and activation_intent["action"] == "ACTIVATE"
            and activation_intent["expected_head_ref"] is None
            and activation_intent["expected_activation_epoch"] == 0
            and activation_intent["reason_code"] == "INITIAL"
            and same(activation_intent["vrs_ref"], graph.context["vrs_ref"])
            and parse_time(activation_intent["requested_at"])
            <= parse_time(activation["evaluated_at"])
            and parse_time(activation["evaluated_at"])
            <= parse_time(activation_record["committed_at"])
            < parse_time(activation["valid_until"])
        ):
            raise VectorError("SNAPSHOT_NOT_ACTIVE")
        if graph.resolve(graph.by_key["activation_record"]["intent_ref"]) is not graph.by_key["activation_intent"]:
            raise VectorError("DIGEST_MISMATCH")

    check("I07-gsr-vrs-activation-chain", gsr_vrs_chain)

    def five_outcomes() -> None:
        outcomes = graph.context["outcomes"]
        if set(outcomes) != {"ANSWERED", "CLARIFY", "REFUSED", "FAILED_PRECONDITION", "FAILED_EXECUTION"}:
            raise VectorError("BOUNDARY_MAPPING_INVALID")
        expected_status = {"ANSWERED": "ANSWER_CANDIDATE", "CLARIFY": "CLARIFY", "REFUSED": "REFUSED", "FAILED_PRECONDITION": "FAILED_PRECONDITION", "FAILED_EXECUTION": "FAILED_EXECUTION"}
        prequery = validate_eligibility(
            graph, graph.context["prequery_eligibility_ref"], "PRE_QUERY"
        )
        release_commits: list[dict[str, Any]] = []
        for outcome, refs in outcomes.items():
            evidence = graph.resolve(refs["evidence_ref"])
            if not (
                evidence["candidate_status"] == expected_status[outcome]
                and evidence["purpose"] == "governed-analysis-demo"
                and same(evidence["gsr_ref"], graph.context["gsr_ref"])
                and same(evidence["vrs_ref"], graph.context["vrs_ref"])
                and same(evidence["activation_record_ref"], graph.context["activation_record_ref"])
                and same(evidence["pre_query_eligibility_ref"], graph.context["prequery_eligibility_ref"])
                and same(evidence["policy_decision_ref"], prequery["policy_decision_ref"])
                and same(
                    evidence["data_identity_ref"],
                    graph.by_key["runtime_payload"]["data_identity_ref"],
                )
                and parse_time(prequery["evaluated_at"])
                <= parse_time(evidence["started_at"])
                <= parse_time(evidence["completed_at"])
                < parse_time(prequery["valid_until"])
            ):
                raise VectorError("BOUNDARY_MAPPING_INVALID")
            if evidence["user_projection_ref"] is not None:
                projection = graph.resolve(evidence["user_projection_ref"])
                if projection["execution_id"] != evidence["execution_id"]:
                    raise VectorError("EVIDENCE_INCOMPLETE")
            if "release_commit_ref" in refs:
                release_commits.append(
                    validate_result_release_commit(
                        graph, refs["release_commit_ref"], refs["evidence_ref"]
                    )
                )
        ordered_commits = sorted(release_commits, key=lambda item: item["commit_sequence"])
        expected_release_refs = {
            render(refs["release_commit_ref"])
            for refs in outcomes.values()
            if "release_commit_ref" in refs
        }
        if (
            refs_for_schema("result-release-commit-subject/1")
            != expected_release_refs
            or
            [item["commit_sequence"] for item in ordered_commits]
            != list(range(1, len(ordered_commits) + 1))
            or [parse_time(item["committed_at"]) for item in ordered_commits]
            != sorted(parse_time(item["committed_at"]) for item in ordered_commits)
        ):
            raise VectorError("RESULT_RELEASE_INVALID")

    check("I08-five-outcomes-release", five_outcomes)

    def concept_boundary() -> None:
        evidence = graph.resolve(graph.context["concept_evidence_ref"])
        resolution = graph.resolve(evidence["concept_resolution_evidence_ref"])
        eligibility = validate_eligibility(
            graph, resolution["pre_query_eligibility_ref"], "PRE_QUERY"
        )
        policy = graph.resolve(resolution["policy_decision_ref"])
        if not (
            evidence["candidate_status"] == "REFUSED"
            and evidence["boundary_code"] == "CONCEPT_NOT_BOUND"
            and evidence["query_engine_access_count"] == 0
            and evidence["plan_ref"] is None
            and evidence["query_ref"] is None
            and resolution["execution_id"] == evidence["execution_id"]
            and resolution["term_well_formed"] is True
            and resolution["semantic_area_code"] == "MARKET_METRICS"
            and resolution["semantic_area_status"] == "KNOWN"
            and resolution["resolution_completed"] is True
            and resolution["binding_count"] == 0
            and resolution["authorization_classification"] == "ELIGIBLE"
            and resolution["query_engine_access_count"] == 0
            and same(resolution["pre_query_eligibility_ref"], evidence["pre_query_eligibility_ref"])
            and same(resolution["policy_decision_ref"], evidence["policy_decision_ref"])
            and same(resolution["pre_query_eligibility_ref"], graph.context["prequery_eligibility_ref"])
            and eligibility["decision"] == "ALLOW"
            and policy["decision"] == "ALLOW"
            and parse_time(eligibility["evaluated_at"])
            <= parse_time(resolution["evaluated_at"])
            < parse_time(eligibility["valid_until"])
        ):
            raise VectorError("BOUNDARY_MAPPING_INVALID")

    check("I10-concept-not-bound-immutable-evidence", concept_boundary)

    def evidence_read() -> None:
        validate_eligibility(
            graph, graph.context["evidence_read_eligibility_ref"], "EVIDENCE_READ"
        )

    check("I11-evidence-read-authorized", evidence_read)

    def scr_chain() -> None:
        scr = graph.resolve(graph.context["scr_ref"])
        enqueue = graph.resolve(scr["enqueue_proposal_ref"])
        enqueue_authority = graph.resolve(scr["requester_authority_decision_ref"])
        disclosure = graph.resolve(enqueue["payload_disclosure_decision_ref"])
        disclosure_authority = graph.resolve(disclosure["disclosure_authority_decision_ref"])
        evaluation = graph.resolve(disclosure["evaluation_ref"])
        payload = graph.resolve(enqueue["proposed_payload_ref"])
        boundary = graph.resolve(payload["boundary_execution_ref"])
        release = graph.resolve(payload["boundary_release_commit_ref"])
        concept_resolution = graph.resolve(boundary["concept_resolution_evidence_ref"])
        safe_entries = [
            graph.resolve(payload["safe_detail_artifact_ref"]),
            graph.resolve(payload["safe_term_alias_ref"]),
            graph.resolve(payload["interaction_handle_ref"]),
        ]
        if refs_for_schema("semantic-change-request-subject/1") != {
            render(graph.context["scr_ref"])
        }:
            raise VectorError("SCR_CONFLICT")
        validate_authority_use(
            graph,
            scr["requester_authority_decision_ref"],
            "SCR_ENQUEUE",
            scr["enqueue_proposal_ref"],
            "semantic-change-triage",
            parse_time(enqueue["requested_at"]),
        )
        validate_authority_use(
            graph,
            disclosure["disclosure_authority_decision_ref"],
            "SCR_DISCLOSE",
            disclosure["evaluation_ref"],
            "semantic-change-triage",
            parse_time(evaluation["issued_at"]),
        )
        if (
            evaluation["decision"] != "ALLOW"
            or not same(evaluation["proposed_payload_ref"], enqueue["proposed_payload_ref"])
            or not same(evaluation["safe_detail_artifact_ref"], payload["safe_detail_artifact_ref"])
            or scope_kind(evaluation["source_scope"]) != "channel"
            or scope_kind(evaluation["destination_scope"]) != "governance"
            or evaluation["purpose"] != "semantic-change-triage"
            or not same(evaluation["source_scope"], boundary["scope"])
            or not same(evaluation["destination_scope"], payload["scope"])
            or evaluation["allowed_fields"]
            != [
                "reason_code",
                "safe_detail_artifact_ref",
                "safe_term_alias_ref",
                "semantic_area_code",
            ]
            or evaluation["obligations"]
            != ["NO_RAW_QUESTION", "REAUTHORIZE_REFS"]
            or any(
                entry["facts"]["classification"] != evaluation["classification"]
                for entry in safe_entries
            )
            or enqueue["limitations"]
            != ["no-raw-question", "synthetic-scope"]
            or not (
                parse_time(evaluation["issued_at"])
                <= parse_time(enqueue["requested_at"])
                < parse_time(evaluation["expires_at"])
            )
            or payload["reason_code"] != "CONCEPT_NOT_BOUND"
        ):
            raise VectorError("DISCLOSURE_BLOCKED")
        for policy_ref in evaluation["policy_refs"]:
            policy = graph.resolve(policy_ref)
            facts = policy["facts"]
            if not (
                policy["leaf_class"] == "STATIC_POLICY"
                and "SCR_DISCLOSE" in facts["allowed_actions"]
                and "semantic-change-triage" in facts["allowed_purposes"]
                and parse_time(facts["effective_at"])
                <= parse_time(evaluation["issued_at"])
                < parse_time(facts["expires_at"])
            ):
                raise VectorError("DISCLOSURE_BLOCKED")
        if (
            boundary["candidate_status"] != "REFUSED"
            or boundary["boundary_code"] != "CONCEPT_NOT_BOUND"
            or not same(release["execution_evidence_ref"], payload["boundary_execution_ref"])
            or not same(release["user_projection_ref"], boundary["user_projection_ref"])
            or not same(payload["safe_term_alias_ref"], concept_resolution["safe_term_alias_ref"])
            or not same(payload["observed_gsr_ref"], boundary["gsr_ref"])
            or not same(payload["observed_vrs_ref"], boundary["vrs_ref"])
        ):
            raise VectorError("BOUNDARY_MAPPING_INVALID")
        validate_result_release_commit(
            graph, payload["boundary_release_commit_ref"], payload["boundary_execution_ref"]
        )
        validate_feedback({"persisted_outcome": "REFUSED", "feedback_state": "CREATED", "reported_outcome": "REFUSED", "scr_count": 1})
        validate_feedback({"persisted_outcome": "REFUSED", "feedback_state": "DISCLOSURE_DENIED", "reported_outcome": "REFUSED", "scr_count": 0})
        validate_feedback({"persisted_outcome": "REFUSED", "feedback_state": "OUTBOX_FAILED", "reported_outcome": "REFUSED", "scr_count": 0})

    check("I12-scr-chain-requires-release", scr_chain)

    def suite_unchanged() -> None:
        suite = graph.by_key["suite"]
        if suite["denominator"] != 8 or suite["status_counts"] != {"ANSWERED": 4, "CLARIFY": 1, "REFUSED": 3} or len(suite["cases"]) != 8:
            raise VectorError("SUITE_DENOMINATOR_INVALID")

    check("I13-adt-suite-denominator-unchanged", suite_unchanged)
    return failures, passed


def ref_from_record_subject(subject: dict[str, Any], digest: str) -> dict[str, Any]:
    return {
        "object_type": subject["object_type"],
        "object_id": subject["object_id"],
        "object_version": subject["object_version"],
        "contract_version": subject["contract_version"],
        "subject_schema": subject["subject_schema"],
        "canonicalization_profile": subject["canonicalization_profile"],
        "scope": copy.deepcopy(subject["scope"]),
        "subject_digest": digest,
    }


def rewrite_refs(value: Any, rewrites: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if set(value) == FULL_REF_FIELDS:
            return copy.deepcopy(rewrites.get(render(value), value))
        return {key: rewrite_refs(child, rewrites) for key, child in value.items()}
    if isinstance(value, list):
        return [rewrite_refs(child, rewrites) for child in value]
    return copy.deepcopy(value)


def apply_path_mutation(subject: dict[str, Any], mutation: dict[str, Any]) -> None:
    path = mutation["path"]
    target: Any = subject
    for segment in path[:-1]:
        target = target[segment]
    leaf = path[-1]
    operation = mutation["operation"]
    if operation == "remove":
        target.pop(leaf)
    elif operation == "add":
        if leaf in target:
            raise VectorError("MUTATION_TARGET_EXISTS")
        target[leaf] = copy.deepcopy(mutation["value"])
    elif operation == "set":
        target[leaf] = copy.deepcopy(mutation["value"])
    else:
        raise VectorError("UNKNOWN_MUTATION_OPERATION")


def rebuild_mutated_graph(document: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    block = document["integrated_graph"]
    rewrites: dict[str, dict[str, Any]] = {}
    rebuilt: list[dict[str, Any]] = []
    found = False
    for record in block["subjects"]:
        original_subject = parse(record["input_json"])
        subject = rewrite_refs(original_subject, rewrites)
        if record["key"] == mutation["record_key"]:
            apply_path_mutation(subject, mutation)
            found = True
        canonical = render(subject)
        digest = subject_digest(subject["subject_schema"], canonical)
        rebuilt.append(
            {
                "key": record["key"],
                "subject_schema": subject["subject_schema"],
                "input_json": json.dumps(subject, ensure_ascii=False, separators=(",", ":")),
                "canonical_json": canonical,
                "subject_digest": digest,
            }
        )
        old_ref = ref_from_record_subject(original_subject, record["subject_digest"])
        new_ref = ref_from_record_subject(subject, digest)
        if not same(old_ref, new_ref):
            rewrites[render(old_ref)] = new_ref
    if not found:
        raise VectorError("MUTATION_TARGET_MISSING")
    mutated = copy.deepcopy(document)
    mutated["integrated_graph"] = {
        "subjects": rebuilt,
        "context": rewrite_refs(block["context"], rewrites),
    }
    mutated["integrated_subject_count"] = len(rebuilt)
    return mutated


def verify_integrated_mutations(document: dict[str, Any]) -> tuple[list[str], list[str], dict[str, int]]:
    failures: list[str] = []
    passed: list[str] = []
    categories: dict[str, int] = {}
    mutations = document.get("integrated_mutations", [])
    if document.get("integrated_mutation_count") != len(mutations):
        failures.append("integrated mutation count mismatch")
    ids: set[str] = set()
    for mutation in mutations:
        mutation_id = mutation.get("id")
        if mutation_id in ids:
            failures.append(f"duplicate integrated mutation {mutation_id}")
            continue
        ids.add(mutation_id)
        category = mutation.get("category")
        categories[category] = categories.get(category, 0) + 1
        try:
            mutated = rebuild_mutated_graph(document, mutation)
            graph_failures, _passed = verify_integrated(mutated)
            if not graph_failures:
                failures.append(f"{mutation_id}: accepted invalid integrated graph")
            else:
                passed.append(mutation_id)
        except Exception as exc:
            failures.append(f"{mutation_id}: harness error {type(exc).__name__}: {exc}")
    for required in {"TRUST_ROOT", "FIVE_GATE", "SEAL", "E01", "SELECTED_LINEAGE", "COMPATIBILITY"}:
        if categories.get(required, 0) < 1:
            failures.append(f"integrated mutation category missing {required}")
    return failures, passed, categories


def logical_bound_digest(domain: str, ref_value: dict[str, Any], body: dict[str, Any]) -> str:
    return domain_digest(
        domain,
        {
            "identity": {
                key: copy.deepcopy(value)
                for key, value in ref_value.items()
                if key != "subject_digest"
            },
            "body": copy.deepcopy(body),
        },
    )


def validate_logical_ref(
    ref_value: dict[str, Any], object_type: str, subject_schema: str
) -> None:
    validate_full_ref_syntax(ref_value)
    if (
        ref_value["object_type"] != object_type
        or ref_value["subject_schema"] != subject_schema
        or scope_kind(ref_value["scope"]) != "governance"
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")


def derive_logical_command(command: dict[str, Any]) -> dict[str, Any]:
    if set(command) != {
        "op",
        "command_id",
        "candidate_set",
        "proposal",
        "authority_decision",
        "reference_manifest",
        "crash_cut",
    } or command["op"] != "COMMAND":
        raise VectorError("LOGICAL_TRACE_INVALID")
    state = command["candidate_set"]
    proposal = command["proposal"]
    decision = command["authority_decision"]
    manifest = command["reference_manifest"]
    if set(state) != {
        "ref",
        "candidate_refs",
        "shared_suite_manifest_ref",
        "selection_policy_ref",
    }:
        raise VectorError("LOGICAL_TRACE_INVALID")
    if set(proposal) != {
        "ref",
        "candidate_set_ref",
        "selected_candidate_ref",
        "reselection_transition",
    } or set(decision) != {
        "ref",
        "action",
        "purpose",
        "decision",
        "trust_epoch",
        "proposed_action_subject_ref",
        "policy_snapshot_ref",
    } or set(manifest) != {
        "ref",
        "selection_proposal_ref",
        "selection_authority_decision_ref",
        "selected_candidate_ref",
    }:
        raise VectorError("LOGICAL_TRACE_INVALID")
    validate_logical_ref(
        state["ref"], "reference-candidate-set", "reference-candidate-set-subject/1"
    )
    validate_logical_ref(
        proposal["ref"],
        "reference-selection-proposal",
        "reference-selection-proposal-subject/1",
    )
    validate_logical_ref(
        decision["ref"],
        "reference-selection-authority-decision",
        "reference-selection-authority-decision-subject/1",
    )
    validate_logical_ref(
        manifest["ref"], "reference-manifest", "reference-manifest-subject/2"
    )
    validate_logical_ref(
        state["shared_suite_manifest_ref"], "suite-manifest", "suite-manifest-subject/1"
    )
    validate_logical_ref(
        state["selection_policy_ref"], "static-policy-leaf", "static-policy-leaf/1"
    )
    scoped_refs = [
        proposal["ref"],
        decision["ref"],
        manifest["ref"],
        state["shared_suite_manifest_ref"],
        state["selection_policy_ref"],
        *state["candidate_refs"],
    ]
    if any(not same(item["scope"], state["ref"]["scope"]) for item in scoped_refs):
        raise VectorError("SCOPE_MISMATCH")
    if not isinstance(state["candidate_refs"], list) or len(state["candidate_refs"]) != 2:
        raise VectorError("LOGICAL_TRACE_INVALID")
    validate_sorted_set(state["candidate_refs"])
    for candidate_ref in state["candidate_refs"]:
        validate_logical_ref(
            candidate_ref, "reference-candidate", "reference-candidate-subject/1"
        )
    state_body = {key: value for key, value in state.items() if key != "ref"}
    if state["ref"]["subject_digest"] != logical_bound_digest(
        "spc-logical-candidate-set-v1", state["ref"], state_body
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")
    proposal_body = {key: value for key, value in proposal.items() if key != "ref"}
    if proposal["ref"]["subject_digest"] != logical_bound_digest(
        "spc-logical-selection-proposal-v1", proposal["ref"], proposal_body
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")
    decision_body = {key: value for key, value in decision.items() if key != "ref"}
    if decision["ref"]["subject_digest"] != logical_bound_digest(
        "spc-logical-selection-decision-v1", decision["ref"], decision_body
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")
    manifest_body = {key: value for key, value in manifest.items() if key != "ref"}
    if manifest["ref"]["subject_digest"] != logical_bound_digest(
        "spc-logical-reference-manifest-v1", manifest["ref"], manifest_body
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")
    if not (
        same(proposal["candidate_set_ref"], state["ref"])
        and any(
            same(proposal["selected_candidate_ref"], member)
            for member in state["candidate_refs"]
        )
        and decision["action"] == "SELECT_REFERENCE"
        and decision["purpose"] == "ontology-build"
        and decision["decision"] == "ALLOW"
        and decision["trust_epoch"] == 11
        and same(decision["proposed_action_subject_ref"], proposal["ref"])
        and same(decision["policy_snapshot_ref"], state["selection_policy_ref"])
        and same(manifest["selection_proposal_ref"], proposal["ref"])
        and same(manifest["selection_authority_decision_ref"], decision["ref"])
        and same(manifest["selected_candidate_ref"], proposal["selected_candidate_ref"])
    ):
        raise VectorError("LOGICAL_TRACE_INVALID")
    transition = proposal["reselection_transition"]
    if transition is not None:
        if set(transition) != {
            "predecessor_candidate_set_ref",
            "predecessor_receipt_id",
            "changed_component_refs",
        } or not isinstance(transition["predecessor_receipt_id"], str):
            raise VectorError("LOGICAL_TRACE_INVALID")
        validate_logical_ref(
            transition["predecessor_candidate_set_ref"],
            "reference-candidate-set",
            "reference-candidate-set-subject/1",
        )
        if not same(
            transition["predecessor_candidate_set_ref"]["scope"],
            state["ref"]["scope"],
        ):
            raise VectorError("SCOPE_MISMATCH")
        if not isinstance(transition["changed_component_refs"], list):
            raise VectorError("LOGICAL_TRACE_INVALID")
        validate_sorted_set(transition["changed_component_refs"])
        for changed_ref in transition["changed_component_refs"]:
            validate_full_ref_syntax(changed_ref)
    request_identity = domain_digest(
        "spc-logical-selection-request-v1",
        {
            "candidate_set_ref": state["ref"],
            "selection_proposal_ref": proposal["ref"],
            "selection_authority_decision_ref": decision["ref"],
            "reference_manifest_ref": manifest["ref"],
        },
    )
    material_components = {
        "candidate_refs": state["candidate_refs"],
        "shared_suite_manifest_ref": state["shared_suite_manifest_ref"],
        "selection_policy_ref": state["selection_policy_ref"],
    }
    return {
        "selection_key": expected_selection_key_digest(state["ref"]["scope"], state["ref"]),
        "series_key": render(
            {
                "scope": state["ref"]["scope"],
                "candidate_set_object_id": state["ref"]["object_id"],
            }
        ),
        "request_identity": request_identity,
        "receipt_id": "receipt-" + request_identity.removeprefix("sha-256:")[:16],
        "material_digest": domain_digest(
            "spc-logical-selection-material-v1", material_components
        ),
        "material_components": material_components,
        "candidate_set_ref": state["ref"],
        "transition": transition,
        "crash_cut": command["crash_cut"],
    }


def interpret_transaction_trace(trace: dict[str, Any]) -> dict[str, Any]:
    journal: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    series_heads: dict[str, dict[str, Any]] = {}
    corrupt = False
    results: list[str] = []
    authority_state = "ALLOW"
    read_authorized = True

    def recover() -> bool:
        nonlocal records, series_heads, corrupt, journal
        if any(frame["kind"] == "CORRUPT" for frame in journal):
            corrupt = True
            return False
        journal = [frame for frame in journal if frame.get("durable") is True]
        records = {}
        series_heads = {}
        for frame in journal:
            receipt = frame["receipt"]
            records[receipt["selection_key"]] = receipt
            series_heads[receipt["series_key"]] = receipt
        corrupt = False
        return True

    for step in trace["steps"]:
        if step["op"] == "RESTART":
            results.append(
                "RECOVERED" if recover() else CONFORMANCE["conformance_contract"]["logical_failure_symbol"]
            )
            continue
        if step["op"] == "SET_AUTHORITY_STATE":
            if set(step) != {"op", "outcome"} or step["outcome"] not in {"ALLOW", "DENY"}:
                raise VectorError("LOGICAL_TRACE_INVALID")
            authority_state = step["outcome"]
            continue
        if step["op"] == "SET_READ_AUTHORIZATION":
            if set(step) != {"op", "allowed"} or type(step["allowed"]) is not bool:
                raise VectorError("LOGICAL_TRACE_INVALID")
            read_authorized = step["allowed"]
            continue
        if step["op"] != "COMMAND":
            raise VectorError("LOGICAL_TRACE_INVALID")
        if corrupt:
            results.append(CONFORMANCE["conformance_contract"]["logical_failure_symbol"])
            continue
        try:
            derived = derive_logical_command(step)
        except VectorError:
            results.append("INVALID_COMMAND")
            continue
        existing = records.get(derived["selection_key"])
        if existing is not None:
            if existing["request_identity"] != derived["request_identity"]:
                results.append("REFERENCE_SELECTION_CONFLICT")
            elif read_authorized is not True:
                results.append("READ_DENIED")
            else:
                results.append("RETRY:" + existing["receipt_id"])
            continue
        if authority_state != "ALLOW":
            results.append("AUTHORITY_DENIED_OR_STALE")
            continue
        head = series_heads.get(derived["series_key"])
        transition = derived["transition"]
        if head is None:
            if transition is not None:
                results.append("STALE_PREDECESSOR")
                continue
        else:
            if transition is None or not (
                transition["predecessor_receipt_id"] == head["receipt_id"]
                and same(
                    transition["predecessor_candidate_set_ref"], head["candidate_set_ref"]
                )
            ):
                results.append("STALE_PREDECESSOR")
                continue
            if derived["material_digest"] == head["material_digest"]:
                results.append("MATERIAL_CHANGE_REQUIRED")
                continue
            actual_changed: list[dict[str, Any]] = []
            previous_components = head["material_components"]
            current_components = derived["material_components"]
            previous_candidates = {render(item) for item in previous_components["candidate_refs"]}
            actual_changed.extend(
                item
                for item in current_components["candidate_refs"]
                if render(item) not in previous_candidates
            )
            if not same(
                current_components["shared_suite_manifest_ref"],
                previous_components["shared_suite_manifest_ref"],
            ):
                actual_changed.append(current_components["shared_suite_manifest_ref"])
            if not same(
                current_components["selection_policy_ref"],
                previous_components["selection_policy_ref"],
            ):
                actual_changed.append(current_components["selection_policy_ref"])
            if transition["changed_component_refs"] != sorted(actual_changed, key=render):
                results.append("MATERIAL_CHANGE_REQUIRED")
                continue
        receipt = {
            "receipt_id": derived["receipt_id"],
            "selection_key": derived["selection_key"],
            "series_key": derived["series_key"],
            "request_identity": derived["request_identity"],
            "material_digest": derived["material_digest"],
            "material_components": derived["material_components"],
            "candidate_set_ref": derived["candidate_set_ref"],
        }
        crash_cut = derived["crash_cut"]
        if crash_cut == "BEFORE_APPEND":
            results.append("CRASH_NO_COMMIT")
            continue
        if crash_cut == "MID_FRAME":
            journal.append({"kind": "CORRUPT", "durable": False})
            corrupt = True
            results.append("CRASH_CORRUPT_TAIL")
            continue
        if crash_cut == "AFTER_WRITE_PRE_SYNC":
            journal.append({"kind": "RECEIPT", "durable": False, "receipt": receipt})
            results.append("CRASH_NO_COMMIT")
            continue
        journal.append({"kind": "RECEIPT", "durable": True, "receipt": receipt})
        records[receipt["selection_key"]] = receipt
        series_heads[receipt["series_key"]] = receipt
        if crash_cut == "AFTER_SYNC_PRE_RESPONSE":
            results.append("CRASH_AFTER_COMMIT")
        elif crash_cut is None:
            results.append("COMMITTED:" + receipt["receipt_id"])
        else:
            raise VectorError("LOGICAL_TRACE_INVALID")

    durable = [
        frame["receipt"]["receipt_id"]
        for frame in journal
        if frame.get("kind") == "RECEIPT" and frame.get("durable") is True
    ]
    heads = {key: value["receipt_id"] for key, value in series_heads.items()}
    if len(heads) == 1:
        head_result: Any = next(iter(heads.values()))
    elif not heads:
        head_result = None
    else:
        head_result = heads
    return {
        "results": results,
        "durable_receipts": durable,
        "series_head": head_result,
        "store_state": "CORRUPT_FAIL_CLOSED" if corrupt else "HEALTHY",
    }


def verify_logical_transactions(document: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    passed: list[str] = []
    traces = document.get("logical_transaction_traces", [])
    if document.get("logical_transaction_trace_count") != len(traces) or len(traces) < 16:
        return ["logical transaction trace count mismatch or below 16"], passed
    required_tokens = {
        "exact-retry-before-expiry",
        "exact-retry-after-expiry",
        "conflict-a-then-b",
        "conflict-b-then-a",
        "invalid-first",
        "authority-expires",
        "legal-material-successor",
        "version-time-only",
        "forked-successors",
        "stale-predecessor",
        "crash-before-append",
        "crash-mid-frame",
        "crash-after-write-before-sync",
        "crash-after-sync-before-response",
        "new-independent-series",
        "retry-read-denied",
    }
    ids = {trace.get("id", "") for trace in traces}
    forbidden_truth_fields = {
        "set_key",
        "series_key",
        "valid",
        "material_digest",
        "changed_component_count",
        "request_digest",
        "proposal_digest",
        "decision_digest",
        "manifest_digest",
    }

    def keys_in(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys_in(child) for child in value.values()))
        if isinstance(value, list):
            return set().union(*(keys_in(child) for child in value))
        return set()

    leaked_truth_fields = keys_in(traces) & forbidden_truth_fields
    if leaked_truth_fields:
        failures.append(f"logical traces contain caller truth fields {sorted(leaked_truth_fields)}")
    for token in required_tokens:
        if not any(token in identifier for identifier in ids):
            failures.append(f"logical trace coverage missing {token}")
    for trace in traces:
        try:
            actual = interpret_transaction_trace(trace)
            expected = {
                "results": trace["expected_results"],
                "durable_receipts": trace["expected_durable_receipts"],
                "series_head": trace["expected_series_head"],
                "store_state": trace["expected_store_state"],
            }
            if actual != expected:
                failures.append(f"{trace['id']}: expected {expected}, got {actual}")
            else:
                passed.append(trace["id"])
        except Exception as exc:
            failures.append(f"{trace.get('id')}: {type(exc).__name__}: {exc}")
    return failures, passed


def main() -> int:
    default = Path(__file__).with_name("canonical-json-v1.0-core-1.1-vectors.json")
    arguments = list(sys.argv[1:])
    report_path: Path | None = None
    if "--report" in arguments:
        index = arguments.index("--report")
        if index + 1 >= len(arguments):
            raise SystemExit("--report requires a path")
        report_path = Path(arguments[index + 1])
        del arguments[index : index + 2]
    if len(arguments) > 1:
        raise SystemExit("usage: verify_vectors_core_1_1.py [VECTORS] [--report PATH]")
    path = Path(arguments[0]) if arguments else default
    document = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    conformance_meta = document.get("conformance_manifest", {})
    if (
        conformance_meta.get("filename") != CONFORMANCE_PATH.name
        or conformance_meta.get("sha256") != sha256_file(CONFORMANCE_PATH)
    ):
        failures.append("pinned conformance manifest mismatch")
    try:
        configure_external_manifest(document)
    except Exception as exc:
        failures.append(f"external manifest: {type(exc).__name__}: {exc}")
    provenance = document.get("toolchain_provenance", {})
    predecessor_helper = BASE_DIR / provenance.get("predecessor_helper_filename", "")
    if (
        not predecessor_helper.is_file()
        or sha256_file(predecessor_helper) != provenance.get("predecessor_helper_sha256")
        or provenance.get("python_implementation") != platform.python_implementation()
        or provenance.get("python_version") != platform.python_version()
        or provenance.get("unicode_data_version") != unicodedata.unidata_version
    ):
        failures.append("toolchain provenance mismatch")
    if document.get("fixture_schema") != "shared-contract-core-1.1-vectors/1":
        failures.append("fixture schema mismatch")
    if document.get("contract_version") != CONTRACT or document.get("stage_profile_id") != STAGE_PROFILE or document.get("annex_profile_id") != ANNEX_PROFILE:
        failures.append("contract/profile identity mismatch")
    if document.get("canonicalization_profile") != CANONICAL_PROFILE:
        failures.append("canonicalization profile mismatch")
    failures.extend(verify_positive(document))
    failures.extend(verify_negative(document))
    mutation_failures, passed_mutations = verify_schema_mutations(document)
    failures.extend(mutation_failures)
    integrated_failures, passed_assertions = verify_integrated(document)
    failures.extend(integrated_failures)
    graph_mutation_failures, passed_graph_mutations, mutation_categories = verify_integrated_mutations(document)
    failures.extend(graph_mutation_failures)
    transaction_failures, passed_traces = verify_logical_transactions(document)
    failures.extend(transaction_failures)
    for rule_id, (assertion_id, mutation_id) in RULE_EVIDENCE.items():
        if assertion_id not in passed_assertions or mutation_id not in passed_graph_mutations:
            failures.append(
                f"rule evidence incomplete {rule_id}: assertion={assertion_id} mutation={mutation_id}"
            )
    if document.get("positive_count") != len(document.get("positive", [])) or document.get("positive_count", 0) < 20:
        failures.append("positive count mismatch or below threshold")
    if document.get("negative_count") != len(document.get("negative", [])) or document.get("negative_count", 0) < 20:
        failures.append("negative count mismatch or below threshold")
    if document.get("integrated_subject_count") != len(document.get("integrated_graph", {}).get("subjects", [])):
        failures.append("integrated subject count mismatch")
    if document.get("integrated_assertion_count") != len(passed_assertions):
        failures.append(f"integrated assertion count mismatch: declared {document.get('integrated_assertion_count')} passed {len(passed_assertions)}")
    if failures:
        if report_path is not None:
            report_path.write_text(
                json.dumps(
                    {
                        "status": "FAIL",
                        "failure_count": len(failures),
                        "failures": failures,
                        "rule_evidence_total": len(RULE_EVIDENCE),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    all_integrated_refs = [
        ref_value
        for record in document["integrated_graph"]["subjects"]
        for ref_value in walk_full_refs(parse(record["input_json"]))
    ]
    external_ref_occurrences = sum(
        1 for ref_value in all_integrated_refs if render(ref_value) in EXTERNAL_BY_REF
    )
    product_ref_occurrences = len(all_integrated_refs) - external_ref_occurrences
    mutation_operation_counts: dict[str, int] = {}
    for mutation in document["schema_mutations"]:
        operation = mutation["operation"]
        mutation_operation_counts[operation] = mutation_operation_counts.get(operation, 0) + 1
    external_class_counts: dict[str, int] = {}
    for entry in EXTERNAL_MANIFEST["entries"]:
        class_code = entry["leaf_class"]
        external_class_counts[class_code] = external_class_counts.get(class_code, 0) + 1
    field_count = sum(len(definition["fields"]) for definition in MACHINE_SCHEMAS.values())
    rule_ids = sorted(
        {
            rule_id
            for definition in MACHINE_SCHEMAS.values()
            for rule_id in definition["rule_ids"]
        }
    )
    rule_layer_counts: dict[str, int] = {}
    for layer in RULE_LAYER.values():
        rule_layer_counts[layer] = rule_layer_counts.get(layer, 0) + 1
    report = {
        "report_schema": "core-1.1-conformance-report/1",
        "status": "PASS",
        "profile": STAGE_PROFILE,
        "pins": {
            "conformance_manifest_sha256": sha256_file(CONFORMANCE_PATH),
            "external_leaf_manifest_sha256": document["external_leaf_manifest"]["sha256"],
            "vectors_sha256": sha256_file(path),
        },
        "schema_coverage": {
            "product_schema_count": len(PRODUCT_SCHEMAS),
            "conformance_only_schema_count": len(CONFORMANCE_ONLY_SCHEMAS),
            "positive_schema_count": len({item["subject_schema"] for item in document["positive"]}),
            "field_rule_count": field_count,
            "cross_rule_count": len(rule_ids),
            "cross_rule_ids": rule_ids,
            "cross_rule_layer_counts": rule_layer_counts,
            "cross_rule_evidence_count": len(RULE_EVIDENCE),
            "cross_rule_evidence": {
                rule_id: {"assertion_id": evidence[0], "mutation_id": evidence[1]}
                for rule_id, evidence in sorted(RULE_EVIDENCE.items())
            },
            "schema_mutation_count": len(passed_mutations),
            "mutation_operation_counts": mutation_operation_counts,
            "accepted_invalid_count": 0,
        },
        "reference_coverage": {
            "full_ref_occurrences": len(all_integrated_refs),
            "checked_product_ref_occurrences": product_ref_occurrences,
            "pinned_external_ref_occurrences": external_ref_occurrences,
            "generic_artifact_auto_success_count": 0,
            "unresolved_critical_ref_count": 0,
            "external_entry_count": EXTERNAL_MANIFEST["entry_count"],
            "external_class_counts": external_class_counts,
        },
        "integrated_coverage": {
            "subject_count": document["integrated_subject_count"],
            "assertion_count": len(passed_assertions),
            "integrated_mutation_count": len(passed_graph_mutations),
            "integrated_mutation_categories": mutation_categories,
        },
        "logical_transaction_coverage": {
            "trace_count": len(passed_traces),
            "passed_trace_ids": passed_traces,
        },
        "toolchain": document["toolchain_provenance"],
    }
    if report_path is not None:
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"PASS {document['positive_count']} positive + {document['negative_count']} negative vectors; "
        f"{document['integrated_subject_count']} integrated subjects + {len(passed_assertions)} assertions; "
        f"{len(passed_mutations)} schema mutations + {len(passed_graph_mutations)} integrated mutations "
        f"across {len(mutation_categories)} categories; {len(passed_traces)} logical transaction traces"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
