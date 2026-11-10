#!/usr/bin/env python3
"""Author the machine-readable synthetic-trusted-flow/core@1.1 contract root.

This file is authoring tooling, not the runtime authority.  The checked-in JSON
output is the immutable review/freeze input and is consumed by the independent
verifier.  The specification is deliberately explicit about every accepted
subject field and compatibility identity; cross-object invariants are named by
rule id and implemented independently by the verifier.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


CONTRACT = "shared-product-contract/0.1"
PROFILE = "synthetic-trusted-flow/core@1.1"
ANNEX = "shared-contract-technical-profile/0.1.1"
CANONICAL = "canonical-json-v1.0"
GATES = [
    "BINDING_DATA_VALIDATION",
    "CONTROL_GOLDEN_EVALUATION",
    "DISCLOSURE_POLICY_CLEARANCE",
    "RUNTIME_CAPABILITY_COMPATIBILITY",
    "SEMANTIC_APPROVAL",
]

GENERIC_ACTIONS = [
    "ACTIVATE",
    "APPROVE_CLEARED_INPUT",
    "ATTEST",
    "EVIDENCE_READ",
    "PRE_QUERY",
    "PUBLISH",
    "RESOLVE",
    "RESULT_RELEASE",
    "REVOKE_VRS",
    "SCR_DISCLOSE",
    "SCR_ENQUEUE",
    "SCR_TRIAGE",
    "SEAL",
]

BASE_FIELD_NAMES = [
    "subject_schema",
    "contract_version",
    "canonicalization_profile",
    "object_type",
    "object_id",
    "object_version",
    "scope",
]


def scalar(kind: str, **constraints: Any) -> dict[str, Any]:
    return {"kind": kind, **constraints}


def ref(*targets: str, external_classes: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "full_ref", "targets": list(targets)}
    if external_classes:
        result["external_classes"] = external_classes
    return result


def nullable(item: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "nullable", "item": item}


def set_of(item: dict[str, Any], min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "set", "item": item, "min_items": min_items}
    if max_items is not None:
        result["max_items"] = max_items
    return result


def ordered(item: dict[str, Any], min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "ordered", "item": item, "min_items": min_items}
    if max_items is not None:
        result["max_items"] = max_items
    return result


def enum(*values: str) -> dict[str, Any]:
    return scalar("string", enum=list(values))


def external(*classes: str) -> dict[str, Any]:
    return ref(external_classes=list(classes))


def schema(
    object_type: str,
    scope_kind: str,
    fields: dict[str, dict[str, Any]],
    rules: list[str] | None = None,
    acceptance_class: str = "product",
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "scope_kind": scope_kind,
        "acceptance_class": acceptance_class,
        "fields": fields,
        "rule_ids": rules or [],
    }


ID = scalar("identifier")
VERSION = scalar("version")
TEXT = scalar("nonempty_string")
TIMESTAMP = scalar("timestamp")
DIGEST = scalar("digest")
NONNEG = scalar("integer", minimum=0)
POSITIVE = scalar("integer", minimum=1)
BOOL = scalar("boolean")
LIMITATION = enum(
    "constructed-target-coupled",
    "local-authority",
    "no-raw-question",
    "non-customer-validation",
    "public-style-synthetic",
    "synthetic-data",
    "synthetic-scope",
)
OBLIGATION = enum("ENFORCE_SCOPE", "NO_RAW_QUESTION", "REAUTHORIZE_REFS", "WRITE_AUDIT")
PURPOSE = enum("governed-analysis-demo", "ontology-build", "semantic-change-triage")


def build_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}

    schemas["cleared-input-proposal-subject/1"] = schema(
        "cleared-input-proposal",
        "governance",
        {
            "classification": enum("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"),
            "origin": enum("manual_transcription", "redacted_attachment", "in_zone_locator", "synthetic"),
            "allowed_uses": set_of(enum("ontology_build", "synthetic_demo"), 1),
            "safe_content_ref": external("INTEGRITY"),
            "opaque_source_locator_ref": scalar("opaque_locator"),
            "limitations": set_of(LIMITATION),
        },
        [],
    )
    schemas["cleared-input-subject/1"] = schema(
        "cleared-input",
        "governance",
        {
            "proposal_ref": ref("cleared-input-proposal-subject/1"),
            "input_disclosure_authority_decision_ref": ref("authority-decision-subject/1"),
        },
        ["cleared-input-authority"],
    )
    schemas["oracle-provenance-subject/1"] = schema(
        "oracle-provenance",
        "governance",
        {
            "reference_case_id": ID,
            "oracle_class": enum("CONSTRUCTED_SYNTHETIC"),
            "cleared_input_ref": ref("cleared-input-subject/1"),
            "source_ref": external("INTEGRITY"),
            "derivation_ref": external("INTEGRITY", "BUILD_SCHEMA"),
            "author_ref": external("PRINCIPAL"),
            "reviewer_ref": external("PRINCIPAL"),
            "limitations": set_of(LIMITATION, 1),
            "frozen_at": TIMESTAMP,
        },
        ["oracle-provenance"],
    )
    schemas["control-manifest-subject/1"] = schema(
        "control-manifest",
        "governance",
        {
            "reference_case_id": ID,
            "oracle_class": enum("CONSTRUCTED_SYNTHETIC"),
            "oracle_provenance_refs": set_of(ref("oracle-provenance-subject/1"), 1, 1),
            "formula_ref": external("INTEGRITY"),
            "period_profile_ref": external("INTEGRITY"),
            "population_profile_ref": external("INTEGRITY"),
            "unit_ref": external("INTEGRITY"),
            "rounding_profile_ref": external("INTEGRITY"),
            "expected_result_refs": ordered(external("INTEGRITY"), 1),
            "tolerance_profile_ref": external("INTEGRITY"),
            "expected_value_author_ref": external("PRINCIPAL"),
            "fixture_author_ref": external("PRINCIPAL"),
            "reviewer_ref": external("PRINCIPAL"),
            "truth_frozen_before_fixture": BOOL,
            "allowed_claims": set_of(enum("reviewed-constructed-synthetic-conformance"), 1, 1),
            "limitations": set_of(LIMITATION, 1),
            "frozen_at": TIMESTAMP,
        },
        ["control-manifest"],
    )
    schemas["suite-manifest-subject/1"] = schema(
        "suite-manifest",
        "governance",
        {
            "suite_id": enum("adt.tracer.v1.suite"),
            "cases": ordered(external("SUITE_CASE"), 8, 8),
            "denominator": POSITIVE,
            "status_counts": scalar(
                "closed_integer_map", keys=["ANSWERED", "CLARIFY", "REFUSED"], minimum=0
            ),
            "mutation_profile_ref": external("INTEGRITY"),
            "frozen_at": TIMESTAMP,
        },
        ["suite-denominator"],
    )
    schemas["reference-candidate-subject/1"] = schema(
        "reference-candidate",
        "governance",
        {
            "reference_case_id": ID,
            "cleared_input_ref": ref("cleared-input-subject/1"),
            "control_manifest_ref": ref("control-manifest-subject/1"),
            "suite_manifest_ref": ref("suite-manifest-subject/1"),
            "oracle_provenance_ref": ref("oracle-provenance-subject/1"),
            "verification_criteria_ref": external("INTEGRITY"),
            "limitations": set_of(LIMITATION, 1),
            "frozen_at": TIMESTAMP,
        },
        ["reference-candidate"],
    )
    schemas["reference-candidate-set-subject/1"] = schema(
        "reference-candidate-set",
        "governance",
        {
            "candidate_refs": set_of(ref("reference-candidate-subject/1"), 2, 2),
            "shared_suite_manifest_ref": ref("suite-manifest-subject/1"),
            "selection_policy_ref": external("STATIC_POLICY"),
            "denominator": POSITIVE,
            "frozen_at": TIMESTAMP,
        },
        ["reference-candidate-set"],
    )
    schemas["reference-reselection-transition-subject/1"] = schema(
        "reference-reselection-transition",
        "governance",
        {
            "predecessor_candidate_set_ref": ref("reference-candidate-set-subject/1"),
            "predecessor_reference_manifest_ref": ref("reference-manifest-subject/2"),
            "predecessor_commit_receipt_ref": ref("reference-selection-commit-receipt-subject/1"),
            "change_reason_code": enum(
                "MATERIAL_SEMANTIC_CHANGE",
                "ORACLE_CORRECTION",
                "POLICY_CHANGE",
                "SOURCE_CORRECTION",
            ),
            "changed_component_refs": set_of(
                ref(
                    "reference-candidate-subject/1",
                    "suite-manifest-subject/1",
                    external_classes=["STATIC_POLICY"],
                ),
                1,
            ),
            "evaluated_at": TIMESTAMP,
        },
        ["reference-reselection-transition"],
    )
    schemas["reference-selection-proposal-subject/1"] = schema(
        "reference-selection-proposal",
        "governance",
        {
            "candidate_set_ref": ref("reference-candidate-set-subject/1"),
            "selected_candidate_ref": ref("reference-candidate-subject/1"),
            "selected_reference_case_id": ID,
            "reselection_transition_ref": nullable(ref("reference-reselection-transition-subject/1")),
            "limitations": set_of(LIMITATION, 1),
        },
        ["reference-selection-proposal"],
    )

    authority_fields = {
        "action": scalar("string"),
        "trusted_session_ref": external("TRUSTED_SESSION"),
        "principal_ref": external("PRINCIPAL"),
        "principal_registry_ref": external("PRINCIPAL_REGISTRY"),
        "role_assignment_ref": external("ROLE_ASSIGNMENT"),
        "trust_epoch": NONNEG,
        "purpose": PURPOSE,
        "proposed_action_subject_ref": ref(
            "activation-intent-subject/1",
            "cleared-input-proposal-subject/1",
            "execution-evidence-subject/2",
            "gate-evaluation-subject/1",
            "gsr-publish-subject/2",
            "payload-disclosure-evaluation-subject/1",
            "revocation-intent-subject/1",
            "scr-enqueue-proposal-subject/1",
            "semantic-change-request-subject/1",
            "vrs-seal-proposal-subject/1",
            external_classes=["REQUEST"],
        ),
        "policy_refs": set_of(external("STATIC_POLICY"), 1),
        "obligations": set_of(OBLIGATION, 1),
        "decision": enum("ALLOW", "DENY"),
        "reason_codes": set_of(TEXT, 1),
        "issued_at": TIMESTAMP,
        "expires_at": TIMESTAMP,
    }
    schemas["authority-decision-subject/1"] = schema(
        "authority-decision",
        "dynamic",
        {**authority_fields, "action": enum(*GENERIC_ACTIONS)},
        ["generic-authority-decision"],
    )
    schemas["reference-selection-authority-decision-subject/1"] = schema(
        "reference-selection-authority-decision",
        "governance",
        {
            **authority_fields,
            "action": enum("SELECT_REFERENCE"),
            "purpose": enum("ontology-build"),
            "proposed_action_subject_ref": ref("reference-selection-proposal-subject/1"),
        },
        ["reference-selection-authority"],
    )
    schemas["reference-manifest-subject/2"] = schema(
        "reference-manifest",
        "governance",
        {
            "reference_case_id": ID,
            "cleared_input_ref": ref("cleared-input-subject/1"),
            "control_manifest_ref": ref("control-manifest-subject/1"),
            "suite_manifest_ref": ref("suite-manifest-subject/1"),
            "oracle_provenance_ref": ref("oracle-provenance-subject/1"),
            "frozen_at": TIMESTAMP,
            "selection_proposal_ref": ref("reference-selection-proposal-subject/1"),
            "selection_authority_decision_ref": ref("reference-selection-authority-decision-subject/1"),
        },
        ["reference-manifest-final"],
    )
    schemas["reference-selection-commit-receipt-subject/1"] = schema(
        "reference-selection-commit-receipt",
        "governance",
        {
            "selection_key_digest": DIGEST,
            "request_identity_digest": DIGEST,
            "candidate_set_ref": ref("reference-candidate-set-subject/1"),
            "selection_proposal_ref": ref("reference-selection-proposal-subject/1"),
            "selection_authority_decision_ref": ref("reference-selection-authority-decision-subject/1"),
            "reference_manifest_ref": ref("reference-manifest-subject/2"),
            "authority_trust_epoch": NONNEG,
            "authority_policy_snapshot_ref": external("STATIC_POLICY"),
            "predecessor_receipt_ref": nullable(ref("reference-selection-commit-receipt-subject/1")),
            "transition_ref": nullable(ref("reference-reselection-transition-subject/1")),
            "commit_sequence": POSITIVE,
            "committed_at": TIMESTAMP,
            "journal_record_digest": DIGEST,
            "commit_status": enum("COMMITTED"),
        },
        ["reference-selection-receipt"],
    )
    schemas["semantic-content-manifest-subject/1"] = schema(
        "semantic-content-manifest",
        "governance",
        {
            "reference_manifest_ref": ref("reference-manifest-subject/2"),
            "semantic_schema_ref": external("BUILD_SCHEMA"),
            "content_digest": DIGEST,
            "compiler_build_ref": external("BUILD_SCHEMA"),
            "limitations": set_of(LIMITATION, 1),
            "built_at": TIMESTAMP,
        },
        ["semantic-content-lineage"],
    )
    schemas["gsr-publish-subject/2"] = schema(
        "gsr-publish-subject",
        "governance",
        {
            "semantic_version": VERSION,
            "semantic_schema_ref": external("BUILD_SCHEMA"),
            "semantic_content_ref": ref("semantic-content-manifest-subject/1"),
            "selected_reference_manifest_ref": ref("reference-manifest-subject/2"),
            "selection_commit_receipt_ref": ref("reference-selection-commit-receipt-subject/1"),
            "cleared_input_refs": set_of(ref("cleared-input-subject/1"), 1, 1),
            "decision_refs": set_of(external("SEMANTIC_DECISION"), 1),
            "required_capability_refs": set_of(external("INTEGRITY"), 1),
            "binding_requirements_ref": external("INTEGRITY"),
            "policy_requirements_ref": external("STATIC_POLICY"),
            "disclosure_labels_ref": external("INTEGRITY"),
            "supersedes_ref": nullable(ref("governed-semantic-release-subject/1")),
        },
        ["gsr-selected-lineage"],
    )
    schemas["semantic-approval-subject/1"] = schema(
        "semantic-approval-subject",
        "governance",
        {
            "gsr_publish_subject_ref": ref("gsr-publish-subject/2"),
            "semantic_validation_profile_ref": external("BUILD_SCHEMA"),
        },
    )
    schemas["governed-semantic-release-subject/1"] = schema(
        "governed-semantic-release",
        "governance",
        {
            "publish_subject_ref": ref("gsr-publish-subject/2"),
            "semantic_approval_attempt_ref": ref("verification-attempt-subject/1"),
            "publish_authority_decision_ref": ref("authority-decision-subject/1"),
        },
        ["gsr-publish-authority"],
    )

    schemas["data-identity-subject/1"] = schema(
        "data-identity",
        "runtime",
        {
            "dataset_manifest_ref": external("INTEGRITY"),
            "schema_digest": DIGEST,
            "partition_identity_refs": set_of(external("INTEGRITY"), 1),
            "row_count": NONNEG,
            "source_engine_ref": external("BUILD_SCHEMA"),
            "transformation_ref": external("INTEGRITY", "BUILD_SCHEMA"),
            "policy_scope_ref": external("STATIC_POLICY"),
            "frozen_at": TIMESTAMP,
            "replay_level": enum("evidence_only"),
        },
    )
    schemas["runtime-snapshot-payload-subject/1"] = schema(
        "runtime-snapshot-payload",
        "runtime",
        {
            "gsr_ref": ref("governed-semantic-release-subject/1"),
            "runtime_semantic_projection_ref": external("INTEGRITY"),
            "binding_bundle_ref": external("INTEGRITY"),
            "projection_policy_bundle_ref": external("STATIC_POLICY"),
            "runtime_capability_manifest_ref": external("INTEGRITY"),
            "data_identity_ref": ref("data-identity-subject/1"),
            "control_manifest_ref": ref("control-manifest-subject/1"),
            "suite_manifest_ref": ref("suite-manifest-subject/1"),
            "reference_manifest_ref": ref("reference-manifest-subject/2"),
            "oracle_provenance_ref": ref("oracle-provenance-subject/1"),
            "evaluation_runner_manifest_ref": external("BUILD_SCHEMA"),
            "compatibility_profile_ref": external("BUILD_SCHEMA"),
            "projection_profile_ref": external("BUILD_SCHEMA"),
        },
        ["runtime-payload-selected-lineage"],
    )
    schemas["binding-data-validation-subject/1"] = schema(
        "binding-data-validation-subject",
        "runtime",
        {
            "gsr_binding_requirements_ref": external("INTEGRITY"),
            "runtime_semantic_projection_ref": external("INTEGRITY"),
            "binding_bundle_ref": external("INTEGRITY"),
            "data_identity_ref": ref("data-identity-subject/1"),
            "binding_validation_profile_ref": external("BUILD_SCHEMA"),
        },
    )
    schemas["disclosure-policy-subject/1"] = schema(
        "disclosure-policy-subject",
        "runtime",
        {
            "gsr_disclosure_labels_ref": external("INTEGRITY"),
            "gsr_policy_requirements_ref": external("STATIC_POLICY"),
            "runtime_semantic_projection_ref": external("INTEGRITY"),
            "runtime_projection_schema_ref": external("BUILD_SCHEMA"),
            "user_projection_schema_ref": external("BUILD_SCHEMA"),
            "projection_transformer_ref": external("BUILD_SCHEMA"),
            "projection_policy_bundle_ref": external("STATIC_POLICY"),
            "audience_purpose_profile_ref": external("INTEGRITY"),
            "projection_fidelity_report_ref": external("EVIDENCE"),
            "disclosure_validation_profile_ref": external("BUILD_SCHEMA"),
        },
    )
    schemas["runtime-capability-subject/1"] = schema(
        "runtime-capability-subject",
        "runtime",
        {
            "gsr_semantic_content_ref": ref("semantic-content-manifest-subject/1"),
            "gsr_capability_requirements_ref": external("INTEGRITY"),
            "runtime_semantic_projection_ref": external("INTEGRITY"),
            "runtime_capability_manifest_ref": external("INTEGRITY"),
            "provider_build_ref": external("BUILD_SCHEMA"),
            "input_schema_ref": external("BUILD_SCHEMA"),
            "output_schema_ref": external("BUILD_SCHEMA"),
            "failure_contract_ref": external("BUILD_SCHEMA"),
            "options_profile_ref": external("BUILD_SCHEMA"),
            "policy_obligations_ref": external("STATIC_POLICY"),
            "compatibility_profile_ref": external("BUILD_SCHEMA"),
            "projection_fidelity_report_ref": external("EVIDENCE"),
            "conformance_suite_ref": external("SUITE_CASE", "INTEGRITY"),
        },
    )
    schemas["control-golden-subject/1"] = schema(
        "control-golden-subject",
        "runtime",
        {
            "runtime_snapshot_payload_ref": ref("runtime-snapshot-payload-subject/1"),
            "control_manifest_ref": ref("control-manifest-subject/1"),
            "suite_manifest_ref": ref("suite-manifest-subject/1"),
            "reference_manifest_ref": ref("reference-manifest-subject/2"),
            "oracle_provenance_ref": ref("oracle-provenance-subject/1"),
            "evaluation_runner_manifest_ref": external("BUILD_SCHEMA"),
            "evaluation_profile_ref": external("BUILD_SCHEMA"),
        },
        ["control-gate-selected-lineage"],
    )
    schemas["gate-evaluation-subject/1"] = schema(
        "gate-evaluation",
        "dynamic",
        {
            "gate_type": enum(*GATES),
            "gate_subject_ref": ref(
                "binding-data-validation-subject/1",
                "control-golden-subject/1",
                "disclosure-policy-subject/1",
                "runtime-capability-subject/1",
                "semantic-approval-subject/1",
            ),
            "outcome": enum("PASS", "FAIL"),
            "evidence_refs": set_of(external("EVIDENCE"), 1),
            "limitations": set_of(LIMITATION),
            "validity_mode": enum("UNTIL"),
            "issued_at": TIMESTAMP,
            "expires_at": nullable(TIMESTAMP),
        },
        ["gate-evaluation"],
    )
    schemas["verification-attempt-subject/1"] = schema(
        "verification-attempt",
        "dynamic",
        {
            "gate_evaluation_ref": ref("gate-evaluation-subject/1"),
            "authority_decision_ref": ref("authority-decision-subject/1"),
        },
        ["verification-attempt"],
    )
    schemas["vrs-seal-proposal-subject/1"] = schema(
        "vrs-seal-proposal",
        "runtime",
        {
            "runtime_snapshot_payload_ref": ref("runtime-snapshot-payload-subject/1"),
            "verification_attempt_refs_by_gate": scalar(
                "closed_ref_map", keys=GATES, targets=["verification-attempt-subject/1"]
            ),
        },
        ["seal-proposal"],
    )
    schemas["verified-runtime-snapshot-subject/1"] = schema(
        "verified-runtime-snapshot",
        "runtime",
        {
            "seal_proposal_ref": ref("vrs-seal-proposal-subject/1"),
            "seal_authority_decision_ref": ref("authority-decision-subject/1"),
            "seal_status": enum("SEALED"),
            "limitations": set_of(LIMITATION),
        },
        ["verified-runtime-snapshot"],
    )

    schemas["policy-decision-subject/1"] = schema(
        "policy-decision",
        "channel",
        {
            "principal_context_ref": external("PRINCIPAL_CONTEXT"),
            "purpose": PURPOSE,
            "resource_refs": set_of(
                ref("execution-evidence-subject/2", "verified-runtime-snapshot-subject/1"), 1
            ),
            "policy_refs": set_of(external("STATIC_POLICY"), 1),
            "input_context_digest": DIGEST,
            "decision": enum("ALLOW", "DENY"),
            "reason_codes": set_of(TEXT, 1),
            "obligations": set_of(OBLIGATION, 1),
            "evaluated_at": TIMESTAMP,
            "valid_until": TIMESTAMP,
        },
        ["policy-decision"],
    )
    schemas["activation-intent-subject/1"] = schema(
        "activation-intent",
        "channel",
        {
            "action": enum("ACTIVATE"),
            "vrs_ref": ref("verified-runtime-snapshot-subject/1"),
            "expected_head_ref": nullable(ref("activation-record-subject/1")),
            "expected_activation_epoch": NONNEG,
            "idempotency_key": scalar("opaque_token"),
            "reason_code": enum("INITIAL"),
            "requested_at": TIMESTAMP,
        },
    )
    schemas["activation-record-subject/1"] = schema(
        "activation-record",
        "channel",
        {
            "intent_ref": ref("activation-intent-subject/1"),
            "eligibility_decision_ref": ref("execution-eligibility-subject/1"),
            "authority_decision_ref": ref("authority-decision-subject/1"),
            "sequence": POSITIVE,
            "previous_record_ref": nullable(ref("activation-record-subject/1")),
            "activation_epoch": POSITIVE,
            "committed_at": TIMESTAMP,
        },
    )
    schemas["revocation-intent-subject/1"] = schema(
        "revocation-intent",
        "channel",
        {
            "target_ref": ref("verified-runtime-snapshot-subject/1"),
            "enforcement": enum("BLOCK_NEW_AND_RESULT_RELEASE"),
            "expected_head_ref": nullable(ref("revocation-record-subject/1")),
            "expected_revocation_epoch": NONNEG,
            "idempotency_key": scalar("opaque_token"),
            "reason_code": enum("INTEGRITY"),
            "requested_at": TIMESTAMP,
        },
    )
    schemas["revocation-record-subject/1"] = schema(
        "revocation-record",
        "channel",
        {
            "intent_ref": ref("revocation-intent-subject/1"),
            "authority_decision_ref": ref("authority-decision-subject/1"),
            "sequence": POSITIVE,
            "previous_record_ref": nullable(ref("revocation-record-subject/1")),
            "new_revocation_epoch": POSITIVE,
            "committed_at": TIMESTAMP,
        },
    )
    schemas["execution-eligibility-subject/1"] = schema(
        "execution-eligibility-decision",
        "channel",
        {
            "phase": enum("ACTIVATE", "EVIDENCE_READ", "PRE_QUERY", "RESULT_RELEASE"),
            "purpose": enum("governed-analysis-demo"),
            "vrs_ref": ref("verified-runtime-snapshot-subject/1"),
            "runtime_snapshot_payload_ref": ref("runtime-snapshot-payload-subject/1"),
            "verification_attempt_refs_by_gate": scalar(
                "closed_ref_map", keys=GATES, targets=["verification-attempt-subject/1"]
            ),
            "activation_head_ref": nullable(ref("activation-record-subject/1")),
            "request_authority_decision_ref": ref("authority-decision-subject/1"),
            "policy_decision_ref": ref("policy-decision-subject/1"),
            "revocation_scope_epoch": NONNEG,
            "observed_revocation_set_digest": DIGEST,
            "evaluated_at": TIMESTAMP,
            "valid_until": TIMESTAMP,
            "decision": enum("ALLOW", "DENY"),
            "reason_codes": set_of(TEXT, 1),
        },
        ["execution-eligibility"],
    )
    schemas["user-projection-subject/1"] = schema(
        "user-evidence-projection",
        "channel",
        {
            "execution_id": ID,
            "projection_schema_ref": external("BUILD_SCHEMA"),
            "content_bytes_digest": DIGEST,
            "renderer_ref": external("BUILD_SCHEMA"),
            "locale": enum("en-HK"),
            "timezone": enum("Asia/Hong_Kong"),
            "unit_profile_ref": external("INTEGRITY"),
            "rounding_profile_ref": external("INTEGRITY"),
            "classification_ref": external("INTEGRITY"),
        },
        ["user-projection"],
    )
    schemas["concept-resolution-evidence-subject/1"] = schema(
        "concept-resolution-evidence",
        "channel",
        {
            "execution_id": ID,
            "safe_term_alias_ref": external("SAFE_HANDLE"),
            "semantic_area_code": enum("MARKET_METRICS"),
            "term_well_formed": BOOL,
            "semantic_area_status": enum("KNOWN"),
            "semantic_registry_ref": external("INTEGRITY"),
            "alias_resolution_profile_ref": external("BUILD_SCHEMA"),
            "resolver_build_ref": external("BUILD_SCHEMA"),
            "resolution_completed": BOOL,
            "binding_count": NONNEG,
            "authorization_classification": enum("ELIGIBLE"),
            "pre_query_eligibility_ref": ref("execution-eligibility-subject/1"),
            "policy_decision_ref": ref("policy-decision-subject/1"),
            "query_engine_access_count": NONNEG,
            "evaluated_at": TIMESTAMP,
        },
        ["concept-resolution-evidence"],
    )
    schemas["execution-evidence-subject/2"] = schema(
        "execution-evidence-envelope",
        "channel",
        {
            "execution_id": ID,
            "principal_context_ref": external("PRINCIPAL_CONTEXT"),
            "purpose": enum("governed-analysis-demo"),
            "gsr_ref": ref("governed-semantic-release-subject/1"),
            "vrs_ref": ref("verified-runtime-snapshot-subject/1"),
            "activation_record_ref": ref("activation-record-subject/1"),
            "pre_query_eligibility_ref": ref("execution-eligibility-subject/1"),
            "policy_decision_ref": ref("policy-decision-subject/1"),
            "data_identity_ref": ref("data-identity-subject/1"),
            "plan_ref": nullable(external("EVIDENCE")),
            "query_ref": nullable(external("EVIDENCE")),
            "operator_refs": set_of(external("BUILD_SCHEMA")),
            "facts_ref": nullable(external("EVIDENCE")),
            "claims_ref": nullable(external("EVIDENCE")),
            "user_projection_ref": nullable(ref("user-projection-subject/1")),
            "concept_resolution_evidence_ref": nullable(ref("concept-resolution-evidence-subject/1")),
            "candidate_status": enum(
                "ANSWER_CANDIDATE", "CLARIFY", "FAILED_EXECUTION", "FAILED_PRECONDITION", "REFUSED"
            ),
            "boundary_code": nullable(
                enum(
                    "CONCEPT_NOT_BOUND",
                    "MISSING_PERIOD",
                    "PARTIAL_RESULT",
                    "RAW_DETAIL_DENIED",
                    "ROLE_DENIED",
                    "SNAPSHOT_NOT_ACTIVE",
                    "UNSUPPORTED_PREDICTION",
                )
            ),
            "query_engine_access_count": NONNEG,
            "started_at": TIMESTAMP,
            "completed_at": TIMESTAMP,
            "replay_level": enum("evidence_only"),
        },
        ["execution-evidence-boundary", "execution-evidence-concept"],
    )
    schemas["result-release-commit-subject/1"] = schema(
        "result-release-commit",
        "channel",
        {
            "execution_evidence_ref": ref("execution-evidence-subject/2"),
            "user_projection_ref": ref("user-projection-subject/1"),
            "result_release_eligibility_ref": ref("execution-eligibility-subject/1"),
            "activation_head_ref": ref("activation-record-subject/1"),
            "vrs_ref": ref("verified-runtime-snapshot-subject/1"),
            "policy_decision_ref": ref("policy-decision-subject/1"),
            "revocation_scope_epoch": NONNEG,
            "commit_sequence": POSITIVE,
            "committed_at": TIMESTAMP,
        },
        ["result-release-commit"],
    )
    schemas["unknown-concept-payload-subject/2"] = schema(
        "proposed-scr-payload",
        "governance",
        {
            "request_type": enum("UNKNOWN_CONCEPT"),
            "safe_term_alias_ref": external("SAFE_HANDLE"),
            "semantic_area_code": enum("MARKET_METRICS"),
            "reason_code": enum("CONCEPT_NOT_BOUND"),
            "safe_context_codes": set_of(enum("METRIC_TERM"), 1, 1),
            "safe_detail_artifact_ref": external("SAFE_HANDLE"),
            "interaction_handle_ref": external("SAFE_HANDLE"),
            "observed_gsr_ref": ref("governed-semantic-release-subject/1"),
            "observed_vrs_ref": ref("verified-runtime-snapshot-subject/1"),
            "boundary_execution_ref": ref("execution-evidence-subject/2"),
            "boundary_release_commit_ref": ref("result-release-commit-subject/1"),
            "requested_action_code": enum("ADD_ALIAS", "CLARIFY_DEFINITION", "REVIEW"),
        },
        ["unknown-concept-payload"],
    )
    schemas["payload-disclosure-evaluation-subject/1"] = schema(
        "payload-disclosure-evaluation",
        "governance",
        {
            "proposed_payload_ref": ref("unknown-concept-payload-subject/2"),
            "safe_detail_artifact_ref": external("SAFE_HANDLE"),
            "source_scope": scalar("scope", allowed_kinds=["channel"]),
            "destination_scope": scalar("scope", allowed_kinds=["governance"]),
            "requester_principal_ref": external("PRINCIPAL"),
            "receiving_audience_ref": external("INTEGRITY"),
            "purpose": enum("semantic-change-triage"),
            "classification": enum("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"),
            "allowed_fields": set_of(
                enum("reason_code", "safe_detail_artifact_ref", "safe_term_alias_ref", "semantic_area_code"), 1
            ),
            "policy_refs": set_of(external("STATIC_POLICY"), 1),
            "obligations": set_of(OBLIGATION, 1),
            "decision": enum("ALLOW", "DENY"),
            "reason_codes": set_of(TEXT, 1),
            "issued_at": TIMESTAMP,
            "expires_at": TIMESTAMP,
        },
        ["payload-disclosure-evaluation"],
    )
    schemas["payload-disclosure-decision-subject/1"] = schema(
        "payload-disclosure-decision",
        "governance",
        {
            "evaluation_ref": ref("payload-disclosure-evaluation-subject/1"),
            "disclosure_authority_decision_ref": ref("authority-decision-subject/1"),
        },
        ["payload-disclosure-decision"],
    )
    schemas["scr-enqueue-proposal-subject/1"] = schema(
        "scr-enqueue-proposal",
        "governance",
        {
            "proposed_payload_ref": ref("unknown-concept-payload-subject/2"),
            "payload_disclosure_decision_ref": ref("payload-disclosure-decision-subject/1"),
            "idempotency_key": scalar("opaque_token"),
            "requested_at": TIMESTAMP,
            "limitations": set_of(LIMITATION),
        },
        ["scr-enqueue-proposal"],
    )
    schemas["semantic-change-request-subject/1"] = schema(
        "semantic-change-request",
        "governance",
        {
            "enqueue_proposal_ref": ref("scr-enqueue-proposal-subject/1"),
            "requester_authority_decision_ref": ref("authority-decision-subject/1"),
        },
        ["semantic-change-request"],
    )
    schemas["canonical-test-subject/1"] = schema(
        "canonical-test",
        "governance",
        {
            "chinese_nfc": TEXT,
            "escaped": TEXT,
            "decimal_value": scalar("decimal_value"),
            "nullable": nullable(TEXT),
            "ordered_values": ordered(TEXT),
            "enabled": BOOL,
        },
        acceptance_class="conformance_only",
    )
    return schemas


def with_base(schema_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    base = {
        "subject_schema": scalar("fixed", value=schema_id),
        "contract_version": scalar("fixed", value=CONTRACT),
        "canonicalization_profile": scalar("fixed", value=CANONICAL),
        "object_type": scalar("fixed", value=definition["object_type"]),
        "object_id": ID,
        "object_version": VERSION,
        "scope": scalar(
            "scope",
            allowed_kinds=[definition["scope_kind"]]
            if definition["scope_kind"] != "dynamic"
            else ["governance", "runtime", "channel"],
        ),
    }
    return {**definition, "fields": {**base, **definition["fields"]}}


def build_manifest() -> dict[str, Any]:
    schemas = {key: with_base(key, value) for key, value in build_schemas().items()}
    compatibility = {
        value["object_type"]: key
        for key, value in schemas.items()
        if value["acceptance_class"] == "product"
    }
    conformance_only = sorted(
        key for key, value in schemas.items() if value["acceptance_class"] == "conformance_only"
    )
    return {
        "manifest_schema": "core-profile-conformance-manifest/1",
        "contract_version": CONTRACT,
        "stage_profile_id": PROFILE,
        "annex_profile_id": ANNEX,
        "canonicalization_profile": CANONICAL,
        "external_leaf_manifest_schema": "external-leaf-manifest/1",
        "primitive_contract": {
            "identifier_pattern": r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$",
            "version_pattern": r"^[0-9]+(?:\.[0-9]+){0,2}(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?$",
            "reserved_versions": ["*", "current", "latest"],
            "digest_pattern": r"^sha-256:[0-9a-f]{64}$",
            "timestamp_pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$",
            "opaque_token_pattern": r"^opaque-[a-z0-9-]{9,121}$",
            "decimal_coefficient_pattern": r"^(?:0|-?[1-9][0-9]*)$",
            "safe_integer_min": -9_007_199_254_740_991,
            "safe_integer_max": 9_007_199_254_740_991,
        },
        "schema_contract": {"base_fields": BASE_FIELD_NAMES, "schemas": schemas},
        "profile_contract": {
            "five_gates": GATES,
            "generic_authority_actions": GENERIC_ACTIONS,
            "selection_authority_action": "SELECT_REFERENCE",
            "authority_action_contract": {
                "ACTIVATE": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_schemas": ["activation-intent-subject/1"]},
                "APPROVE_CLEARED_INPUT": {"purposes": ["ontology-build"], "scope_kind": "governance", "target_schemas": ["cleared-input-proposal-subject/1"]},
                "ATTEST": {"purposes": ["governed-analysis-demo"], "scope_kind": "same_as_resource", "target_schemas": ["gate-evaluation-subject/1"]},
                "EVIDENCE_READ": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_schemas": ["execution-evidence-subject/2"]},
                "PRE_QUERY": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_external_classes": ["REQUEST"]},
                "PUBLISH": {"purposes": ["governed-analysis-demo"], "scope_kind": "governance", "target_schemas": ["gsr-publish-subject/2"]},
                "RESOLVE": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_external_classes": ["REQUEST"]},
                "RESULT_RELEASE": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_schemas": ["execution-evidence-subject/2"]},
                "REVOKE_VRS": {"purposes": ["governed-analysis-demo"], "scope_kind": "channel", "target_schemas": ["revocation-intent-subject/1"]},
                "SCR_DISCLOSE": {"purposes": ["semantic-change-triage"], "scope_kind": "governance", "target_schemas": ["payload-disclosure-evaluation-subject/1"]},
                "SCR_ENQUEUE": {"purposes": ["semantic-change-triage"], "scope_kind": "governance", "target_schemas": ["scr-enqueue-proposal-subject/1"]},
                "SCR_TRIAGE": {"purposes": ["semantic-change-triage"], "scope_kind": "governance", "target_schemas": ["semantic-change-request-subject/1"]},
                "SEAL": {"purposes": ["governed-analysis-demo"], "scope_kind": "runtime", "target_schemas": ["vrs-seal-proposal-subject/1"]},
            },
            "semantic_decision_profile": "recorded-semantic-decision",
            "analytic_outcomes": [
                "ANSWERED",
                "CLARIFY",
                "FAILED_EXECUTION",
                "FAILED_PRECONDITION",
                "REFUSED",
            ],
            "suite": {
                "suite_id": "adt.tracer.v1.suite",
                "denominator": 8,
                "status_counts": {"ANSWERED": 4, "CLARIFY": 1, "REFUSED": 3},
            },
            "fixed_scope": {
                "tenant_id": "local-synthetic",
                "workspace_id": "adt-poc",
                "environment_id": "synthetic-reference",
                "channel": "active",
            },
            "claim_ceiling": [
                "constructed-synthetic",
                "non-customer-validation",
                "non-production",
                "simulated-local-authority",
            ],
        },
        "compatibility": {
            "accepted_schema_by_object_type": compatibility,
            "conformance_only_schemas": conformance_only,
            "predecessor_only_rejected": {
                "execution-evidence-envelope": "execution-evidence-subject/1",
                "gsr-publish-subject": "gsr-publish-subject/1",
                "proposed-scr-payload": "unknown-concept-payload-subject/1",
                "reference-manifest": "reference-manifest-subject/1",
            },
            "migration_rule": "FRESH_SUBJECTS_ONLY_NO_RELABEL_NO_MIX",
            "unknown_profile_behavior": "FAIL_CLOSED",
        },
        "required_coverage": {
            "every_product_schema_has_positive": True,
            "every_conformance_schema_has_positive": True,
            "every_field_has_remove_and_wrong_type_mutation": True,
            "every_ref_field_has_target_or_external_resolution_mutation": True,
            "every_enum_has_unknown_value_mutation": True,
            "every_cross_rule_has_semantic_mutation": True,
            "critical_unresolved_ref_count": 0,
            "accepted_invalid_count": 0,
        },
        "conformance_contract": {
            "fixture_evaluation_time": "2026-08-19T00:04:00.000Z",
            "logical_failure_symbol": "JOURNAL_CORRUPT_OR_NOT_DURABLE",
        },
    }


def main() -> None:
    rendered = json.dumps(build_manifest(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) == 3 and sys.argv[1] == "--output":
        Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: build_conformance_manifest_core_1_1.py [--output PATH]")
    print(rendered, end="")


if __name__ == "__main__":
    main()
