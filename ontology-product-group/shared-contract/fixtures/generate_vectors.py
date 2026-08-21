#!/usr/bin/env python3
"""Generate frozen Shared Product Contract canonicalization vectors to stdout.

This is the fixture-generation path. The independent verifier intentionally does
not import this module. Expected values are checked into JSON and never generated
by the implementation under test during conformance tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


PROFILE = "canonical-json-v1.0"
CONTRACT = "shared-product-contract/0.1"
SAFE_INT = 9_007_199_254_740_991
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
SUBJECT_SCHEMA_BY_OBJECT_TYPE = {
    "gsr-publish-subject": "gsr-publish-subject/1",
    "semantic-approval-subject": "semantic-approval-subject/1",
    "binding-data-validation-subject": "binding-data-validation-subject/1",
    "disclosure-policy-subject": "disclosure-policy-subject/1",
    "runtime-capability-subject": "runtime-capability-subject/1",
    "control-golden-subject": "control-golden-subject/1",
    "execution-eligibility-decision": "execution-eligibility-subject/1",
    "user-evidence-projection": "user-projection-subject/1",
    "execution-evidence-envelope": "execution-evidence-subject/1",
    "proposed-scr-payload": "unknown-concept-payload-subject/1",
}


def _string(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("NON_NFC")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("UNPAIRED_SURROGATE")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if not -SAFE_INT <= value <= SAFE_INT:
            raise ValueError("INTEGER_OUT_OF_RANGE")
        return str(value)
    if isinstance(value, float):
        raise ValueError("FLOAT_FORBIDDEN")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = list(value)
        if any(not isinstance(key, str) for key in keys):
            raise ValueError("NON_STRING_KEY")
        if any(unicodedata.normalize("NFC", key) != key for key in keys):
            raise ValueError("NON_NFC_KEY")
        return "{" + ",".join(
            _string(key) + ":" + canonical(value[key]) for key in sorted(keys)
        ) + "}"
    raise ValueError("UNSUPPORTED_TYPE")


def digest(schema: str, canonical_json: str) -> tuple[str, str]:
    preimage = (
        b"spc-v0.1\x00"
        + PROFILE.encode()
        + b"\x00"
        + schema.encode()
        + b"\x00"
        + canonical_json.encode("utf-8")
    )
    return preimage.hex(), "sha-256:" + hashlib.sha256(preimage).hexdigest()


def scope(kind: str = "governance") -> dict[str, str]:
    result = {"tenant_id": "local-synthetic", "workspace_id": "adt-poc"}
    if kind in {"runtime", "channel"}:
        result["environment_id"] = "synthetic-reference"
    if kind == "channel":
        result["channel"] = "active"
    return result


def base(schema: str, object_type: str, object_id: str, version: str, kind: str) -> dict[str, Any]:
    return {
        "subject_schema": schema,
        "contract_version": CONTRACT,
        "canonicalization_profile": PROFILE,
        "object_type": object_type,
        "object_id": object_id,
        "object_version": version,
        "scope": scope(kind),
    }


def fake_digest(label: str) -> str:
    return "sha-256:" + hashlib.sha256(label.encode()).hexdigest()


def ref(label: str, kind: str = "governance", object_type: str = "artifact") -> dict[str, Any]:
    return {
        "object_type": object_type,
        "object_id": label,
        "object_version": "1.0.0",
        "contract_version": CONTRACT,
        "subject_schema": SUBJECT_SCHEMA_BY_OBJECT_TYPE.get(object_type, f"{object_type}-subject/1"),
        "canonicalization_profile": PROFILE,
        "scope": scope(kind),
        "subject_digest": fake_digest(label),
    }


def sorted_set(items: list[Any]) -> list[Any]:
    return sorted(items, key=lambda item: canonical(item).encode("utf-8"))


def positive_subjects() -> list[tuple[str, dict[str, Any]]]:
    g = "governance"
    r = "runtime"
    c = "channel"
    objects: list[tuple[str, dict[str, Any]]] = []

    s = base("cleared-input-proposal-subject/1", "cleared-input-proposal", "input.adt.reference.proposal", "1.0.0", g)
    s.update(classification="PUBLIC", origin="manual_transcription", allowed_uses=["ontology_build", "synthetic_demo"], safe_content_ref=ref("safe-content.adt"), opaque_source_locator_ref=ref("opaque-source.001"), limitations=["non-hkex-validation"])
    objects.append(("P01a-cleared-input-proposal", s))

    s = base("cleared-input-subject/1", "cleared-input", "input.adt.reference", "1.0.0", g)
    s.update(proposal_ref=ref("input.adt.reference.proposal", g, "cleared-input-proposal"), input_disclosure_authority_decision_ref=ref("authority.input-disclosure.001", g, "authority-decision"))
    objects.append(("P01b-cleared-input", s))

    s = base("gsr-publish-subject/1", "gsr-publish-subject", "ontology.exchange-analytics.adt.publish", "1.0.0", g)
    s.update(semantic_version="1.0.0", semantic_schema_ref=ref("semantic-schema.adt"), semantic_content_ref=ref("semantic-content.adt"), cleared_input_refs=[ref("input.adt.reference", object_type="cleared-input")], decision_refs=sorted_set([ref("decision.adt.scope"), ref("decision.adt.rounding")]), required_capability_refs=sorted_set([ref("capability.exact-period-compare"), ref("capability.metric-resolve")]), binding_requirements_ref=ref("binding-requirements.adt"), policy_requirements_ref=ref("policy-requirements.adt"), disclosure_labels_ref=ref("disclosure-labels.adt"), supersedes_ref=None)
    objects.append(("P02-gsr-publish", s))

    s = base("governed-semantic-release-subject/1", "governed-semantic-release", "ontology.exchange-analytics.adt", "1.0.0", g)
    s.update(publish_subject_ref=ref("ontology.exchange-analytics.adt.publish", object_type="gsr-publish-subject"), semantic_approval_attempt_ref=ref("attempt.semantic.001", object_type="verification-attempt"), publish_authority_decision_ref=ref("authority.publish.001", object_type="authority-decision"))
    objects.append(("P03-gsr", s))

    s = base("runtime-snapshot-payload-subject/1", "runtime-snapshot-payload", "payload.adt.synthetic", "1.0.0", r)
    s.update(gsr_ref=ref("ontology.exchange-analytics.adt", object_type="governed-semantic-release"), runtime_semantic_projection_ref=ref("runtime-semantic.adt", r), binding_bundle_ref=ref("binding.adt.synthetic", r), projection_policy_bundle_ref=ref("projection-policy.adt", r), runtime_capability_manifest_ref=ref("runtime-capabilities.adt", r), data_identity_ref=ref("dataset.adt.synthetic", r, "data-identity"), control_manifest_ref=ref("control.adt", g, "control-manifest"), suite_manifest_ref=ref("adt.tracer.v1.suite", g, "suite-manifest"), reference_manifest_ref=ref("reference.adt", g, "reference-manifest"), oracle_provenance_ref=ref("oracle.adt", g), evaluation_runner_manifest_ref=ref("runner.adt", r), compatibility_profile_ref=ref("compatibility.exact", r), projection_profile_ref=ref("projection.adt", r))
    objects.append(("P04-runtime-payload", s))

    s = base("data-identity-subject/1", "data-identity", "dataset.adt.synthetic", "1.0.0", r)
    s.update(dataset_manifest_ref=ref("dataset-manifest.adt", r), schema_digest=fake_digest("dataset-schema"), partition_identity_refs=sorted_set([ref("partition.q3", r), ref("partition.q4", r)]), row_count=126, source_engine_ref=ref("engine.duckdb", r), transformation_ref=ref("transform.synthetic.adt", r), policy_scope_ref=ref("data-policy.synthetic", r), frozen_at="2026-08-18T00:00:00.000Z", replay_level="evidence_only")
    objects.append(("P05-data-identity", s))

    s = base("reference-manifest-subject/1", "reference-manifest", "reference.adt", "1.0.0", g)
    s.update(reference_case_id="adt.synthetic.v1", cleared_input_ref=ref("input.adt.reference", object_type="cleared-input"), control_manifest_ref=ref("control.adt", g, "control-manifest"), suite_manifest_ref=ref("adt.tracer.v1.suite", g, "suite-manifest"), oracle_provenance_ref=ref("oracle.adt"), frozen_at="2026-08-18T00:00:00.000Z")
    objects.append(("P06-reference-manifest", s))

    s = base("control-manifest-subject/1", "control-manifest", "control.adt", "1.0.0", g)
    s.update(reference_case_id="adt.synthetic.v1", oracle_class="CONSTRUCTED_SYNTHETIC", oracle_provenance_refs=[ref("oracle.adt")], formula_ref=ref("formula.adt"), period_profile_ref=ref("period.quarter"), population_profile_ref=ref("population.trades"), unit_ref=ref("unit.hkd-million"), rounding_profile_ref=ref("rounding.scale6"), expected_result_refs=[ref("expected.q3"), ref("expected.q4")], tolerance_profile_ref=ref("tolerance.exact-scale6"), expected_value_author_ref=ref("principal.truth-owner"), fixture_author_ref=ref("principal.truth-owner"), reviewer_ref=ref("principal.control-reviewer"), truth_frozen_before_fixture=True, allowed_claims=["reviewed-constructed-synthetic-conformance"], limitations=["constructed-target-coupled", "non-hkex-validation"], frozen_at="2026-08-18T00:00:00.000Z")
    objects.append(("P07-control-manifest", s))

    s = base("suite-manifest-subject/1", "suite-manifest", "adt.tracer.v1.suite", "1.0.0", g)
    cases = [ref(f"case.{index:02d}") for index in range(1, 9)]
    s.update(suite_id="adt.tracer.v1.suite", cases=cases, denominator=8, status_counts={"ANSWERED": 4, "CLARIFY": 1, "REFUSED": 3}, mutation_profile_ref=ref("mutation.adt.core"), frozen_at="2026-08-18T00:00:00.000Z")
    objects.append(("P08-suite-manifest", s))

    gate_definitions = [
        ("P09-semantic-gate", "semantic-approval-subject/1", "semantic-approval-subject", g, {"gsr_publish_subject_ref": ref("ontology.exchange-analytics.adt.publish", object_type="gsr-publish-subject"), "semantic_validation_profile_ref": ref("semantic-validation.adt")}),
        ("P10-binding-gate", "binding-data-validation-subject/1", "binding-data-validation-subject", r, {"gsr_binding_requirements_ref": ref("binding-requirements.adt"), "runtime_semantic_projection_ref": ref("runtime-semantic.adt", r), "binding_bundle_ref": ref("binding.adt.synthetic", r), "data_identity_ref": ref("dataset.adt.synthetic", r, "data-identity"), "binding_validation_profile_ref": ref("binding-validation.adt", r)}),
        ("P11-disclosure-gate", "disclosure-policy-subject/1", "disclosure-policy-subject", r, {"gsr_disclosure_labels_ref": ref("disclosure-labels.adt"), "gsr_policy_requirements_ref": ref("policy-requirements.adt"), "runtime_semantic_projection_ref": ref("runtime-semantic.adt", r), "runtime_projection_schema_ref": ref("runtime-projection-schema.adt", r), "user_projection_schema_ref": ref("user-projection-schema.adt", r), "projection_transformer_ref": ref("projection-transformer.adt", r), "projection_policy_bundle_ref": ref("projection-policy.adt", r), "audience_purpose_profile_ref": ref("audience.demo-analyst", r), "projection_fidelity_report_ref": ref("projection-fidelity.adt", r), "disclosure_validation_profile_ref": ref("disclosure-validation.adt", r)}),
        ("P12-runtime-gate", "runtime-capability-subject/1", "runtime-capability-subject", r, {"gsr_semantic_content_ref": ref("semantic-content.adt"), "gsr_capability_requirements_ref": ref("capability-requirements.adt"), "runtime_semantic_projection_ref": ref("runtime-semantic.adt", r), "runtime_capability_manifest_ref": ref("runtime-capabilities.adt", r), "provider_build_ref": ref("runtime-build.adt", r), "input_schema_ref": ref("operator-input.adt", r), "output_schema_ref": ref("operator-output.adt", r), "failure_contract_ref": ref("failure-contract.adt", r), "options_profile_ref": ref("options.adt", r), "policy_obligations_ref": ref("operator-policy.adt", r), "compatibility_profile_ref": ref("compatibility.exact", r), "projection_fidelity_report_ref": ref("projection-fidelity.adt", r), "conformance_suite_ref": ref("operator-conformance.adt", r)}),
        ("P13-control-gate", "control-golden-subject/1", "control-golden-subject", r, {"runtime_snapshot_payload_ref": ref("payload.adt.synthetic", r, "runtime-snapshot-payload"), "control_manifest_ref": ref("control.adt", g, "control-manifest"), "suite_manifest_ref": ref("adt.tracer.v1.suite", g, "suite-manifest"), "reference_manifest_ref": ref("reference.adt", g, "reference-manifest"), "oracle_provenance_ref": ref("oracle.adt"), "evaluation_runner_manifest_ref": ref("runner.adt", r), "evaluation_profile_ref": ref("evaluation.adt", r)}),
    ]
    for vector_id, schema, object_type, kind, fields in gate_definitions:
        s = base(schema, object_type, object_type.replace("-subject", ".adt"), "1.0.0", kind)
        s.update(fields)
        objects.append((vector_id, s))

    s = base("gate-evaluation-subject/1", "gate-evaluation", "evaluation.semantic.001", "1.0.0", g)
    s.update(gate_type="SEMANTIC_APPROVAL", gate_subject_ref=ref("semantic-approval.adt", g, "semantic-approval-subject"), outcome="PASS", evidence_refs=[ref("evidence.semantic.001")], limitations=["local-authority", "synthetic-data"], validity_mode="UNTIL", issued_at="2026-08-18T00:00:00.000Z", expires_at="2026-09-17T00:00:00.000Z")
    objects.append(("P14-gate-evaluation", s))

    s = base("authority-decision-subject/1", "authority-decision", "authority.publish.001", "1.0.0", g)
    s.update(action="PUBLISH", trusted_session_ref=ref("session.release-manager"), principal_ref=ref("principal.release-manager"), principal_registry_ref=ref("principal-registry.local"), role_assignment_ref=ref("role.release-manager"), trust_epoch=7, purpose="governed-analysis-demo", proposed_action_subject_ref=ref("ontology.exchange-analytics.adt.publish", object_type="gsr-publish-subject"), policy_refs=[ref("authority-policy.local")], obligations=["ENFORCE_SCOPE", "WRITE_AUDIT"], decision="ALLOW", reason_codes=["ROLE_AND_SCOPE_MATCH"], issued_at="2026-08-18T00:00:00.000Z", expires_at="2026-08-18T00:05:00.000Z")
    objects.append(("P15-authority-decision", s))

    s = base("policy-decision-subject/1", "policy-decision", "policy.query.001", "1.0.0", c)
    s.update(principal_context_ref=ref("principal-context.analyst", c), purpose="governed-analysis-demo", resource_refs=[ref("vrs.adt.synthetic", r, "verified-runtime-snapshot")], policy_refs=[ref("runtime-policy.adt", c)], input_context_digest=fake_digest("policy-query-context"), decision="ALLOW", reason_codes=["POLICY_MATCH"], obligations=["ENFORCE_SCOPE", "WRITE_AUDIT"], evaluated_at="2026-08-18T00:01:00.000Z", valid_until="2026-08-18T00:01:05.000Z")
    objects.append(("P15b-policy-decision", s))

    s = base("verification-attempt-subject/1", "verification-attempt", "attempt.semantic.001", "1.0.0", g)
    s.update(gate_evaluation_ref=ref("evaluation.semantic.001", g, "gate-evaluation"), authority_decision_ref=ref("authority.attest.semantic.001", g, "authority-decision"))
    objects.append(("P16-verification-attempt", s))

    attempt_map = {gate: ref(f"attempt.{gate.lower()}", g if gate == "SEMANTIC_APPROVAL" else r, "verification-attempt") for gate in ["SEMANTIC_APPROVAL", "BINDING_DATA_VALIDATION", "DISCLOSURE_POLICY_CLEARANCE", "RUNTIME_CAPABILITY_COMPATIBILITY", "CONTROL_GOLDEN_EVALUATION"]}
    s = base("vrs-seal-proposal-subject/1", "vrs-seal-proposal", "seal-proposal.adt.synthetic", "1.0.0", r)
    s.update(runtime_snapshot_payload_ref=ref("payload.adt.synthetic", r, "runtime-snapshot-payload"), verification_attempt_refs_by_gate=attempt_map)
    objects.append(("P17-vrs-seal-proposal", s))

    s = base("verified-runtime-snapshot-subject/1", "verified-runtime-snapshot", "vrs.adt.synthetic", "1.0.0", r)
    s.update(seal_proposal_ref=ref("seal-proposal.adt.synthetic", r, "vrs-seal-proposal"), seal_authority_decision_ref=ref("authority.seal.001", r, "authority-decision"), seal_status="SEALED", limitations=["local-authority", "synthetic-data"])
    objects.append(("P18-vrs", s))

    s = base("activation-intent-subject/1", "activation-intent", "activation-intent.0001", "1", c)
    s.update(action="ACTIVATE", vrs_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), expected_head_ref=None, expected_activation_epoch=0, idempotency_key="opaque-activation-token-001", reason_code="INITIAL", requested_at="2026-08-18T00:00:00.000Z")
    objects.append(("P19-activation-intent", s))

    s = base("activation-record-subject/1", "activation-record", "activation.0001", "1", c)
    s.update(intent_ref=ref("activation-intent.0001", c, "activation-intent"), eligibility_decision_ref=ref("eligibility.activate.001", c, "execution-eligibility-decision"), authority_decision_ref=ref("authority.activate.001", c, "authority-decision"), sequence=1, previous_record_ref=None, activation_epoch=1, committed_at="2026-08-18T00:00:00.000Z")
    objects.append(("P20-activation-record", s))

    s = base("revocation-intent-subject/1", "revocation-intent", "revocation-intent.0001", "1", c)
    s.update(target_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), enforcement="BLOCK_NEW_AND_RESULT_RELEASE", expected_head_ref=None, expected_revocation_epoch=0, idempotency_key="opaque-revocation-token-001", reason_code="INTEGRITY", requested_at="2026-08-18T00:10:00.000Z")
    objects.append(("P21-revocation-intent", s))

    s = base("revocation-record-subject/1", "revocation-record", "revocation.0001", "1", c)
    s.update(intent_ref=ref("revocation-intent.0001", c, "revocation-intent"), authority_decision_ref=ref("authority.revoke.001", c, "authority-decision"), sequence=1, previous_record_ref=None, new_revocation_epoch=1, committed_at="2026-08-18T00:10:00.000Z")
    objects.append(("P22-revocation-record", s))

    s = base("execution-eligibility-subject/1", "execution-eligibility-decision", "eligibility.pre-query.001", "1.0.0", c)
    s.update(phase="PRE_QUERY", purpose="governed-analysis-demo", vrs_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), runtime_snapshot_payload_ref=ref("payload.adt.synthetic", r, "runtime-snapshot-payload"), verification_attempt_refs_by_gate=attempt_map, activation_head_ref=ref("activation.0001", c, "activation-record"), request_authority_decision_ref=ref("authority.query.001", c, "authority-decision"), policy_decision_ref=ref("policy.query.001", c, "policy-decision"), revocation_scope_epoch=0, observed_revocation_set_digest=fake_digest("empty-revocation-set"), evaluated_at="2026-08-18T00:01:00.000Z", valid_until="2026-08-18T00:01:05.000Z", decision="ALLOW", reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"])
    objects.append(("P23-eligibility", s))

    s = base("user-projection-subject/1", "user-evidence-projection", "projection.exec.001", "1.0.0", c)
    s.update(execution_id="exec.001", projection_schema_ref=ref("user-projection-schema.adt", r), content_bytes_digest=fake_digest("safe-projection-bytes"), renderer_ref=ref("renderer.adt", r), locale="en-HK", timezone="Asia/Hong_Kong", unit_profile_ref=ref("unit.hkd-million"), rounding_profile_ref=ref("rounding.scale6"), classification_ref=ref("classification.public"))
    objects.append(("P24-user-projection", s))

    s = base("execution-evidence-subject/1", "execution-evidence-envelope", "execution.exec.001", "1.0.0", c)
    s.update(execution_id="exec.001", principal_context_ref=ref("principal-context.analyst", c), purpose="governed-analysis-demo", gsr_ref=ref("ontology.exchange-analytics.adt", g, "governed-semantic-release"), vrs_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), activation_record_ref=ref("activation.0001", c, "activation-record"), pre_query_eligibility_ref=ref("eligibility.pre-query.001", c, "execution-eligibility-decision"), policy_decision_ref=ref("policy.query.001", c, "policy-decision"), data_identity_ref=ref("dataset.adt.synthetic", r, "data-identity"), plan_ref=ref("plan.exec.001", c), query_ref=ref("query.exec.001", c), operator_refs=[ref("operator.exact-period-compare", r)], facts_ref=ref("facts.exec.001", c), claims_ref=ref("claims.exec.001", c), user_projection_ref=ref("projection.exec.001", c, "user-evidence-projection"), candidate_status="ANSWER_CANDIDATE", boundary_code=None, query_engine_access_count=1, started_at="2026-08-18T00:01:00.000Z", completed_at="2026-08-18T00:01:01.000Z", replay_level="evidence_only")
    objects.append(("P25-execution-evidence", s))

    s = base("result-release-commit-subject/1", "result-release-commit", "release.exec.001", "1", c)
    s.update(execution_evidence_ref=ref("execution.exec.001", c, "execution-evidence-envelope"), user_projection_ref=ref("projection.exec.001", c, "user-evidence-projection"), result_release_eligibility_ref=ref("eligibility.release.001", c, "execution-eligibility-decision"), activation_head_ref=ref("activation.0001", c, "activation-record"), vrs_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), policy_decision_ref=ref("policy.release.001", c, "policy-decision"), revocation_scope_epoch=0, commit_sequence=1, committed_at="2026-08-18T00:01:01.000Z")
    objects.append(("P26-result-release", s))

    s = base("unknown-concept-payload-subject/1", "proposed-scr-payload", "scr-payload.001", "1.0.0", g)
    s.update(request_type="UNKNOWN_CONCEPT", safe_term_alias_ref=ref("safe-term.turnover-velocity"), semantic_area_code="MARKET_METRICS", reason_code="CONCEPT_NOT_BOUND", safe_context_codes=["METRIC_TERM"], safe_detail_artifact_ref=ref("safe-detail.001"), interaction_handle_ref=ref("interaction.opaque.001"), observed_gsr_ref=ref("ontology.exchange-analytics.adt", g, "governed-semantic-release"), observed_vrs_ref=ref("vrs.adt.synthetic", r, "verified-runtime-snapshot"), boundary_execution_ref=ref("execution.boundary.001", c, "execution-evidence-envelope"), requested_action_code="REVIEW")
    objects.append(("P27-unknown-concept", s))

    s = base("payload-disclosure-evaluation-subject/1", "payload-disclosure-evaluation", "disclosure-evaluation.scr.001", "1.0.0", g)
    s.update(proposed_payload_ref=ref("scr-payload.001", g, "proposed-scr-payload"), safe_detail_artifact_ref=ref("safe-detail.001"), source_scope=scope(g), destination_scope=scope(g), requester_principal_ref=ref("principal.market-analyst"), receiving_audience_ref=ref("audience.studio-triage"), purpose="semantic-change-triage", classification="PUBLIC", allowed_fields=["reason_code", "safe_detail_artifact_ref", "safe_term_alias_ref", "semantic_area_code"], policy_refs=[ref("scr-disclosure-policy.001")], obligations=["NO_RAW_QUESTION", "REAUTHORIZE_REFS"], decision="ALLOW", reason_codes=["MINIMUM_DISCLOSURE_PASS"], issued_at="2026-08-18T00:02:00.000Z", expires_at="2026-08-18T00:07:00.000Z")
    objects.append(("P28a-payload-disclosure-evaluation", s))

    s = base("payload-disclosure-decision-subject/1", "payload-disclosure-decision", "disclosure.scr.001", "1.0.0", g)
    s.update(evaluation_ref=ref("disclosure-evaluation.scr.001", g, "payload-disclosure-evaluation"), disclosure_authority_decision_ref=ref("authority.scr-disclosure.001", g, "authority-decision"))
    objects.append(("P28b-payload-disclosure-decision", s))

    s = base("scr-enqueue-proposal-subject/1", "scr-enqueue-proposal", "scr-enqueue-proposal.001", "1.0.0", g)
    s.update(proposed_payload_ref=ref("scr-payload.001", g, "proposed-scr-payload"), payload_disclosure_decision_ref=ref("disclosure.scr.001", g, "payload-disclosure-decision"), idempotency_key="opaque-scr-token-001", requested_at="2026-08-18T00:02:00.000Z", limitations=["no-raw-question", "synthetic-scope"])
    objects.append(("P29a-scr-enqueue-proposal", s))

    s = base("semantic-change-request-subject/1", "semantic-change-request", "scr.001", "1.0.0", g)
    s.update(enqueue_proposal_ref=ref("scr-enqueue-proposal.001", g, "scr-enqueue-proposal"), requester_authority_decision_ref=ref("authority.scr-enqueue.001", g, "authority-decision"))
    objects.append(("P29b-scr", s))

    s = base("canonical-test-subject/1", "canonical-test", "canonical.features", "1.0.0", g)
    s.update(chinese_nfc="港交所", escaped="quote=\" slash=/ backslash=\\ newline=\n", decimal_value={"coefficient": "100", "scale": 2}, nullable=None, ordered_values=["q4", "q3"], enabled=True)
    objects.append(("P30-canonical-features", s))
    return objects


def negative_vectors() -> list[dict[str, Any]]:
    return [
        {"id": "N01-utf8-bom", "raw_utf8_hex": "efbbbf7b7d", "validation": "raw-json", "expected_error": "UTF8_BOM_FORBIDDEN"},
        {"id": "N02-invalid-utf8", "raw_utf8_hex": "7b22ff223a317d", "validation": "raw-json", "expected_error": "INVALID_UTF8"},
        {"id": "N03-duplicate-key", "input_json": "{\"a\":1,\"a\":2}", "validation": "raw-json", "expected_error": "DUPLICATE_KEY"},
        {"id": "N04-non-nfc-string", "input_json": "{\"value\":\"e\\u0301\"}", "validation": "canonical", "expected_error": "NON_NFC"},
        {"id": "N05-non-nfc-key", "input_json": "{\"e\\u0301\":\"value\"}", "validation": "canonical", "expected_error": "NON_NFC_KEY"},
        {"id": "N06-unpaired-surrogate", "input_json": "{\"value\":\"\\ud800\"}", "validation": "canonical", "expected_error": "UNPAIRED_SURROGATE"},
        {"id": "N07-binary-float", "input_json": "{\"value\":1.5}", "validation": "canonical", "expected_error": "FLOAT_FORBIDDEN"},
        {"id": "N08-exponent-number", "input_json": "{\"value\":1e2}", "validation": "canonical", "expected_error": "FLOAT_FORBIDDEN"},
        {"id": "N09-negative-zero-number", "input_json": "{\"value\":-0}", "validation": "raw-number", "expected_error": "NEGATIVE_ZERO_FORBIDDEN"},
        {"id": "N10-nan", "input_json": "{\"value\":NaN}", "validation": "raw-number", "expected_error": "NON_FINITE_FORBIDDEN"},
        {"id": "N11-infinity", "input_json": "{\"value\":Infinity}", "validation": "raw-number", "expected_error": "NON_FINITE_FORBIDDEN"},
        {"id": "N12-integer-overflow", "input_json": "{\"value\":9007199254740992}", "validation": "canonical", "expected_error": "INTEGER_OUT_OF_RANGE"},
        {"id": "N13-timestamp-offset", "input_json": "{\"issued_at\":\"2026-08-18T00:00:00.000+00:00\"}", "validation": "timestamp", "expected_error": "TIMESTAMP_NOT_UTC_MILLISECOND_Z"},
        {"id": "N14-timestamp-no-millis", "input_json": "{\"issued_at\":\"2026-08-18T00:00:00Z\"}", "validation": "timestamp", "expected_error": "TIMESTAMP_NOT_UTC_MILLISECOND_Z"},
        {"id": "N15-timestamp-leap-second", "input_json": "{\"issued_at\":\"2026-08-18T00:00:60.000Z\"}", "validation": "timestamp", "expected_error": "INVALID_TIMESTAMP"},
        {"id": "N16-timestamp-invalid-date", "input_json": "{\"issued_at\":\"2026-02-30T00:00:00.000Z\"}", "validation": "timestamp", "expected_error": "INVALID_TIMESTAMP"},
        {"id": "N17-null-nonnullable", "input_json": "{\"subject_schema\":null}", "validation": "base-subject", "expected_error": "NULL_NOT_ALLOWED"},
        {"id": "N18-unknown-field", "input_json": "{\"subject_schema\":\"canonical-test-subject/1\",\"unexpected\":true}", "validation": "canonical-test-schema", "expected_error": "UNKNOWN_FIELD"},
        {"id": "N19-unsorted-set", "input_json": "{\"limitations\":[\"z\",\"a\"]}", "validation": "set", "expected_error": "SET_NOT_CANONICALLY_SORTED"},
        {"id": "N20-duplicate-set", "input_json": "{\"limitations\":[\"a\",\"a\"]}", "validation": "set", "expected_error": "SET_DUPLICATE"},
        {"id": "N21-uppercase-digest", "input_json": "{\"subject_digest\":\"sha-256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"}", "validation": "digest", "expected_error": "INVALID_DIGEST"},
        {"id": "N22-latest-version", "input_json": "{\"object_version\":\"latest\"}", "validation": "version", "expected_error": "RESERVED_VERSION"},
        {"id": "N23-identity-conflict", "registry_case": {"scope": {"tenant_id": "local-synthetic", "workspace_id": "adt-poc"}, "object_type": "artifact", "object_id": "same.identity", "object_version": "1.0.0", "existing_digest": fake_digest("one"), "incoming_digest": fake_digest("two")}, "validation": "registry", "expected_error": "IDENTITY_CONFLICT"},
        {"id": "N24-self-digest-field", "input_json": "{\"subject_schema\":\"canonical-test-subject/1\",\"subject_digest\":\"" + fake_digest("self") + "\"}", "validation": "canonical-test-schema", "expected_error": "UNKNOWN_FIELD"},
        {"id": "N25-decimal-negative-zero", "input_json": "{\"decimal_value\":{\"coefficient\":\"-0\",\"scale\":2}}", "validation": "decimal", "expected_error": "INVALID_DECIMAL_COEFFICIENT"},
        {"id": "N26-decimal-leading-zero", "input_json": "{\"decimal_value\":{\"coefficient\":\"01\",\"scale\":2}}", "validation": "decimal", "expected_error": "INVALID_DECIMAL_COEFFICIENT"},
        {"id": "N27-decimal-exponent", "input_json": "{\"decimal_value\":{\"coefficient\":\"1e2\",\"scale\":0}}", "validation": "decimal", "expected_error": "INVALID_DECIMAL_COEFFICIENT"},
        {"id": "N28-decimal-scale-range", "input_json": "{\"decimal_value\":{\"coefficient\":\"1\",\"scale\":19}}", "validation": "decimal", "expected_error": "INVALID_DECIMAL_SCALE"},
        {"id": "N29-unsorted-ref-set", "input_json": json.dumps({"refs": [ref("z"), ref("a")]}, ensure_ascii=False, separators=(",", ":")), "validation": "ref-set", "expected_error": "SET_NOT_CANONICALLY_SORTED"},
        {"id": "N30-wrong-scope-shape", "input_json": "{\"scope\":{\"tenant_id\":\"local-synthetic\",\"workspace_id\":\"adt-poc\",\"channel\":\"active\"}}", "validation": "runtime-scope", "expected_error": "INVALID_SCOPE_SHAPE"},
    ]


def main() -> None:
    positives = []
    for vector_id, subject in positive_subjects():
        schema = subject["subject_schema"]
        canonical_json = canonical(subject)
        _preimage_hex, expected_digest = digest(schema, canonical_json)
        positives.append(
            {
                "id": vector_id,
                "subject_schema": schema,
                "input_json": json.dumps(subject, ensure_ascii=False, separators=(",", ":")),
                "canonical_json": canonical_json,
                "subject_digest": expected_digest,
            }
        )

    document = {
        "fixture_schema": "shared-contract-canonical-vectors/1",
        "contract_version": CONTRACT,
        "canonicalization_profile": PROFILE,
        "digest_algorithm": "sha-256",
        "domain_prefix_utf8": "spc-v0.1",
        "positive_count": len(positives),
        "negative_count": len(negative_vectors()),
        "positive": positives,
        "negative": negative_vectors(),
    }
    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if len(sys.argv) == 3 and sys.argv[1] == "--output":
        Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: generate_vectors.py [--output PATH]")
    print(rendered, end="")


if __name__ == "__main__":
    main()
