#!/usr/bin/env python3
"""Generate the checked-in core@1.1 canonical and integrated conformance fixture.

The frozen core@1 generator remains untouched. This revision reuses only its
fixture-generation helpers; the verifier is independently implemented and does
not import either generator.
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
import unicodedata
from pathlib import Path
from typing import Any

import generate_vectors as v0


STAGE_PROFILE = "synthetic-trusted-flow/core@1.1"
ANNEX_PROFILE = "shared-contract-technical-profile/0.1.1"
FIXTURE_SCHEMA = "shared-contract-core-1.1-vectors/1"
CONFORMANCE_MANIFEST = Path(__file__).with_name("core-profile-conformance-manifest-1.1.json")
EXTERNAL_MANIFEST_SCHEMA = "external-leaf-manifest/1"
PREDECESSOR_HELPER_SHA256 = "dcabbb415dd29308c17e8c7c775a43315591d6e7ba24a65da0abd48a06709485"

EXTERNAL_ENTRIES: dict[str, dict[str, Any]] = {}

LEAF_TYPE_SCHEMA = {
    "BUILD_SCHEMA": ("build-schema-leaf", "build-schema-leaf/1"),
    "EVIDENCE": ("evidence-leaf", "evidence-leaf/1"),
    "INTEGRITY": ("integrity-leaf", "integrity-leaf/1"),
    "PRINCIPAL": ("principal-leaf", "principal-leaf/1"),
    "PRINCIPAL_CONTEXT": ("principal-context-leaf", "principal-context-leaf/1"),
    "PRINCIPAL_REGISTRY": ("principal-registry-leaf", "principal-registry-leaf/1"),
    "REQUEST": ("request-leaf", "request-leaf/1"),
    "ROLE_ASSIGNMENT": ("role-assignment-leaf", "role-assignment-leaf/1"),
    "SAFE_HANDLE": ("safe-handle-leaf", "safe-handle-leaf/1"),
    "STATIC_POLICY": ("static-policy-leaf", "static-policy-leaf/1"),
    "SEMANTIC_DECISION": ("semantic-decision-leaf", "semantic-decision-leaf/1"),
    "SUITE_CASE": ("suite-case-leaf", "suite-case-leaf/1"),
    "TRUSTED_SESSION": ("trusted-session-leaf", "trusted-session-leaf/1"),
}


def leaf_class(label: str) -> str:
    if label.startswith("semantic-decision."):
        return "SEMANTIC_DECISION"
    if label.startswith("session."):
        return "TRUSTED_SESSION"
    if label.startswith("principal-registry."):
        return "PRINCIPAL_REGISTRY"
    if label.startswith("principal-context."):
        return "PRINCIPAL_CONTEXT"
    if label.startswith("principal."):
        return "PRINCIPAL"
    if label.startswith(("role-assignment.", "role.")):
        return "ROLE_ASSIGNMENT"
    if label.startswith("request."):
        return "REQUEST"
    if label.startswith("case."):
        return "SUITE_CASE"
    if label.startswith(("safe-term.", "safe-detail.", "interaction.")):
        return "SAFE_HANDLE"
    if "policy" in label:
        return "STATIC_POLICY"
    if label.startswith(("claims.", "evidence.", "facts.", "plan.", "projection-fidelity.", "query.")):
        return "EVIDENCE"
    if any(
        token in label
        for token in (
            "build",
            "schema",
            "renderer",
            "runner",
            "engine",
            "transformer",
            "operator.",
            "compatibility.",
            "evaluation.",
            "failure-contract",
            "operator-input",
            "operator-output",
            "options.",
            "projection.",
            "validation",
            "profile",
        )
    ):
        return "BUILD_SCHEMA"
    return "INTEGRITY"


def allowed_actions_for_role(role_code: str) -> list[str]:
    exact = {
        "reference-truth-owner": ["SELECT_REFERENCE"],
        "disclosure-approver": ["APPROVE_CLEARED_INPUT", "SCR_DISCLOSE"],
        "release-manager": ["PUBLISH"],
        "runtime-release-manager": ["ATTEST", "SEAL"],
        "runtime-operator": ["ACTIVATE", "REVOKE_VRS"],
        "analyst": ["EVIDENCE_READ", "PRE_QUERY", "RESOLVE", "RESULT_RELEASE"],
        "market-analyst": ["EVIDENCE_READ", "PRE_QUERY", "RESOLVE", "RESULT_RELEASE"],
        "result-releaser": ["RESULT_RELEASE"],
        "scr-requester": ["SCR_ENQUEUE"],
        "triager": ["SCR_TRIAGE"],
        "attestor": ["ATTEST"],
    }
    if role_code.endswith("-attestor"):
        return ["ATTEST"]
    return exact.get(role_code, ["ATTEST"])


def external_facts(label: str, class_code: str, kind: str) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "classification": "PUBLIC",
        "dependency_free": True,
        "status": "ACTIVE",
    }
    if class_code == "TRUSTED_SESSION":
        facts.update(
            principal_object_id="principal." + label.removeprefix("session."),
            trust_epoch=11,
            issued_at="2026-08-19T00:00:00.000Z",
            expires_at="2026-08-20T00:00:00.000Z",
        )
    elif class_code == "PRINCIPAL_REGISTRY":
        facts.update(snapshot_digest=v0.fake_digest("registry-snapshot.local"), trust_epoch=11)
    elif class_code == "PRINCIPAL":
        facts.update(registry_object_id="principal-registry.local")
    elif class_code == "PRINCIPAL_CONTEXT":
        facts.update(principal_object_id="principal.market-analyst", purpose="governed-analysis-demo")
    elif class_code == "ROLE_ASSIGNMENT":
        if label.startswith("role-assignment."):
            _prefix, principal_code, role_code = label.split(".", 2)
        else:
            role_code = label.removeprefix("role.")
            principal_code = role_code
        facts.update(
            principal_object_id="principal." + principal_code,
            role_code=role_code,
            allowed_actions=allowed_actions_for_role(role_code),
            trust_epoch=11,
            issued_at="2026-08-19T00:00:00.000Z",
            expires_at="2026-08-20T00:00:00.000Z",
        )
    elif class_code == "STATIC_POLICY":
        actions = ["SELECT_REFERENCE"] if label.startswith("selection-policy.adt.r01") else sorted(
            set(
                [
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
            )
        )
        facts.update(
            allowed_actions=actions,
            allowed_purposes=["governed-analysis-demo", "ontology-build", "semantic-change-triage"],
            effective_at="2026-08-19T00:00:00.000Z",
            expires_at="2026-08-20T00:00:00.000Z",
            policy_version="1.0.0",
        )
    elif class_code == "SEMANTIC_DECISION":
        facts.update(
            decision_profile="recorded-semantic-decision",
            decision_kind="scope-period-rounding",
            source_cleared_input_subject_digest=v0.fake_digest("semantic-decision.default-input"),
            candidate_subject_digest=v0.fake_digest("semantic-decision.default-candidate"),
            trace_subject_digest=v0.fake_digest("semantic-decision.default-trace"),
            decision_outcome="ACCEPTED",
        )
    elif class_code == "REQUEST":
        facts.update(request_family="governed-analysis", allowed_purpose="governed-analysis-demo")
    elif class_code == "SAFE_HANDLE":
        facts.update(raw_value_present=False, handle_kind="opaque-safe-handle")
    elif class_code == "SUITE_CASE":
        facts.update(suite_id="adt.tracer.v1.suite")
    elif class_code == "EVIDENCE":
        facts.update(evidence_profile="deterministic-synthetic")
    elif class_code == "BUILD_SCHEMA":
        facts.update(build_or_schema_identity=label)
    else:
        facts.update(allowed_slot_family="integrity")
    facts["scope_kind"] = kind
    return facts


def artifact(
    label: str,
    kind: str = "governance",
    *,
    fact_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    class_code = leaf_class(label)
    object_type, subject_schema = LEAF_TYPE_SCHEMA[class_code]
    facts = external_facts(label, class_code, kind)
    if fact_overrides:
        facts.update(copy.deepcopy(fact_overrides))
    entry_without_ref = {
        "leaf_class": class_code,
        "object_id": label,
        "object_version": "1.0.0",
        "scope": v0.scope(kind),
        "facts": facts,
    }
    leaf_digest = "sha-256:" + hashlib.sha256(
        b"spc-external-leaf-v1\x00" + v0.canonical(entry_without_ref).encode("utf-8")
    ).hexdigest()
    result = {
        "object_type": object_type,
        "object_id": label,
        "object_version": "1.0.0",
        "contract_version": v0.CONTRACT,
        "subject_schema": subject_schema,
        "canonicalization_profile": v0.PROFILE,
        "scope": v0.scope(kind),
        "subject_digest": leaf_digest,
    }
    entry = {**entry_without_ref, "ref": copy.deepcopy(result)}
    key = v0.canonical(result)
    existing = EXTERNAL_ENTRIES.get(key)
    if existing is not None and existing != entry:
        raise ValueError(f"external leaf collision: {label}")
    EXTERNAL_ENTRIES[key] = entry
    return result


def opaque_locator(label: str) -> dict[str, Any]:
    return {
        "locator_handle": "opaque-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:24],
        "scope": v0.scope("governance"),
        "classification": "PUBLIC",
    }


def domain_digest(domain: str, value: Any) -> str:
    """Digest a closed logical value with an explicit domain separator."""

    return "sha-256:" + hashlib.sha256(
        domain.encode("utf-8") + b"\x00" + v0.canonical(value).encode("utf-8")
    ).hexdigest()


def derived_selection_key_digest(scope: dict[str, Any], candidate_set_ref: dict[str, Any]) -> str:
    return domain_digest(
        "spc-reference-selection-key-v1",
        {
            "scope": copy.deepcopy(scope),
            "candidate_set_subject_digest": candidate_set_ref["subject_digest"],
        },
    )


def derived_request_identity_digest(
    candidate_set_ref: dict[str, Any],
    proposal_ref: dict[str, Any],
    decision_ref: dict[str, Any],
    manifest_ref: dict[str, Any],
) -> str:
    return domain_digest(
        "spc-reference-selection-request-v1",
        {
            "candidate_set_ref": copy.deepcopy(candidate_set_ref),
            "selection_proposal_ref": copy.deepcopy(proposal_ref),
            "selection_authority_decision_ref": copy.deepcopy(decision_ref),
            "reference_manifest_ref": copy.deepcopy(manifest_ref),
        },
    )


def derived_journal_record_digest(receipt_fields: dict[str, Any]) -> str:
    """Digest the logical committed record; excludes its own digest field."""

    return domain_digest(
        "spc-reference-selection-logical-record-v1",
        {
            key: copy.deepcopy(value)
            for key, value in receipt_fields.items()
            if key != "journal_record_digest"
        },
    )


def empty_revocation_digest(scope: dict[str, Any], epoch: int = 0) -> str:
    return domain_digest(
        "spc-revocation-set-v1",
        {"scope": copy.deepcopy(scope), "epoch": epoch, "active_revocation_refs": []},
    )

v0.SUBJECT_SCHEMA_BY_OBJECT_TYPE.update(
    {
        "cleared-input-proposal": "cleared-input-proposal-subject/1",
        "cleared-input": "cleared-input-subject/1",
        "reference-candidate": "reference-candidate-subject/1",
        "reference-candidate-set": "reference-candidate-set-subject/1",
        "reference-selection-proposal": "reference-selection-proposal-subject/1",
        "reference-reselection-transition": "reference-reselection-transition-subject/1",
        "reference-selection-authority-decision": "reference-selection-authority-decision-subject/1",
        "reference-selection-commit-receipt": "reference-selection-commit-receipt-subject/1",
        "reference-manifest": "reference-manifest-subject/2",
        "oracle-provenance": "oracle-provenance-subject/1",
        "semantic-content-manifest": "semantic-content-manifest-subject/1",
        "gsr-publish-subject": "gsr-publish-subject/2",
        "control-manifest": "control-manifest-subject/1",
        "suite-manifest": "suite-manifest-subject/1",
        "gate-evaluation": "gate-evaluation-subject/1",
        "authority-decision": "authority-decision-subject/1",
        "policy-decision": "policy-decision-subject/1",
        "verification-attempt": "verification-attempt-subject/1",
        "vrs-seal-proposal": "vrs-seal-proposal-subject/1",
        "verified-runtime-snapshot": "verified-runtime-snapshot-subject/1",
        "activation-intent": "activation-intent-subject/1",
        "activation-record": "activation-record-subject/1",
        "revocation-intent": "revocation-intent-subject/1",
        "revocation-record": "revocation-record-subject/1",
        "result-release-commit": "result-release-commit-subject/1",
        "payload-disclosure-evaluation": "payload-disclosure-evaluation-subject/1",
        "payload-disclosure-decision": "payload-disclosure-decision-subject/1",
        "scr-enqueue-proposal": "scr-enqueue-proposal-subject/1",
        "semantic-change-request": "semantic-change-request-subject/1",
        "concept-resolution-evidence": "concept-resolution-evidence-subject/1",
        "execution-evidence-envelope": "execution-evidence-subject/2",
        "proposed-scr-payload": "unknown-concept-payload-subject/2",
        "governed-semantic-release": "governed-semantic-release-subject/1",
        "runtime-snapshot-payload": "runtime-snapshot-payload-subject/1",
        "data-identity": "data-identity-subject/1",
    }
)


class Graph:
    """Topologically builds a fully resolvable product-subject graph."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.refs: dict[str, dict[str, Any]] = {}

    def add(
        self,
        key: str,
        schema: str,
        object_type: str,
        object_id: str,
        version: str,
        kind: str,
        **fields: Any,
    ) -> dict[str, Any]:
        subject = v0.base(schema, object_type, object_id, version, kind)
        subject.update(copy.deepcopy(fields))
        rendered = v0.canonical(subject)
        _preimage, subject_digest = v0.digest(schema, rendered)
        ref = {
            "object_type": object_type,
            "object_id": object_id,
            "object_version": version,
            "contract_version": v0.CONTRACT,
            "subject_schema": schema,
            "canonicalization_profile": v0.PROFILE,
            "scope": v0.scope(kind),
            "subject_digest": subject_digest,
        }
        self.records.append(
            {
                "key": key,
                "subject_schema": schema,
                "input_json": json.dumps(subject, ensure_ascii=False, separators=(",", ":")),
                "canonical_json": rendered,
                "subject_digest": subject_digest,
            }
        )
        self.refs[key] = ref
        return copy.deepcopy(ref)

    def ref(self, key: str) -> dict[str, Any]:
        return copy.deepcopy(self.refs[key])


def add_authority(
    graph: Graph,
    key: str,
    action: str,
    resource_ref: dict[str, Any],
    kind: str,
    purpose: str,
    principal: str,
    role: str,
    issued_at: str = "2026-08-19T00:00:00.000Z",
    expires_at: str = "2026-08-19T01:00:00.000Z",
) -> dict[str, Any]:
    return graph.add(
        key,
        "authority-decision-subject/1",
        "authority-decision",
        key.replace("_", "."),
        "1.0.0",
        kind,
        action=action,
        trusted_session_ref=artifact(f"session.{principal}", kind),
        principal_ref=artifact(f"principal.{principal}", kind),
        principal_registry_ref=artifact("principal-registry.local", kind),
        role_assignment_ref=artifact(f"role-assignment.{principal}.{role}", kind),
        trust_epoch=11,
        purpose=purpose,
        proposed_action_subject_ref=copy.deepcopy(resource_ref),
        policy_refs=[artifact("authority-policy.local", kind)],
        obligations=["ENFORCE_SCOPE", "WRITE_AUDIT"],
        decision="ALLOW",
        reason_codes=["ROLE_AND_SCOPE_MATCH"],
        issued_at=issued_at,
        expires_at=expires_at,
    )


def add_selection_authority(
    graph: Graph,
    key: str,
    resource_ref: dict[str, Any],
    issued_at: str = "2026-08-19T00:00:00.000Z",
    expires_at: str = "2026-08-19T01:00:00.000Z",
    policy_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    principal = "reference-truth-owner"
    return graph.add(
        key,
        "reference-selection-authority-decision-subject/1",
        "reference-selection-authority-decision",
        key.replace("_", "."),
        "1.0.0",
        "governance",
        action="SELECT_REFERENCE",
        trusted_session_ref=artifact(f"session.{principal}"),
        principal_ref=artifact(f"principal.{principal}"),
        principal_registry_ref=artifact("principal-registry.local"),
        role_assignment_ref=artifact(
            f"role-assignment.{principal}.reference-truth-owner"
        ),
        trust_epoch=11,
        purpose="ontology-build",
        proposed_action_subject_ref=copy.deepcopy(resource_ref),
        policy_refs=[
            copy.deepcopy(policy_ref)
            if policy_ref is not None
            else artifact("selection-policy.adt.r01")
        ],
        obligations=["ENFORCE_SCOPE", "WRITE_AUDIT"],
        decision="ALLOW",
        reason_codes=["ROLE_AND_SCOPE_MATCH"],
        issued_at=issued_at,
        expires_at=expires_at,
    )


def add_policy(
    graph: Graph,
    key: str,
    resource_ref: dict[str, Any],
    purpose: str,
    evaluated_at: str = "2026-08-19T00:10:00.000Z",
    valid_until: str = "2026-08-19T00:20:00.000Z",
) -> dict[str, Any]:
    return graph.add(
        key,
        "policy-decision-subject/1",
        "policy-decision",
        key.replace("_", "."),
        "1.0.0",
        "channel",
        principal_context_ref=artifact("principal-context.analyst", "channel"),
        purpose=purpose,
        resource_refs=[copy.deepcopy(resource_ref)],
        policy_refs=[artifact("runtime-policy.adt", "channel")],
        input_context_digest=v0.fake_digest(key),
        decision="ALLOW",
        reason_codes=["POLICY_MATCH"],
        obligations=["ENFORCE_SCOPE", "WRITE_AUDIT"],
        evaluated_at=evaluated_at,
        valid_until=valid_until,
    )


def add_gate(
    graph: Graph,
    key: str,
    gate_type: str,
    gate_subject_ref: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    evaluation_ref = graph.add(
        f"{key}_evaluation",
        "gate-evaluation-subject/1",
        "gate-evaluation",
        f"evaluation.{key}",
        "1.0.0",
        kind,
        gate_type=gate_type,
        gate_subject_ref=copy.deepcopy(gate_subject_ref),
        outcome="PASS",
        evidence_refs=[artifact(f"evidence.{key}", kind)],
        limitations=["local-authority", "synthetic-data"],
        validity_mode="UNTIL",
        issued_at="2026-08-19T00:02:00.000Z",
        expires_at="2026-09-18T00:00:00.000Z",
    )
    authority_ref = add_authority(
        graph,
        f"{key}_attest_authority",
        "ATTEST",
        evaluation_ref,
        kind,
        "governed-analysis-demo",
        f"{key}-attestor",
        "attestor",
    )
    return graph.add(
        f"{key}_attempt",
        "verification-attempt-subject/1",
        "verification-attempt",
        f"attempt.{key}",
        "1.0.0",
        kind,
        gate_evaluation_ref=evaluation_ref,
        authority_decision_ref=authority_ref,
    )


def add_projection(graph: Graph, key: str, execution_id: str) -> dict[str, Any]:
    return graph.add(
        key,
        "user-projection-subject/1",
        "user-evidence-projection",
        f"projection.{execution_id}",
        "1.0.0",
        "channel",
        execution_id=execution_id,
        projection_schema_ref=artifact("user-projection-schema.adt", "runtime"),
        content_bytes_digest=v0.fake_digest(f"safe-bytes.{execution_id}"),
        renderer_ref=artifact("renderer.adt", "runtime"),
        locale="en-HK",
        timezone="Asia/Hong_Kong",
        unit_profile_ref=artifact("unit.hkd-million"),
        rounding_profile_ref=artifact("rounding.scale6"),
        classification_ref=artifact("classification.public"),
    )


def build_integrated_graph() -> tuple[Graph, dict[str, Any]]:
    graph = Graph()
    g, r, c = "governance", "runtime", "channel"

    suite_ref = graph.add(
        "suite",
        "suite-manifest-subject/1",
        "suite-manifest",
        "adt.tracer.v1.suite",
        "1.0.0",
        g,
        suite_id="adt.tracer.v1.suite",
        cases=[artifact(f"case.{index:02d}") for index in range(1, 9)],
        denominator=8,
        status_counts={"ANSWERED": 4, "CLARIFY": 1, "REFUSED": 3},
        mutation_profile_ref=artifact("mutation.adt.core"),
        frozen_at="2026-08-19T00:00:00.000Z",
    )

    candidate_specs = [
        ("public", "adt.public-style-synthetic.v1", "manual_transcription"),
        ("synthetic", "adt.synthetic.v1", "synthetic"),
        ("aux", "adt.auxiliary-negative-fixture.v1", "synthetic"),
    ]
    candidate_refs: dict[str, dict[str, Any]] = {}
    control_refs: dict[str, dict[str, Any]] = {}
    input_refs: dict[str, dict[str, Any]] = {}
    oracle_refs: dict[str, dict[str, Any]] = {}
    for label, case_id, origin in candidate_specs:
        label_limitations = ["constructed-target-coupled", "non-hkex-validation"]
        if label == "public":
            label_limitations.append("public-style-synthetic")
        proposal_ref = graph.add(
            f"input_{label}_proposal",
            "cleared-input-proposal-subject/1",
            "cleared-input-proposal",
            f"input.adt.{label}.proposal",
            "1.0.0",
            g,
            classification="PUBLIC",
            origin=origin,
            allowed_uses=["ontology_build", "synthetic_demo"],
            safe_content_ref=artifact(f"safe-content.adt.{label}"),
            opaque_source_locator_ref=opaque_locator(f"opaque-source.{label}"),
            limitations=["non-hkex-validation"],
        )
        input_authority_ref = add_authority(
            graph,
            f"input_{label}_authority",
            "APPROVE_CLEARED_INPUT",
            proposal_ref,
            g,
            "ontology-build",
            "disclosure-approver",
            "disclosure-approver",
        )
        input_refs[label] = graph.add(
            f"input_{label}",
            "cleared-input-subject/1",
            "cleared-input",
            f"input.adt.{label}",
            "1.0.0",
            g,
            proposal_ref=proposal_ref,
            input_disclosure_authority_decision_ref=input_authority_ref,
        )
        oracle_refs[label] = graph.add(
            f"oracle_{label}",
            "oracle-provenance-subject/1",
            "oracle-provenance",
            f"oracle.adt.{label}",
            "1.0.0",
            g,
            reference_case_id=case_id,
            oracle_class="CONSTRUCTED_SYNTHETIC",
            cleared_input_ref=input_refs[label],
            source_ref=artifact(f"oracle-source.adt.{label}"),
            derivation_ref=artifact(f"oracle-derivation.adt.{label}"),
            author_ref=artifact("principal.reference-truth-owner"),
            reviewer_ref=artifact("principal.control-reviewer"),
            limitations=v0.sorted_set(label_limitations),
            frozen_at="2026-08-19T00:00:00.000Z",
        )
        control_refs[label] = graph.add(
            f"control_{label}",
            "control-manifest-subject/1",
            "control-manifest",
            f"control.adt.{label}",
            "1.0.0",
            g,
            reference_case_id=case_id,
            oracle_class="CONSTRUCTED_SYNTHETIC",
            oracle_provenance_refs=[copy.deepcopy(oracle_refs[label])],
            formula_ref=artifact(f"formula.adt.{label}"),
            period_profile_ref=artifact("period.quarter"),
            population_profile_ref=artifact("population.trades"),
            unit_ref=artifact("unit.hkd-million"),
            rounding_profile_ref=artifact("rounding.scale6"),
            expected_result_refs=[artifact(f"expected.{label}.q3"), artifact(f"expected.{label}.q4")],
            tolerance_profile_ref=artifact("tolerance.exact-scale6"),
            expected_value_author_ref=artifact("principal.reference-truth-owner"),
            fixture_author_ref=artifact("principal.reference-truth-owner"),
            reviewer_ref=artifact("principal.control-reviewer"),
            truth_frozen_before_fixture=True,
            allowed_claims=["reviewed-constructed-synthetic-conformance"],
            limitations=v0.sorted_set(label_limitations),
            frozen_at="2026-08-19T00:00:00.000Z",
        )
        candidate_refs[label] = graph.add(
            f"candidate_{label}",
            "reference-candidate-subject/1",
            "reference-candidate",
            f"reference-candidate.adt.{label}",
            "1.0.0",
            g,
            reference_case_id=case_id,
            cleared_input_ref=input_refs[label],
            control_manifest_ref=control_refs[label],
            suite_manifest_ref=suite_ref,
            oracle_provenance_ref=oracle_refs[label],
            verification_criteria_ref=artifact(f"verification-criteria.adt.{label}"),
            limitations=v0.sorted_set(
                ["non-hkex-validation", "synthetic-scope"]
                + (["public-style-synthetic"] if label == "public" else [])
            ),
            frozen_at="2026-08-19T00:00:00.000Z",
        )

    set_ref = graph.add(
        "candidate_set_predecessor",
        "reference-candidate-set-subject/1",
        "reference-candidate-set",
        "reference-candidate-set.adt",
        "1.0.0",
        g,
        candidate_refs=v0.sorted_set([candidate_refs["public"], candidate_refs["synthetic"]]),
        shared_suite_manifest_ref=suite_ref,
        selection_policy_ref=artifact("selection-policy.adt.r01"),
        denominator=2,
        frozen_at="2026-08-19T00:00:00.000Z",
    )
    selection_proposal_ref = graph.add(
        "selection_proposal_predecessor",
        "reference-selection-proposal-subject/1",
        "reference-selection-proposal",
        "reference-selection.adt.synthetic",
        "1.0.0",
        g,
        candidate_set_ref=set_ref,
        selected_candidate_ref=candidate_refs["synthetic"],
        selected_reference_case_id="adt.synthetic.v1",
        reselection_transition_ref=None,
        limitations=["non-hkex-validation", "synthetic-scope"],
    )
    selection_authority_ref = add_selection_authority(
        graph, "selection_authority_predecessor", selection_proposal_ref
    )
    reference_manifest_ref = graph.add(
        "reference_manifest_predecessor",
        "reference-manifest-subject/2",
        "reference-manifest",
        "reference.adt.synthetic",
        "1.0.0",
        g,
        reference_case_id="adt.synthetic.v1",
        cleared_input_ref=input_refs["synthetic"],
        control_manifest_ref=control_refs["synthetic"],
        suite_manifest_ref=suite_ref,
        oracle_provenance_ref=oracle_refs["synthetic"],
        frozen_at="2026-08-19T00:00:00.000Z",
        selection_proposal_ref=selection_proposal_ref,
        selection_authority_decision_ref=selection_authority_ref,
    )

    selection_receipt_fields = {
        "selection_key_digest": derived_selection_key_digest(v0.scope(g), set_ref),
        "request_identity_digest": derived_request_identity_digest(
            set_ref, selection_proposal_ref, selection_authority_ref, reference_manifest_ref
        ),
        "candidate_set_ref": set_ref,
        "selection_proposal_ref": selection_proposal_ref,
        "selection_authority_decision_ref": selection_authority_ref,
        "reference_manifest_ref": reference_manifest_ref,
        "authority_trust_epoch": 11,
        "authority_policy_snapshot_ref": artifact("selection-policy.adt.r01"),
        "predecessor_receipt_ref": None,
        "transition_ref": None,
        "commit_sequence": 1,
        "committed_at": "2026-08-19T00:00:00.500Z",
        "commit_status": "COMMITTED",
    }
    selection_receipt_fields["journal_record_digest"] = derived_journal_record_digest(
        selection_receipt_fields
    )
    selection_receipt_ref = graph.add(
        "selection_receipt_predecessor",
        "reference-selection-commit-receipt-subject/1",
        "reference-selection-commit-receipt",
        "reference-selection-receipt.adt.synthetic.0001",
        "1.0.0",
        g,
        **selection_receipt_fields,
    )

    predecessor_set_ref = copy.deepcopy(set_ref)
    predecessor_proposal_ref = copy.deepcopy(selection_proposal_ref)
    predecessor_authority_ref = copy.deepcopy(selection_authority_ref)
    predecessor_manifest_ref = copy.deepcopy(reference_manifest_ref)
    predecessor_receipt_ref = copy.deepcopy(selection_receipt_ref)

    corrected_policy_ref = artifact("selection-policy.adt.r01.corrected")
    set_ref = graph.add(
        "candidate_set",
        "reference-candidate-set-subject/1",
        "reference-candidate-set",
        "reference-candidate-set.adt",
        "1.1.0",
        g,
        candidate_refs=v0.sorted_set([candidate_refs["public"], candidate_refs["synthetic"]]),
        shared_suite_manifest_ref=suite_ref,
        selection_policy_ref=corrected_policy_ref,
        denominator=2,
        frozen_at="2026-08-19T00:00:00.600Z",
    )
    transition_ref = graph.add(
        "selection_transition",
        "reference-reselection-transition-subject/1",
        "reference-reselection-transition",
        "reference-reselection-transition.adt.0002",
        "1.0.0",
        g,
        predecessor_candidate_set_ref=predecessor_set_ref,
        predecessor_reference_manifest_ref=predecessor_manifest_ref,
        predecessor_commit_receipt_ref=predecessor_receipt_ref,
        change_reason_code="POLICY_CHANGE",
        changed_component_refs=[corrected_policy_ref],
        evaluated_at="2026-08-19T00:00:00.700Z",
    )
    selection_proposal_ref = graph.add(
        "selection_proposal",
        "reference-selection-proposal-subject/1",
        "reference-selection-proposal",
        "reference-selection.adt.synthetic",
        "1.1.0",
        g,
        candidate_set_ref=set_ref,
        selected_candidate_ref=candidate_refs["synthetic"],
        selected_reference_case_id="adt.synthetic.v1",
        reselection_transition_ref=transition_ref,
        limitations=["non-hkex-validation", "synthetic-scope"],
    )
    selection_authority_ref = add_selection_authority(
        graph,
        "selection_authority",
        selection_proposal_ref,
        issued_at="2026-08-19T00:00:00.700Z",
        policy_ref=corrected_policy_ref,
    )
    reference_manifest_ref = graph.add(
        "reference_manifest",
        "reference-manifest-subject/2",
        "reference-manifest",
        "reference.adt.synthetic",
        "1.1.0",
        g,
        reference_case_id="adt.synthetic.v1",
        cleared_input_ref=input_refs["synthetic"],
        control_manifest_ref=control_refs["synthetic"],
        suite_manifest_ref=suite_ref,
        oracle_provenance_ref=oracle_refs["synthetic"],
        frozen_at="2026-08-19T00:00:00.800Z",
        selection_proposal_ref=selection_proposal_ref,
        selection_authority_decision_ref=selection_authority_ref,
    )
    selection_receipt_fields = {
        "selection_key_digest": derived_selection_key_digest(v0.scope(g), set_ref),
        "request_identity_digest": derived_request_identity_digest(
            set_ref, selection_proposal_ref, selection_authority_ref, reference_manifest_ref
        ),
        "candidate_set_ref": set_ref,
        "selection_proposal_ref": selection_proposal_ref,
        "selection_authority_decision_ref": selection_authority_ref,
        "reference_manifest_ref": reference_manifest_ref,
        "authority_trust_epoch": 11,
        "authority_policy_snapshot_ref": corrected_policy_ref,
        "predecessor_receipt_ref": predecessor_receipt_ref,
        "transition_ref": transition_ref,
        "commit_sequence": 2,
        "committed_at": "2026-08-19T00:00:00.900Z",
        "commit_status": "COMMITTED",
    }
    selection_receipt_fields["journal_record_digest"] = derived_journal_record_digest(
        selection_receipt_fields
    )
    selection_receipt_ref = graph.add(
        "selection_receipt",
        "reference-selection-commit-receipt-subject/1",
        "reference-selection-commit-receipt",
        "reference-selection-receipt.adt.synthetic.0002",
        "1.0.0",
        g,
        **selection_receipt_fields,
    )

    unselected_proposal_ref = graph.add(
        "unselected_selection_proposal",
        "reference-selection-proposal-subject/1",
        "reference-selection-proposal",
        "reference-selection.adt.public-style-uncommitted",
        "1.0.0",
        g,
        candidate_set_ref=set_ref,
        selected_candidate_ref=candidate_refs["public"],
        selected_reference_case_id="adt.public-style-synthetic.v1",
        reselection_transition_ref=transition_ref,
        limitations=["non-hkex-validation", "public-style-synthetic", "synthetic-scope"],
    )
    unselected_authority_ref = add_selection_authority(
        graph, "unselected_selection_authority", unselected_proposal_ref
    )
    unselected_manifest_ref = graph.add(
        "unselected_reference_manifest",
        "reference-manifest-subject/2",
        "reference-manifest",
        "reference.adt.public-style-uncommitted",
        "1.0.0",
        g,
        reference_case_id="adt.public-style-synthetic.v1",
        cleared_input_ref=input_refs["public"],
        control_manifest_ref=control_refs["public"],
        suite_manifest_ref=suite_ref,
        oracle_provenance_ref=oracle_refs["public"],
        frozen_at="2026-08-19T00:00:00.000Z",
        selection_proposal_ref=unselected_proposal_ref,
        selection_authority_decision_ref=unselected_authority_ref,
    )
    unselected_semantic_content_ref = graph.add(
        "unselected_semantic_content",
        "semantic-content-manifest-subject/1",
        "semantic-content-manifest",
        "semantic-content.adt.public-style-uncommitted",
        "1.0.0",
        g,
        reference_manifest_ref=unselected_manifest_ref,
        semantic_schema_ref=artifact("semantic-schema.adt"),
        content_digest=v0.fake_digest("semantic-content.adt.public-style-uncommitted"),
        compiler_build_ref=artifact("semantic-compiler-build.adt"),
        limitations=["non-hkex-validation", "public-style-synthetic", "synthetic-scope"],
        built_at="2026-08-19T00:01:00.000Z",
    )

    semantic_content_ref = graph.add(
        "semantic_content",
        "semantic-content-manifest-subject/1",
        "semantic-content-manifest",
        "semantic-content.adt.synthetic-selected",
        "1.0.0",
        g,
        reference_manifest_ref=reference_manifest_ref,
        semantic_schema_ref=artifact("semantic-schema.adt"),
        content_digest=v0.fake_digest("semantic-content.adt.synthetic-selected"),
        compiler_build_ref=artifact("semantic-compiler-build.adt"),
        limitations=["non-hkex-validation", "synthetic-scope"],
        built_at="2026-08-19T00:01:00.000Z",
    )

    semantic_decision_ref = artifact(
        "semantic-decision.adt.scope-period-rounding",
        fact_overrides={
            "source_cleared_input_subject_digest": input_refs["synthetic"]["subject_digest"],
            "candidate_subject_digest": candidate_refs["synthetic"]["subject_digest"],
            "trace_subject_digest": v0.fake_digest("trace.adt.synthetic.scope-period-rounding"),
        },
    )
    semantic_decision_aux_ref = artifact(
        "semantic-decision.adt.auxiliary",
        fact_overrides={
            "source_cleared_input_subject_digest": input_refs["aux"]["subject_digest"],
            "candidate_subject_digest": candidate_refs["aux"]["subject_digest"],
            "trace_subject_digest": v0.fake_digest("trace.adt.auxiliary"),
        },
    )
    publish_ref = graph.add(
        "gsr_publish",
        "gsr-publish-subject/2",
        "gsr-publish-subject",
        "ontology.exchange-analytics.adt.publish",
        "1.1.0",
        g,
        semantic_version="1.1.0",
        semantic_schema_ref=artifact("semantic-schema.adt"),
        semantic_content_ref=semantic_content_ref,
        selected_reference_manifest_ref=reference_manifest_ref,
        selection_commit_receipt_ref=selection_receipt_ref,
        cleared_input_refs=[input_refs["synthetic"]],
        decision_refs=[semantic_decision_ref],
        required_capability_refs=v0.sorted_set(
            [artifact("capability.exact-period-compare"), artifact("capability.metric-resolve")]
        ),
        binding_requirements_ref=artifact("binding-requirements.adt"),
        policy_requirements_ref=artifact("policy-requirements.adt"),
        disclosure_labels_ref=artifact("disclosure-labels.adt"),
        supersedes_ref=None,
    )
    semantic_subject_ref = graph.add(
        "semantic_gate_subject",
        "semantic-approval-subject/1",
        "semantic-approval-subject",
        "semantic-approval.adt",
        "1.1.0",
        g,
        gsr_publish_subject_ref=publish_ref,
        semantic_validation_profile_ref=artifact("semantic-validation.adt"),
    )
    semantic_attempt_ref = add_gate(graph, "semantic", "SEMANTIC_APPROVAL", semantic_subject_ref, g)
    publish_authority_ref = add_authority(
        graph,
        "publish_authority",
        "PUBLISH",
        publish_ref,
        g,
        "governed-analysis-demo",
        "release-manager",
        "release-manager",
    )
    gsr_ref = graph.add(
        "gsr",
        "governed-semantic-release-subject/1",
        "governed-semantic-release",
        "ontology.exchange-analytics.adt",
        "1.1.0",
        g,
        publish_subject_ref=publish_ref,
        semantic_approval_attempt_ref=semantic_attempt_ref,
        publish_authority_decision_ref=publish_authority_ref,
    )

    data_ref = graph.add(
        "data_identity",
        "data-identity-subject/1",
        "data-identity",
        "dataset.adt.synthetic",
        "1.1.0",
        r,
        dataset_manifest_ref=artifact("dataset-manifest.adt", r),
        schema_digest=v0.fake_digest("dataset-schema.core-1.1"),
        partition_identity_refs=v0.sorted_set([artifact("partition.q3", r), artifact("partition.q4", r)]),
        row_count=126,
        source_engine_ref=artifact("engine.duckdb", r),
        transformation_ref=artifact("transform.synthetic.adt", r),
        policy_scope_ref=artifact("data-policy.synthetic", r),
        frozen_at="2026-08-19T00:00:00.000Z",
        replay_level="evidence_only",
    )
    payload_ref = graph.add(
        "runtime_payload",
        "runtime-snapshot-payload-subject/1",
        "runtime-snapshot-payload",
        "payload.adt.synthetic",
        "1.1.0",
        r,
        gsr_ref=gsr_ref,
        runtime_semantic_projection_ref=artifact("runtime-semantic.adt", r),
        binding_bundle_ref=artifact("binding.adt.synthetic", r),
        projection_policy_bundle_ref=artifact("projection-policy.adt", r),
        runtime_capability_manifest_ref=artifact("runtime-capabilities.adt", r),
        data_identity_ref=data_ref,
        control_manifest_ref=control_refs["synthetic"],
        suite_manifest_ref=suite_ref,
        reference_manifest_ref=reference_manifest_ref,
        oracle_provenance_ref=oracle_refs["synthetic"],
        evaluation_runner_manifest_ref=artifact("runner.adt", r),
        compatibility_profile_ref=artifact("compatibility.exact", r),
        projection_profile_ref=artifact("projection.adt", r),
    )

    binding_subject_ref = graph.add(
        "binding_gate_subject",
        "binding-data-validation-subject/1",
        "binding-data-validation-subject",
        "binding-data-validation.adt",
        "1.1.0",
        r,
        gsr_binding_requirements_ref=artifact("binding-requirements.adt"),
        runtime_semantic_projection_ref=artifact("runtime-semantic.adt", r),
        binding_bundle_ref=artifact("binding.adt.synthetic", r),
        data_identity_ref=data_ref,
        binding_validation_profile_ref=artifact("binding-validation.adt", r),
    )
    disclosure_subject_ref = graph.add(
        "disclosure_gate_subject",
        "disclosure-policy-subject/1",
        "disclosure-policy-subject",
        "disclosure-policy.adt",
        "1.1.0",
        r,
        gsr_disclosure_labels_ref=artifact("disclosure-labels.adt"),
        gsr_policy_requirements_ref=artifact("policy-requirements.adt"),
        runtime_semantic_projection_ref=artifact("runtime-semantic.adt", r),
        runtime_projection_schema_ref=artifact("runtime-projection-schema.adt", r),
        user_projection_schema_ref=artifact("user-projection-schema.adt", r),
        projection_transformer_ref=artifact("projection-transformer.adt", r),
        projection_policy_bundle_ref=artifact("projection-policy.adt", r),
        audience_purpose_profile_ref=artifact("audience.demo-analyst", r),
        projection_fidelity_report_ref=artifact("projection-fidelity.adt", r),
        disclosure_validation_profile_ref=artifact("disclosure-validation.adt", r),
    )
    runtime_subject_ref = graph.add(
        "runtime_gate_subject",
        "runtime-capability-subject/1",
        "runtime-capability-subject",
        "runtime-capability.adt",
        "1.1.0",
        r,
        gsr_semantic_content_ref=semantic_content_ref,
        gsr_capability_requirements_ref=artifact("capability-requirements.adt"),
        runtime_semantic_projection_ref=artifact("runtime-semantic.adt", r),
        runtime_capability_manifest_ref=artifact("runtime-capabilities.adt", r),
        provider_build_ref=artifact("runtime-build.adt", r),
        input_schema_ref=artifact("operator-input.adt", r),
        output_schema_ref=artifact("operator-output.adt", r),
        failure_contract_ref=artifact("failure-contract.adt", r),
        options_profile_ref=artifact("options.adt", r),
        policy_obligations_ref=artifact("operator-policy.adt", r),
        compatibility_profile_ref=artifact("compatibility.exact", r),
        projection_fidelity_report_ref=artifact("projection-fidelity.adt", r),
        conformance_suite_ref=artifact("operator-conformance.adt", r),
    )
    control_subject_ref = graph.add(
        "control_gate_subject",
        "control-golden-subject/1",
        "control-golden-subject",
        "control-golden.adt",
        "1.1.0",
        r,
        runtime_snapshot_payload_ref=payload_ref,
        control_manifest_ref=control_refs["synthetic"],
        suite_manifest_ref=suite_ref,
        reference_manifest_ref=reference_manifest_ref,
        oracle_provenance_ref=oracle_refs["synthetic"],
        evaluation_runner_manifest_ref=artifact("runner.adt", r),
        evaluation_profile_ref=artifact("evaluation.adt", r),
    )
    attempts = {
        "SEMANTIC_APPROVAL": semantic_attempt_ref,
        "BINDING_DATA_VALIDATION": add_gate(
            graph, "binding", "BINDING_DATA_VALIDATION", binding_subject_ref, r
        ),
        "DISCLOSURE_POLICY_CLEARANCE": add_gate(
            graph, "disclosure", "DISCLOSURE_POLICY_CLEARANCE", disclosure_subject_ref, r
        ),
        "RUNTIME_CAPABILITY_COMPATIBILITY": add_gate(
            graph, "runtime", "RUNTIME_CAPABILITY_COMPATIBILITY", runtime_subject_ref, r
        ),
        "CONTROL_GOLDEN_EVALUATION": add_gate(
            graph, "control", "CONTROL_GOLDEN_EVALUATION", control_subject_ref, r
        ),
    }
    seal_proposal_ref = graph.add(
        "seal_proposal",
        "vrs-seal-proposal-subject/1",
        "vrs-seal-proposal",
        "seal-proposal.adt.synthetic",
        "1.1.0",
        r,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
    )
    seal_authority_ref = add_authority(
        graph,
        "seal_authority",
        "SEAL",
        seal_proposal_ref,
        r,
        "governed-analysis-demo",
        "runtime-release-manager",
        "runtime-release-manager",
    )
    vrs_ref = graph.add(
        "vrs",
        "verified-runtime-snapshot-subject/1",
        "verified-runtime-snapshot",
        "vrs.adt.synthetic",
        "1.1.0",
        r,
        seal_proposal_ref=seal_proposal_ref,
        seal_authority_decision_ref=seal_authority_ref,
        seal_status="SEALED",
        limitations=["local-authority", "synthetic-data"],
    )

    revocation_intent_ref = graph.add(
        "revocation_intent_uncommitted",
        "revocation-intent-subject/1",
        "revocation-intent",
        "revocation-intent.uncommitted.0001",
        "1",
        c,
        target_ref=vrs_ref,
        enforcement="BLOCK_NEW_AND_RESULT_RELEASE",
        expected_head_ref=None,
        expected_revocation_epoch=0,
        idempotency_key="opaque-revocation-token-011",
        reason_code="INTEGRITY",
        requested_at="2026-08-19T00:03:00.000Z",
    )
    add_authority(
        graph,
        "revoke_authority",
        "REVOKE_VRS",
        revocation_intent_ref,
        c,
        "governed-analysis-demo",
        "runtime-operator",
        "runtime-operator",
    )
    add_authority(
        graph,
        "resolve_authority",
        "RESOLVE",
        artifact("request.resolve.001", c),
        c,
        "governed-analysis-demo",
        "market-analyst",
        "analyst",
    )

    activation_intent_ref = graph.add(
        "activation_intent",
        "activation-intent-subject/1",
        "activation-intent",
        "activation-intent.0001",
        "1",
        c,
        action="ACTIVATE",
        vrs_ref=vrs_ref,
        expected_head_ref=None,
        expected_activation_epoch=0,
        idempotency_key="opaque-activation-token-011",
        reason_code="INITIAL",
        requested_at="2026-08-19T00:05:00.000Z",
    )
    activation_authority_ref = add_authority(
        graph,
        "activation_authority",
        "ACTIVATE",
        activation_intent_ref,
        c,
        "governed-analysis-demo",
        "runtime-operator",
        "runtime-operator",
    )
    activation_policy_ref = add_policy(
        graph,
        "activation_policy",
        vrs_ref,
        "governed-analysis-demo",
        "2026-08-19T00:05:00.000Z",
        "2026-08-19T00:05:05.000Z",
    )
    activation_eligibility_ref = graph.add(
        "activation_eligibility",
        "execution-eligibility-subject/1",
        "execution-eligibility-decision",
        "eligibility.activate.001",
        "1.0.0",
        c,
        phase="ACTIVATE",
        purpose="governed-analysis-demo",
        vrs_ref=vrs_ref,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
        activation_head_ref=None,
        request_authority_decision_ref=activation_authority_ref,
        policy_decision_ref=activation_policy_ref,
        revocation_scope_epoch=0,
        observed_revocation_set_digest=empty_revocation_digest(v0.scope(c)),
        evaluated_at="2026-08-19T00:05:00.000Z",
        valid_until="2026-08-19T00:05:05.000Z",
        decision="ALLOW",
        reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"],
    )
    activation_record_ref = graph.add(
        "activation_record",
        "activation-record-subject/1",
        "activation-record",
        "activation.0001",
        "1",
        c,
        intent_ref=activation_intent_ref,
        eligibility_decision_ref=activation_eligibility_ref,
        authority_decision_ref=activation_authority_ref,
        sequence=1,
        previous_record_ref=None,
        activation_epoch=1,
        committed_at="2026-08-19T00:05:00.000Z",
    )

    prequery_authority_ref = add_authority(
        graph,
        "prequery_authority",
        "PRE_QUERY",
        artifact("request.exec.001", c),
        c,
        "governed-analysis-demo",
        "market-analyst",
        "analyst",
    )
    # The policy may be evaluated before activation, but PRE_QUERY eligibility may
    # not.  Keeping these clocks distinct makes the activation-order mutation a
    # genuine cross-object test instead of an incidental policy-time failure.
    prequery_policy_ref = add_policy(
        graph,
        "prequery_policy",
        vrs_ref,
        "governed-analysis-demo",
        evaluated_at="2026-08-19T00:04:00.000Z",
    )
    prequery_eligibility_ref = graph.add(
        "prequery_eligibility",
        "execution-eligibility-subject/1",
        "execution-eligibility-decision",
        "eligibility.pre-query.001",
        "1.0.0",
        c,
        phase="PRE_QUERY",
        purpose="governed-analysis-demo",
        vrs_ref=vrs_ref,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
        activation_head_ref=activation_record_ref,
        request_authority_decision_ref=prequery_authority_ref,
        policy_decision_ref=prequery_policy_ref,
        revocation_scope_epoch=0,
        observed_revocation_set_digest=empty_revocation_digest(v0.scope(c)),
        evaluated_at="2026-08-19T00:10:00.000Z",
        valid_until="2026-08-19T00:10:05.000Z",
        decision="ALLOW",
        reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"],
    )

    def evidence(
        key: str,
        execution_id: str,
        status: str,
        boundary_code: str | None,
        query_count: int,
        projection_ref: dict[str, Any] | None,
        concept_resolution_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        answered = status == "ANSWER_CANDIDATE"
        failed_execution = status == "FAILED_EXECUTION"
        return graph.add(
            key,
            "execution-evidence-subject/2",
            "execution-evidence-envelope",
            f"execution.{execution_id}",
            "1.0.0",
            c,
            execution_id=execution_id,
            principal_context_ref=artifact("principal-context.analyst", c),
            purpose="governed-analysis-demo",
            gsr_ref=gsr_ref,
            vrs_ref=vrs_ref,
            activation_record_ref=activation_record_ref,
            pre_query_eligibility_ref=prequery_eligibility_ref,
            policy_decision_ref=prequery_policy_ref,
            data_identity_ref=data_ref,
            plan_ref=artifact(f"plan.{execution_id}", c) if answered or failed_execution else None,
            query_ref=artifact(f"query.{execution_id}", c) if answered or failed_execution else None,
            operator_refs=[artifact("operator.metric-resolve", r)] if query_count else [],
            facts_ref=artifact(f"facts.{execution_id}", c) if answered else None,
            claims_ref=artifact(f"claims.{execution_id}", c) if projection_ref is not None else None,
            user_projection_ref=copy.deepcopy(projection_ref),
            concept_resolution_evidence_ref=copy.deepcopy(concept_resolution_ref),
            candidate_status=status,
            boundary_code=boundary_code,
            query_engine_access_count=query_count,
            started_at="2026-08-19T00:10:00.000Z",
            completed_at="2026-08-19T00:10:01.000Z",
            replay_level="evidence_only",
        )

    answer_projection_ref = add_projection(graph, "answer_projection", "exec.answer")
    answer_evidence_ref = evidence(
        "answer_evidence", "exec.answer", "ANSWER_CANDIDATE", None, 1, answer_projection_ref
    )
    clarify_projection_ref = add_projection(graph, "clarify_projection", "exec.clarify")
    clarify_evidence_ref = evidence(
        "clarify_evidence", "exec.clarify", "CLARIFY", "MISSING_PERIOD", 0, clarify_projection_ref
    )
    refused_projection_ref = add_projection(graph, "concept_projection", "exec.concept")
    concept_resolution_ref = graph.add(
        "concept_resolution_evidence",
        "concept-resolution-evidence-subject/1",
        "concept-resolution-evidence",
        "concept-resolution.exec.concept",
        "1.0.0",
        c,
        execution_id="exec.concept",
        safe_term_alias_ref=artifact("safe-term.turnover-velocity"),
        semantic_area_code="MARKET_METRICS",
        term_well_formed=True,
        semantic_area_status="KNOWN",
        semantic_registry_ref=artifact("semantic-registry.market-metrics"),
        alias_resolution_profile_ref=artifact("alias-resolution-profile.adt"),
        resolver_build_ref=artifact("resolver-build.adt"),
        resolution_completed=True,
        binding_count=0,
        authorization_classification="ELIGIBLE",
        pre_query_eligibility_ref=prequery_eligibility_ref,
        policy_decision_ref=prequery_policy_ref,
        query_engine_access_count=0,
        evaluated_at="2026-08-19T00:10:00.500Z",
    )
    concept_evidence_ref = evidence(
        "concept_evidence",
        "exec.concept",
        "REFUSED",
        "CONCEPT_NOT_BOUND",
        0,
        refused_projection_ref,
        concept_resolution_ref,
    )
    failed_precondition_ref = evidence(
        "failed_precondition_evidence",
        "exec.precondition",
        "FAILED_PRECONDITION",
        "SNAPSHOT_NOT_ACTIVE",
        0,
        None,
    )
    failed_execution_ref = evidence(
        "failed_execution_evidence",
        "exec.failed",
        "FAILED_EXECUTION",
        "PARTIAL_RESULT",
        1,
        None,
    )

    release_authority_ref = add_authority(
        graph,
        "release_authority",
        "RESULT_RELEASE",
        answer_evidence_ref,
        c,
        "governed-analysis-demo",
        "result-releaser",
        "result-releaser",
    )
    release_policy_ref = add_policy(
        graph, "release_policy", answer_evidence_ref, "governed-analysis-demo"
    )
    release_eligibility_ref = graph.add(
        "release_eligibility",
        "execution-eligibility-subject/1",
        "execution-eligibility-decision",
        "eligibility.release.001",
        "1.0.0",
        c,
        phase="RESULT_RELEASE",
        purpose="governed-analysis-demo",
        vrs_ref=vrs_ref,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
        activation_head_ref=activation_record_ref,
        request_authority_decision_ref=release_authority_ref,
        policy_decision_ref=release_policy_ref,
        revocation_scope_epoch=0,
        observed_revocation_set_digest=empty_revocation_digest(v0.scope(c)),
        evaluated_at="2026-08-19T00:10:01.000Z",
        valid_until="2026-08-19T00:10:05.000Z",
        decision="ALLOW",
        reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"],
    )
    release_commit_ref = graph.add(
        "release_commit",
        "result-release-commit-subject/1",
        "result-release-commit",
        "release.exec.answer",
        "1",
        c,
        execution_evidence_ref=answer_evidence_ref,
        user_projection_ref=answer_projection_ref,
        result_release_eligibility_ref=release_eligibility_ref,
        activation_head_ref=activation_record_ref,
        vrs_ref=vrs_ref,
        policy_decision_ref=release_policy_ref,
        revocation_scope_epoch=0,
        commit_sequence=1,
        committed_at="2026-08-19T00:10:01.000Z",
    )

    concept_release_authority_ref = add_authority(
        graph,
        "concept_release_authority",
        "RESULT_RELEASE",
        concept_evidence_ref,
        c,
        "governed-analysis-demo",
        "result-releaser",
        "result-releaser",
    )
    concept_release_policy_ref = add_policy(
        graph, "concept_release_policy", concept_evidence_ref, "governed-analysis-demo"
    )
    concept_release_eligibility_ref = graph.add(
        "concept_release_eligibility",
        "execution-eligibility-subject/1",
        "execution-eligibility-decision",
        "eligibility.release.concept.001",
        "1.0.0",
        c,
        phase="RESULT_RELEASE",
        purpose="governed-analysis-demo",
        vrs_ref=vrs_ref,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
        activation_head_ref=activation_record_ref,
        request_authority_decision_ref=concept_release_authority_ref,
        policy_decision_ref=concept_release_policy_ref,
        revocation_scope_epoch=0,
        observed_revocation_set_digest=empty_revocation_digest(v0.scope(c)),
        evaluated_at="2026-08-19T00:10:02.000Z",
        valid_until="2026-08-19T00:10:06.000Z",
        decision="ALLOW",
        reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"],
    )
    concept_release_commit_ref = graph.add(
        "concept_release_commit",
        "result-release-commit-subject/1",
        "result-release-commit",
        "release.exec.concept",
        "1",
        c,
        execution_evidence_ref=concept_evidence_ref,
        user_projection_ref=refused_projection_ref,
        result_release_eligibility_ref=concept_release_eligibility_ref,
        activation_head_ref=activation_record_ref,
        vrs_ref=vrs_ref,
        policy_decision_ref=concept_release_policy_ref,
        revocation_scope_epoch=0,
        commit_sequence=2,
        committed_at="2026-08-19T00:10:02.000Z",
    )

    evidence_read_authority_ref = add_authority(
        graph,
        "evidence_read_authority",
        "EVIDENCE_READ",
        answer_evidence_ref,
        c,
        "governed-analysis-demo",
        "market-analyst",
        "analyst",
    )
    evidence_read_policy_ref = add_policy(graph, "evidence_read_policy", answer_evidence_ref, "governed-analysis-demo")
    evidence_read_eligibility_ref = graph.add(
        "evidence_read_eligibility",
        "execution-eligibility-subject/1",
        "execution-eligibility-decision",
        "eligibility.evidence-read.001",
        "1.0.0",
        c,
        phase="EVIDENCE_READ",
        purpose="governed-analysis-demo",
        vrs_ref=vrs_ref,
        runtime_snapshot_payload_ref=payload_ref,
        verification_attempt_refs_by_gate=attempts,
        activation_head_ref=activation_record_ref,
        request_authority_decision_ref=evidence_read_authority_ref,
        policy_decision_ref=evidence_read_policy_ref,
        revocation_scope_epoch=0,
        observed_revocation_set_digest=empty_revocation_digest(v0.scope(c)),
        evaluated_at="2026-08-19T00:11:00.000Z",
        valid_until="2026-08-19T00:11:05.000Z",
        decision="ALLOW",
        reason_codes=["ACTIVE", "ATTESTATIONS_VALID", "AUTHORIZED", "NOT_REVOKED", "SEALED"],
    )

    payload_scr_ref = graph.add(
        "scr_payload",
        "unknown-concept-payload-subject/2",
        "proposed-scr-payload",
        "scr-payload.001",
        "1.0.0",
        g,
        request_type="UNKNOWN_CONCEPT",
        safe_term_alias_ref=artifact("safe-term.turnover-velocity"),
        semantic_area_code="MARKET_METRICS",
        reason_code="CONCEPT_NOT_BOUND",
        safe_context_codes=["METRIC_TERM"],
        safe_detail_artifact_ref=artifact("safe-detail.001"),
        interaction_handle_ref=artifact("interaction.opaque.001"),
        observed_gsr_ref=gsr_ref,
        observed_vrs_ref=vrs_ref,
        boundary_execution_ref=concept_evidence_ref,
        boundary_release_commit_ref=concept_release_commit_ref,
        requested_action_code="REVIEW",
    )
    disclosure_evaluation_ref = graph.add(
        "scr_disclosure_evaluation",
        "payload-disclosure-evaluation-subject/1",
        "payload-disclosure-evaluation",
        "disclosure-evaluation.scr.001",
        "1.0.0",
        g,
        proposed_payload_ref=payload_scr_ref,
        safe_detail_artifact_ref=artifact("safe-detail.001"),
        source_scope=v0.scope(c),
        destination_scope=v0.scope(g),
        requester_principal_ref=artifact("principal.market-analyst"),
        receiving_audience_ref=artifact("audience.studio-triage"),
        purpose="semantic-change-triage",
        classification="PUBLIC",
        allowed_fields=["reason_code", "safe_detail_artifact_ref", "safe_term_alias_ref", "semantic_area_code"],
        policy_refs=[artifact("scr-disclosure-policy.001")],
        obligations=["NO_RAW_QUESTION", "REAUTHORIZE_REFS"],
        decision="ALLOW",
        reason_codes=["MINIMUM_DISCLOSURE_PASS"],
        issued_at="2026-08-19T00:12:00.000Z",
        expires_at="2026-08-19T00:17:00.000Z",
    )
    disclosure_authority_ref = add_authority(
        graph,
        "scr_disclosure_authority",
        "SCR_DISCLOSE",
        disclosure_evaluation_ref,
        g,
        "semantic-change-triage",
        "disclosure-approver",
        "disclosure-approver",
    )
    disclosure_decision_ref = graph.add(
        "scr_disclosure_decision",
        "payload-disclosure-decision-subject/1",
        "payload-disclosure-decision",
        "disclosure.scr.001",
        "1.0.0",
        g,
        evaluation_ref=disclosure_evaluation_ref,
        disclosure_authority_decision_ref=disclosure_authority_ref,
    )
    enqueue_proposal_ref = graph.add(
        "scr_enqueue_proposal",
        "scr-enqueue-proposal-subject/1",
        "scr-enqueue-proposal",
        "scr-enqueue-proposal.001",
        "1.0.0",
        g,
        proposed_payload_ref=payload_scr_ref,
        payload_disclosure_decision_ref=disclosure_decision_ref,
        idempotency_key="opaque-scr-token-011",
        requested_at="2026-08-19T00:12:00.000Z",
        limitations=["no-raw-question", "synthetic-scope"],
    )
    enqueue_authority_ref = add_authority(
        graph,
        "scr_enqueue_authority",
        "SCR_ENQUEUE",
        enqueue_proposal_ref,
        g,
        "semantic-change-triage",
        "scr-requester",
        "scr-requester",
    )
    scr_ref = graph.add(
        "scr",
        "semantic-change-request-subject/1",
        "semantic-change-request",
        "scr.001",
        "1.0.0",
        g,
        enqueue_proposal_ref=enqueue_proposal_ref,
        requester_authority_decision_ref=enqueue_authority_ref,
    )
    add_authority(
        graph,
        "scr_triage_authority",
        "SCR_TRIAGE",
        scr_ref,
        g,
        "semantic-change-triage",
        "triager",
        "triager",
    )

    context = {
        "selected_case_id": "adt.synthetic.v1",
        "selected_candidate_ref": candidate_refs["synthetic"],
        "unselected_candidate_ref": candidate_refs["public"],
        "unselected_selection_proposal_ref": unselected_proposal_ref,
        "unselected_selection_authority_ref": unselected_authority_ref,
        "unselected_reference_manifest_ref": unselected_manifest_ref,
        "unselected_semantic_content_ref": unselected_semantic_content_ref,
        "aux_candidate_ref": candidate_refs["aux"],
        "aux_oracle_ref": oracle_refs["aux"],
        "candidate_set_ref": set_ref,
        "predecessor_candidate_set_ref": predecessor_set_ref,
        "predecessor_selection_proposal_ref": predecessor_proposal_ref,
        "predecessor_selection_authority_ref": predecessor_authority_ref,
        "predecessor_reference_manifest_ref": predecessor_manifest_ref,
        "predecessor_selection_receipt_ref": predecessor_receipt_ref,
        "selection_transition_ref": transition_ref,
        "selection_proposal_ref": selection_proposal_ref,
        "selection_authority_ref": selection_authority_ref,
        "reference_manifest_ref": reference_manifest_ref,
        "selection_receipt_ref": selection_receipt_ref,
        "semantic_content_ref": semantic_content_ref,
        "semantic_decision_ref": semantic_decision_ref,
        "semantic_decision_aux_ref": semantic_decision_aux_ref,
        "selected_input_ref": input_refs["synthetic"],
        "unselected_input_ref": input_refs["public"],
        "selected_control_ref": control_refs["synthetic"],
        "selected_suite_ref": suite_ref,
        "selected_oracle_ref": oracle_refs["synthetic"],
        "unselected_oracle_ref": oracle_refs["public"],
        "unselected_control_ref": control_refs["public"],
        "gsr_ref": gsr_ref,
        "runtime_payload_ref": payload_ref,
        "seal_proposal_ref": seal_proposal_ref,
        "vrs_ref": vrs_ref,
        "activation_record_ref": activation_record_ref,
        "prequery_eligibility_ref": prequery_eligibility_ref,
        "release_commit_ref": release_commit_ref,
        "evidence_read_eligibility_ref": evidence_read_eligibility_ref,
        "scr_ref": scr_ref,
        "concept_evidence_ref": concept_evidence_ref,
        "concept_resolution_evidence_ref": concept_resolution_ref,
        "concept_release_commit_ref": concept_release_commit_ref,
        "outcomes": {
            "ANSWERED": {"evidence_ref": answer_evidence_ref, "release_commit_ref": release_commit_ref},
            "CLARIFY": {"evidence_ref": clarify_evidence_ref},
            "REFUSED": {
                "evidence_ref": concept_evidence_ref,
                "release_commit_ref": concept_release_commit_ref,
            },
            "FAILED_PRECONDITION": {"evidence_ref": failed_precondition_ref},
            "FAILED_EXECUTION": {"evidence_ref": failed_execution_ref},
        },
        "resolver_observation": {
            "execution_ref": concept_evidence_ref,
            "concept_resolution_ref": concept_resolution_ref,
        },
        "demo_label": {
            "reference_case_id": "adt.synthetic.v1",
            "reference_manifest_ref": reference_manifest_ref,
            "limitations": ["constructed-target-coupled", "non-hkex-validation"],
        },
    }
    return graph, context


def isolated_positive_subjects(
    graph: Graph, context: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """Return one normal positive per schema plus bounded isolated variants."""

    positives: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for record in graph.records:
        schema_id = record["subject_schema"]
        if schema_id in seen:
            continue
        seen.add(schema_id)
        positives.append((f"P-{schema_id.replace('/', '-')}", json.loads(record["input_json"])))

    revocation_intent_ref = graph.ref("revocation_intent_uncommitted")
    revocation_record = v0.base(
        "revocation-record-subject/1",
        "revocation-record",
        "revocation.0001",
        "1",
        "channel",
    )
    revocation_record.update(
        intent_ref=revocation_intent_ref,
        authority_decision_ref=graph.ref("revoke_authority"),
        sequence=1,
        previous_record_ref=None,
        new_revocation_epoch=1,
        committed_at="2026-08-19T00:20:00.000Z",
    )
    positives.append(("P-revocation-record", revocation_record))

    canonical = v0.base(
        "canonical-test-subject/1", "canonical-test", "canonical.features", "1.0.0", "governance"
    )
    canonical.update(
        chinese_nfc="港交所",
        escaped='quote=" slash=/ backslash=\\ newline=\n',
        decimal_value={"coefficient": "1234500", "scale": 4},
        nullable=None,
        ordered_values=["first", "second"],
        enabled=True,
    )
    positives.append(("P-canonical-features", canonical))
    return positives


def semantic_negatives(context: dict[str, Any]) -> list[dict[str, Any]]:
    g = v0.scope("governance")
    selected = context["selected_candidate_ref"]
    unselected = context["unselected_candidate_ref"]
    aux = context["aux_candidate_ref"]
    proposal = context["selection_proposal_ref"]
    decision = context["selection_authority_ref"]
    selected_tuple = {
        "reference_case_id": context["selected_case_id"],
        "cleared_input_ref": context["selected_input_ref"],
        "control_manifest_ref": context["selected_control_ref"],
        "suite_manifest_ref": context["selected_suite_ref"],
        "oracle_provenance_ref": context["selected_oracle_ref"],
    }
    base_authority = {
        "action": "SELECT_REFERENCE",
        "scope": g,
        "purpose": "ontology-build",
        "decision": "ALLOW",
        "proposed_action_subject_ref": proposal,
        "expected_proposal_ref": proposal,
        "trusted_principal_id": "principal.reference-truth-owner",
        "trusted_role_id": "role.reference-truth-owner",
        "caller_claimed_role_id": None,
        "trust_epoch": 11,
        "current_trust_epoch": 11,
        "expires_at": "2026-08-19T01:00:00.000Z",
        "evaluated_at": "2026-08-19T00:30:00.000Z",
    }
    base_final = {
        "selected_tuple": selected_tuple,
        "final_tuple": copy.deepcopy(selected_tuple),
        "selection_proposal_ref": proposal,
        "expected_proposal_ref": proposal,
        "selection_authority_decision_ref": decision,
        "decision_action": "SELECT_REFERENCE",
        "decision_outcome": "ALLOW",
        "decision_proposed_action_subject_ref": proposal,
    }
    return [
        {
            "id": "N31-candidate-set-denominator",
            "validation": "candidate-set",
            "case": {
                "candidate_refs": [unselected, selected],
                "candidate_case_ids": ["adt.public-reference.v1", "adt.synthetic.v1"],
                "candidate_suite_refs": [context["selected_suite_ref"], context["selected_suite_ref"]],
                "shared_suite_manifest_ref": context["selected_suite_ref"],
                "denominator": 3,
            },
            "expected_error": "REFERENCE_CANDIDATE_SET_INVALID",
        },
        {
            "id": "N32-candidate-set-suite-mismatch",
            "validation": "candidate-set",
            "case": {
                "candidate_refs": [unselected, selected],
                "candidate_case_ids": ["adt.public-reference.v1", "adt.synthetic.v1"],
                "candidate_suite_refs": [context["selected_suite_ref"], artifact("suite.other")],
                "shared_suite_manifest_ref": context["selected_suite_ref"],
                "denominator": 2,
            },
            "expected_error": "REFERENCE_CANDIDATE_SET_INVALID",
        },
        {
            "id": "N33-proposal-selected-not-member",
            "validation": "selection-proposal",
            "case": {
                "set_members": [unselected, selected],
                "selected_candidate_ref": aux,
                "selected_candidate_case_id": "adt.auxiliary-negative-fixture.v1",
                "selected_reference_case_id": "adt.auxiliary-negative-fixture.v1",
            },
            "expected_error": "REFERENCE_SELECTED_CANDIDATE_INVALID",
        },
        {
            "id": "N34-proposal-case-id-mismatch",
            "validation": "selection-proposal",
            "case": {
                "set_members": [unselected, selected],
                "selected_candidate_ref": selected,
                "selected_candidate_case_id": "adt.synthetic.v1",
                "selected_reference_case_id": "adt.public-reference.v1",
            },
            "expected_error": "REFERENCE_SELECTED_CANDIDATE_INVALID",
        },
        {
            "id": "N35-selection-authority-wrong-role",
            "validation": "selection-authority",
            "case": {**base_authority, "trusted_role_id": "role.studio-domain-owner"},
            "expected_error": "AUTHORITY_DENIED_OR_STALE",
        },
        {
            "id": "N36-caller-role-cannot-grant",
            "validation": "selection-authority",
            "case": {
                **base_authority,
                "trusted_principal_id": "principal.studio-domain-owner",
                "trusted_role_id": "role.studio-domain-owner",
                "caller_claimed_role_id": "role.reference-truth-owner",
            },
            "expected_error": "AUTHORITY_DENIED_OR_STALE",
        },
        {
            "id": "N37-selection-authority-wrong-scope",
            "validation": "selection-authority",
            "case": {**base_authority, "scope": v0.scope("runtime")},
            "expected_error": "SCOPE_MISMATCH",
        },
        {
            "id": "N38-selection-authority-wrong-purpose",
            "validation": "selection-authority",
            "case": {**base_authority, "purpose": "governed-analysis-demo"},
            "expected_error": "AUTHORITY_DENIED_OR_STALE",
        },
        {
            "id": "N39-selection-authority-expired",
            "validation": "selection-authority",
            "case": {**base_authority, "evaluated_at": "2026-08-19T01:00:00.001Z"},
            "expected_error": "AUTHORITY_DENIED_OR_STALE",
        },
        {
            "id": "N40-final-manifest-missing-decision",
            "validation": "final-reference",
            "case": {**base_final, "selection_authority_decision_ref": None},
            "expected_error": "REFERENCE_FINAL_INVALID",
        },
        {
            "id": "N41-final-manifest-tuple-mismatch",
            "validation": "final-reference",
            "case": {
                **base_final,
                "final_tuple": {**selected_tuple, "control_manifest_ref": context["unselected_control_ref"]},
            },
            "expected_error": "REFERENCE_FINAL_INVALID",
        },
        {
            "id": "N42-final-manifest-wrong-action",
            "validation": "final-reference",
            "case": {**base_final, "decision_action": "PUBLISH"},
            "expected_error": "AUTHORITY_DENIED_OR_STALE",
        },
        {
            "id": "N43-same-set-different-proposal-conflict",
            "validation": "selection-commit-sequence",
            "case": {
                "scope": g,
                "candidate_set_digest": context["candidate_set_ref"]["subject_digest"],
                "attempts": [
                    {"manifest_id": "manifest.a", "manifest_version": "1", "proposal_ref": proposal, "decision_ref": decision, "final_digest": context["reference_manifest_ref"]["subject_digest"]},
                    {"manifest_id": "manifest.b", "manifest_version": "1", "proposal_ref": {**proposal, "subject_digest": v0.fake_digest("other-proposal")}, "decision_ref": decision, "final_digest": v0.fake_digest("other-final")},
                ],
            },
            "expected_error": "REFERENCE_SELECTION_CONFLICT",
        },
        {
            "id": "N44-manifest-version-cannot-bypass",
            "validation": "selection-commit-sequence",
            "case": {
                "scope": g,
                "candidate_set_digest": context["candidate_set_ref"]["subject_digest"],
                "attempts": [
                    {"manifest_id": "manifest.a", "manifest_version": "1", "proposal_ref": proposal, "decision_ref": decision, "final_digest": context["reference_manifest_ref"]["subject_digest"]},
                    {"manifest_id": "manifest.a", "manifest_version": "2", "proposal_ref": proposal, "decision_ref": {**decision, "subject_digest": v0.fake_digest("different-decision")}, "final_digest": v0.fake_digest("other-version-final")},
                ],
            },
            "expected_error": "REFERENCE_SELECTION_CONFLICT",
        },
        {
            "id": "N45-fixture-before-final-commit",
            "validation": "fixture-timeline",
            "case": {"reference_manifest_committed": False, "fixture_write_count": 1},
            "expected_error": "REFERENCE_FINAL_REQUIRED",
        },
        {
            "id": "N46-unselected-control-downstream",
            "validation": "downstream-selection",
            "case": {
                "selected_reference_manifest_ref": context["reference_manifest_ref"],
                "selected_control_ref": context["selected_control_ref"],
                "payload_reference_manifest_ref": context["reference_manifest_ref"],
                "payload_control_ref": context["unselected_control_ref"],
                "control_gate_reference_manifest_ref": context["reference_manifest_ref"],
                "control_gate_control_ref": context["selected_control_ref"],
            },
            "expected_error": "REFERENCE_DOWNSTREAM_MISMATCH",
        },
        {
            "id": "N47-clarify-concept-not-bound",
            "validation": "boundary-mapping",
            "case": {"candidate_status": "CLARIFY", "boundary_code": "CONCEPT_NOT_BOUND", "query_engine_access_count": 0, "well_formed_term": True, "known_semantic_area": True, "allowed_alias_binding_count": 0, "role_authorized": True},
            "expected_error": "BOUNDARY_MAPPING_INVALID",
        },
        {
            "id": "N48-role-denial-mislabeled-concept",
            "validation": "boundary-mapping",
            "case": {"candidate_status": "REFUSED", "boundary_code": "CONCEPT_NOT_BOUND", "query_engine_access_count": 0, "well_formed_term": True, "known_semantic_area": True, "allowed_alias_binding_count": 1, "role_authorized": False},
            "expected_error": "BOUNDARY_MAPPING_INVALID",
        },
        {
            "id": "N49-concept-boundary-queried",
            "validation": "boundary-mapping",
            "case": {"candidate_status": "REFUSED", "boundary_code": "CONCEPT_NOT_BOUND", "query_engine_access_count": 1, "well_formed_term": True, "known_semantic_area": True, "allowed_alias_binding_count": 0, "role_authorized": True},
            "expected_error": "BOUNDARY_MAPPING_INVALID",
        },
        {
            "id": "N50-feedback-cannot-replace-outcome",
            "validation": "feedback-isolation",
            "case": {"persisted_outcome": "REFUSED", "feedback_state": "CREATED", "reported_outcome": "SCR_CREATED", "scr_count": 1},
            "expected_error": "ANALYTIC_OUTCOME_MUTATED",
        },
        {
            "id": "N51-disclosure-deny-cannot-create-scr",
            "validation": "feedback-isolation",
            "case": {"persisted_outcome": "REFUSED", "feedback_state": "DISCLOSURE_DENIED", "reported_outcome": "REFUSED", "scr_count": 1},
            "expected_error": "DISCLOSURE_BLOCKED",
        },
        {
            "id": "N52-outbox-failure-cannot-change-outcome",
            "validation": "feedback-isolation",
            "case": {"persisted_outcome": "REFUSED", "feedback_state": "OUTBOX_FAILED", "reported_outcome": "FAILED_EXECUTION", "scr_count": 0},
            "expected_error": "ANALYTIC_OUTCOME_MUTATED",
        },
    ]


def logical_transaction_traces() -> list[dict[str, Any]]:
    """Fixed logical traces whose keys and predicates are derived from typed state."""

    def logical_ref(object_type: str, schema: str, object_id: str, version: str) -> dict[str, Any]:
        return {
            "object_type": object_type,
            "object_id": object_id,
            "object_version": version,
            "contract_version": v0.CONTRACT,
            "subject_schema": schema,
            "canonicalization_profile": v0.PROFILE,
            "scope": v0.scope("governance"),
            "subject_digest": v0.fake_digest(f"logical.{schema}.{object_id}.{version}"),
        }

    def bind_logical_ref(
        ref_value: dict[str, Any], domain: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        result = copy.deepcopy(ref_value)
        result["subject_digest"] = domain_digest(
            domain,
            {
                "identity": {
                    key: copy.deepcopy(value)
                    for key, value in result.items()
                    if key != "subject_digest"
                },
                "body": copy.deepcopy(body),
            },
        )
        return result

    candidate_public = logical_ref(
        "reference-candidate", "reference-candidate-subject/1", "logical.candidate.public", "1.0.0"
    )
    candidate_synthetic = logical_ref(
        "reference-candidate", "reference-candidate-subject/1", "logical.candidate.synthetic", "1.0.0"
    )
    candidate_outsider = logical_ref(
        "reference-candidate", "reference-candidate-subject/1", "logical.candidate.outsider", "1.0.0"
    )
    suite = logical_ref("suite-manifest", "suite-manifest-subject/1", "adt.tracer.v1.suite", "1.0.0")

    def policy(label: str) -> dict[str, Any]:
        return logical_ref("static-policy-leaf", "static-policy-leaf/1", f"logical.policy.{label}", "1.0.0")

    policy_a, policy_b, policy_c, policy_d = (policy(label) for label in "abcd")

    def candidate_set(label: str, version: str, policy_ref: dict[str, Any], *, series: str = "adt") -> dict[str, Any]:
        state = {
            "ref": logical_ref(
                "reference-candidate-set",
                "reference-candidate-set-subject/1",
                f"logical.reference-set.{series}",
                version,
            ),
            "candidate_refs": v0.sorted_set([candidate_public, candidate_synthetic]),
            "shared_suite_manifest_ref": suite,
            "selection_policy_ref": copy.deepcopy(policy_ref),
        }
        state["ref"] = bind_logical_ref(
            state["ref"],
            "spc-logical-candidate-set-v1",
            {key: value for key, value in state.items() if key != "ref"},
        )
        return state

    set_a = candidate_set("a", "1.0.0", policy_a)
    set_b = candidate_set("b", "1.1.0", policy_b)
    set_c = candidate_set("c", "1.2.0", policy_c)
    set_d = candidate_set("d", "1.3.0", policy_d)
    set_same_material = candidate_set("same", "1.0.1", policy_a)
    set_z = candidate_set("z", "1.0.0", policy_a, series="other")

    def bundle(
        label: str,
        state: dict[str, Any],
        selected_ref: dict[str, Any],
        transition: dict[str, Any] | None = None,
        crash_cut: str | None = None,
    ) -> dict[str, Any]:
        proposal_ref = logical_ref(
            "reference-selection-proposal",
            "reference-selection-proposal-subject/1",
            f"logical.proposal.{label}",
            "1.0.0",
        )
        proposal_body = {
            "candidate_set_ref": copy.deepcopy(state["ref"]),
            "selected_candidate_ref": copy.deepcopy(selected_ref),
            "reselection_transition": copy.deepcopy(transition),
        }
        proposal_ref = bind_logical_ref(
            proposal_ref, "spc-logical-selection-proposal-v1", proposal_body
        )
        decision_ref = logical_ref(
            "reference-selection-authority-decision",
            "reference-selection-authority-decision-subject/1",
            f"logical.decision.{label}",
            "1.0.0",
        )
        decision_body = {
            "action": "SELECT_REFERENCE",
            "purpose": "ontology-build",
            "decision": "ALLOW",
            "trust_epoch": 11,
            "proposed_action_subject_ref": proposal_ref,
            "policy_snapshot_ref": copy.deepcopy(state["selection_policy_ref"]),
        }
        decision_ref = bind_logical_ref(
            decision_ref, "spc-logical-selection-decision-v1", decision_body
        )
        manifest_ref = logical_ref(
            "reference-manifest",
            "reference-manifest-subject/2",
            f"logical.manifest.{label}",
            "1.0.0",
        )
        manifest_body = {
            "selection_proposal_ref": proposal_ref,
            "selection_authority_decision_ref": decision_ref,
            "selected_candidate_ref": copy.deepcopy(selected_ref),
        }
        manifest_ref = bind_logical_ref(
            manifest_ref, "spc-logical-reference-manifest-v1", manifest_body
        )
        return {
            "op": "COMMAND",
            "command_id": label,
            "candidate_set": copy.deepcopy(state),
            "proposal": {
                "ref": proposal_ref,
                **proposal_body,
            },
            "authority_decision": {
                "ref": decision_ref,
                **decision_body,
            },
            "reference_manifest": {
                "ref": manifest_ref,
                **manifest_body,
            },
            "crash_cut": crash_cut,
        }

    def request_digest(command: dict[str, Any]) -> str:
        return domain_digest(
            "spc-logical-selection-request-v1",
            {
                "candidate_set_ref": command["candidate_set"]["ref"],
                "selection_proposal_ref": command["proposal"]["ref"],
                "selection_authority_decision_ref": command["authority_decision"]["ref"],
                "reference_manifest_ref": command["reference_manifest"]["ref"],
            },
        )

    def receipt_id(command: dict[str, Any]) -> str:
        return "receipt-" + request_digest(command).removeprefix("sha-256:")[:16]

    def series_key(state: dict[str, Any]) -> str:
        return v0.canonical(
            {
                "scope": state["ref"]["scope"],
                "candidate_set_object_id": state["ref"]["object_id"],
            }
        )

    first = bundle("a", set_a, candidate_synthetic)
    rival = bundle("b", set_a, candidate_public)
    first_receipt = receipt_id(first)

    def transition(
        predecessor_set: dict[str, Any], predecessor_receipt_id: str, changed_refs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "predecessor_candidate_set_ref": copy.deepcopy(predecessor_set["ref"]),
            "predecessor_receipt_id": predecessor_receipt_id,
            "changed_component_refs": v0.sorted_set(changed_refs),
        }

    legal_successor = bundle(
        "successor-a",
        set_b,
        candidate_synthetic,
        transition(set_a, first_receipt, [policy_b]),
    )
    legal_receipt = receipt_id(legal_successor)
    fork_successor = bundle(
        "successor-b",
        set_c,
        candidate_synthetic,
        transition(set_a, first_receipt, [policy_c]),
    )
    same_material = bundle(
        "version-only",
        set_same_material,
        candidate_synthetic,
        transition(set_a, first_receipt, [policy_a]),
    )
    stale_successor = bundle(
        "stale",
        set_d,
        candidate_synthetic,
        transition(set_a, first_receipt, [policy_d]),
    )
    invalid_first = copy.deepcopy(first)
    invalid_first["command_id"] = "invalid-first"
    invalid_first["proposal"]["selected_candidate_ref"] = candidate_outsider
    invalid_first["reference_manifest"]["selected_candidate_ref"] = candidate_outsider
    independent = bundle("new-series", set_z, candidate_synthetic)
    independent_receipt = receipt_id(independent)

    def retry(command: dict[str, Any], label: str, crash_cut: str | None = None) -> dict[str, Any]:
        result = copy.deepcopy(command)
        result["command_id"] = label
        result["crash_cut"] = crash_cut
        return result

    healthy = "HEALTHY"
    traces = [
        {"id": "T01-exact-retry-before-expiry", "steps": [first, retry(first, "a-retry")], "expected_results": [f"COMMITTED:{first_receipt}", f"RETRY:{first_receipt}"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T02-exact-retry-after-expiry", "steps": [first, {"op": "SET_AUTHORITY_STATE", "outcome": "DENY"}, retry(first, "a-retry-expired")], "expected_results": [f"COMMITTED:{first_receipt}", f"RETRY:{first_receipt}"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T03-conflict-a-then-b", "steps": [first, rival], "expected_results": [f"COMMITTED:{first_receipt}", "REFERENCE_SELECTION_CONFLICT"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T04-conflict-b-then-a", "steps": [rival, first], "expected_results": [f"COMMITTED:{receipt_id(rival)}", "REFERENCE_SELECTION_CONFLICT"], "expected_durable_receipts": [receipt_id(rival)], "expected_series_head": receipt_id(rival), "expected_store_state": healthy},
        {"id": "T05-invalid-first-does-not-reserve", "steps": [invalid_first, first], "expected_results": ["INVALID_COMMAND", f"COMMITTED:{first_receipt}"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T06-authority-expires-while-waiting", "steps": [{"op": "SET_AUTHORITY_STATE", "outcome": "DENY"}, first], "expected_results": ["AUTHORITY_DENIED_OR_STALE"], "expected_durable_receipts": [], "expected_series_head": None, "expected_store_state": healthy},
        {"id": "T07-legal-material-successor", "steps": [first, legal_successor], "expected_results": [f"COMMITTED:{first_receipt}", f"COMMITTED:{legal_receipt}"], "expected_durable_receipts": [first_receipt, legal_receipt], "expected_series_head": legal_receipt, "expected_store_state": healthy},
        {"id": "T08-version-time-only-successor", "steps": [first, same_material], "expected_results": [f"COMMITTED:{first_receipt}", "MATERIAL_CHANGE_REQUIRED"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T09-forked-successors", "steps": [first, legal_successor, fork_successor], "expected_results": [f"COMMITTED:{first_receipt}", f"COMMITTED:{legal_receipt}", "STALE_PREDECESSOR"], "expected_durable_receipts": [first_receipt, legal_receipt], "expected_series_head": legal_receipt, "expected_store_state": healthy},
        {"id": "T10-stale-predecessor", "steps": [first, legal_successor, stale_successor], "expected_results": [f"COMMITTED:{first_receipt}", f"COMMITTED:{legal_receipt}", "STALE_PREDECESSOR"], "expected_durable_receipts": [first_receipt, legal_receipt], "expected_series_head": legal_receipt, "expected_store_state": healthy},
        {"id": "T11-crash-before-append", "steps": [retry(first, "crash-before", "BEFORE_APPEND"), {"op": "RESTART"}], "expected_results": ["CRASH_NO_COMMIT", "RECOVERED"], "expected_durable_receipts": [], "expected_series_head": None, "expected_store_state": healthy},
        {"id": "T12-crash-mid-frame", "steps": [retry(first, "crash-mid", "MID_FRAME"), {"op": "RESTART"}], "expected_results": ["CRASH_CORRUPT_TAIL", "JOURNAL_CORRUPT_OR_NOT_DURABLE"], "expected_durable_receipts": [], "expected_series_head": None, "expected_store_state": "CORRUPT_FAIL_CLOSED"},
        {"id": "T13-crash-after-write-before-sync", "steps": [retry(first, "crash-pre-sync", "AFTER_WRITE_PRE_SYNC"), {"op": "RESTART"}], "expected_results": ["CRASH_NO_COMMIT", "RECOVERED"], "expected_durable_receipts": [], "expected_series_head": None, "expected_store_state": healthy},
        {"id": "T14-crash-after-sync-before-response", "steps": [retry(first, "crash-post-sync", "AFTER_SYNC_PRE_RESPONSE"), {"op": "RESTART"}, {"op": "SET_AUTHORITY_STATE", "outcome": "DENY"}, retry(first, "a-after-crash")], "expected_results": ["CRASH_AFTER_COMMIT", "RECOVERED", f"RETRY:{first_receipt}"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
        {"id": "T15-new-independent-series", "steps": [first, independent], "expected_results": [f"COMMITTED:{first_receipt}", f"COMMITTED:{independent_receipt}"], "expected_durable_receipts": [first_receipt, independent_receipt], "expected_series_head": {series_key(set_a): first_receipt, series_key(set_z): independent_receipt}, "expected_store_state": healthy},
        {"id": "T16-retry-read-denied-no-existence-leak", "steps": [first, {"op": "SET_READ_AUTHORIZATION", "allowed": False}, retry(first, "a-read-denied")], "expected_results": [f"COMMITTED:{first_receipt}", "READ_DENIED"], "expected_durable_receipts": [first_receipt], "expected_series_head": first_receipt, "expected_store_state": healthy},
    ]
    return traces


def build_schema_mutation_matrix(positive: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contract = json.loads(CONFORMANCE_MANIFEST.read_text(encoding="utf-8"))
    schemas = contract["schema_contract"]["schemas"]
    sample_by_schema: dict[str, str] = {}
    for vector in positive:
        sample_by_schema.setdefault(vector["subject_schema"], vector["id"])
    missing = set(schemas) - set(sample_by_schema)
    if missing:
        raise ValueError(f"schemas without positive samples: {sorted(missing)}")
    matrix: list[dict[str, Any]] = []

    def add(schema_id: str, field: str, operation: str) -> None:
        matrix.append(
            {
                "id": f"M-{len(matrix) + 1:04d}-{schema_id.replace('/', '-')}-{field}-{operation}",
                "positive_id": sample_by_schema[schema_id],
                "subject_schema": schema_id,
                "field": field,
                "operation": operation,
                "must_reject": True,
            }
        )

    def unwrap(spec: dict[str, Any]) -> dict[str, Any]:
        return spec["item"] if spec["kind"] == "nullable" else spec

    def contains_kind(spec: dict[str, Any], wanted: str) -> bool:
        spec = unwrap(spec)
        if spec["kind"] == wanted:
            return True
        if spec["kind"] in {"set", "ordered"}:
            return contains_kind(spec["item"], wanted)
        if wanted == "full_ref" and spec["kind"] == "closed_ref_map":
            return True
        return False

    def contains_enum(spec: dict[str, Any]) -> bool:
        spec = unwrap(spec)
        if spec.get("enum"):
            return True
        if spec["kind"] in {"set", "ordered"}:
            return contains_enum(spec["item"])
        return False

    for schema_id, definition in schemas.items():
        for field, raw_spec in definition["fields"].items():
            spec = unwrap(raw_spec)
            add(schema_id, field, "remove")
            add(schema_id, field, "wrong_type")
            if contains_enum(raw_spec):
                add(schema_id, field, "unknown_enum")
            if contains_kind(raw_spec, "full_ref"):
                add(schema_id, field, "invalid_ref_target")
            if spec["kind"] == "set":
                add(schema_id, field, "noncanonical_set")
            if spec["kind"] == "timestamp":
                add(schema_id, field, "malformed_timestamp")
            if spec["kind"] == "version":
                add(schema_id, field, "nonascii_version")
            if spec["kind"] == "identifier":
                add(schema_id, field, "invalid_identifier")
            if spec["kind"] == "scope":
                add(schema_id, field, "wildcard_scope")
            if spec["kind"] == "opaque_locator":
                add(schema_id, field, "locator_path_injection")
            if spec["kind"] in {"closed_integer_map", "closed_ref_map"}:
                add(schema_id, field, "remove_map_key")
            if spec["kind"] == "decimal_value":
                add(schema_id, field, "invalid_decimal")
    return matrix


def build_integrated_mutations(graph: Graph, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Fixed graph mutations.  The verifier rehashes the complete dependent DAG."""

    mutations: list[dict[str, Any]] = []

    def add(
        mutation_id: str,
        category: str,
        record_key: str,
        path: list[str],
        value: Any = None,
        operation: str = "set",
    ) -> None:
        mutations.append(
            {
                "id": mutation_id,
                "category": category,
                "record_key": record_key,
                "path": path,
                "operation": operation,
                "value": copy.deepcopy(value),
                "must_fail_closed": True,
            }
        )

    add(
        "G01-forged-session-digest",
        "TRUST_ROOT",
        "selection_authority",
        ["trusted_session_ref", "subject_digest"],
        v0.fake_digest("forged-session"),
    )
    add(
        "G02-session-principal-substitution",
        "TRUST_ROOT",
        "selection_authority",
        ["trusted_session_ref"],
        artifact("session.disclosure-approver"),
    )
    add(
        "G03-role-assignment-substitution",
        "TRUST_ROOT",
        "selection_authority",
        ["role_assignment_ref"],
        artifact("role-assignment.disclosure-approver.disclosure-approver"),
    )
    add(
        "G04-selection-policy-substitution",
        "TRUST_ROOT",
        "selection_authority",
        ["policy_refs"],
        [artifact("authority-policy.local")],
    )
    add(
        "G05-selection-trust-epoch",
        "TRUST_ROOT",
        "selection_authority",
        ["trust_epoch"],
        12,
    )

    gate_keys = ["semantic", "binding", "disclosure", "runtime", "control"]
    for index, gate_key in enumerate(gate_keys, start=1):
        add(
            f"G1{index}-gate-{gate_key}-fail",
            "FIVE_GATE",
            f"{gate_key}_evaluation",
            ["outcome"],
            "FAIL",
        )
        add(
            f"G2{index}-attest-{gate_key}-deny",
            "FIVE_GATE",
            f"{gate_key}_attest_authority",
            ["decision"],
            "DENY",
        )
        add(
            f"G3{index}-gate-{gate_key}-expired",
            "FIVE_GATE",
            f"{gate_key}_evaluation",
            ["expires_at"],
            "2026-08-19T00:03:59.999Z",
        )
        add(
            f"G3{index + 5}-gate-{gate_key}-future-issued",
            "FIVE_GATE",
            f"{gate_key}_evaluation",
            ["issued_at"],
            "2026-08-19T00:04:00.001Z",
        )
    add(
        "G40-attest-wrong-resource",
        "FIVE_GATE",
        "binding_attest_authority",
        ["proposed_action_subject_ref"],
        graph.ref("disclosure_evaluation"),
    )
    add(
        "G41-gate-wrong-type",
        "FIVE_GATE",
        "binding_evaluation",
        ["gate_type"],
        "DISCLOSURE_POLICY_CLEARANCE",
    )
    add(
        "G42-gate-limitation-incompatible",
        "FIVE_GATE",
        "binding_evaluation",
        ["limitations"],
        ["local-authority", "public-style-synthetic", "synthetic-data"],
    )
    add(
        "G43-seal-deny",
        "SEAL",
        "seal_authority",
        ["decision"],
        "DENY",
    )
    add(
        "G44-seal-omit-attempt",
        "SEAL",
        "seal_proposal",
        ["verification_attempt_refs_by_gate", "SEMANTIC_APPROVAL"],
        operation="remove",
    )

    add("G50-concept-not-well-formed", "E01", "concept_resolution_evidence", ["term_well_formed"], False)
    add("G51-concept-resolution-incomplete", "E01", "concept_resolution_evidence", ["resolution_completed"], False)
    add("G52-concept-binding-nonzero", "E01", "concept_resolution_evidence", ["binding_count"], 1)
    add("G53-concept-query-access", "E01", "concept_resolution_evidence", ["query_engine_access_count"], 1)
    add("G54-policy-deny-mislabeled-concept", "E01", "prequery_policy", ["decision"], "DENY")
    add(
        "G55-concept-evidence-ref-omitted",
        "E01",
        "concept_evidence",
        ["concept_resolution_evidence_ref"],
        None,
    )
    add(
        "G56-unreleased-boundary-substitution",
        "E01",
        "scr_payload",
        ["boundary_release_commit_ref"],
        context["release_commit_ref"],
    )
    add(
        "G57-safe-alias-substitution",
        "E01",
        "scr_payload",
        ["safe_term_alias_ref"],
        artifact("safe-term.unrelated"),
    )
    add(
        "G58-raw-question-field",
        "E01",
        "scr_payload",
        ["raw_question"],
        "restricted question",
        operation="add",
    )
    add("G59-disclosure-evaluation-deny", "E01", "scr_disclosure_evaluation", ["decision"], "DENY")
    add("G60-disclosure-authority-deny", "E01", "scr_disclosure_authority", ["decision"], "DENY")
    add("G61-enqueue-authority-deny", "E01", "scr_enqueue_authority", ["decision"], "DENY")
    add(
        "G62-boundary-execution-answer-substitution",
        "E01",
        "scr_payload",
        ["boundary_execution_ref"],
        graph.ref("answer_evidence"),
    )

    add(
        "G70-gsr-unselected-manifest",
        "SELECTED_LINEAGE",
        "gsr_publish",
        ["selected_reference_manifest_ref"],
        context["unselected_reference_manifest_ref"],
    )
    add(
        "G71-receipt-unselected-manifest",
        "SELECTED_LINEAGE",
        "selection_receipt",
        ["reference_manifest_ref"],
        context["unselected_reference_manifest_ref"],
    )
    add(
        "G72-gsr-unselected-semantic-content",
        "SELECTED_LINEAGE",
        "gsr_publish",
        ["semantic_content_ref"],
        context["unselected_semantic_content_ref"],
    )
    add(
        "G73-gsr-unselected-input",
        "SELECTED_LINEAGE",
        "gsr_publish",
        ["cleared_input_refs"],
        [context["unselected_input_ref"]],
    )
    add(
        "G74-gsr-unselected-decision",
        "SELECTED_LINEAGE",
        "gsr_publish",
        ["decision_refs"],
        [context["unselected_selection_authority_ref"]],
    )
    add(
        "G75-payload-unselected-manifest",
        "SELECTED_LINEAGE",
        "runtime_payload",
        ["reference_manifest_ref"],
        context["unselected_reference_manifest_ref"],
    )
    add(
        "G76-payload-unselected-control",
        "SELECTED_LINEAGE",
        "runtime_payload",
        ["control_manifest_ref"],
        context["unselected_control_ref"],
    )
    add(
        "G77-payload-unselected-oracle",
        "SELECTED_LINEAGE",
        "runtime_payload",
        ["oracle_provenance_ref"],
        context["unselected_oracle_ref"],
    )
    add(
        "G78-control-gate-unselected-manifest",
        "SELECTED_LINEAGE",
        "control_gate_subject",
        ["reference_manifest_ref"],
        context["unselected_reference_manifest_ref"],
    )
    add(
        "G79-control-gate-unselected-control",
        "SELECTED_LINEAGE",
        "control_gate_subject",
        ["control_manifest_ref"],
        context["unselected_control_ref"],
    )
    add(
        "G80-runtime-unselected-semantic-content",
        "SELECTED_LINEAGE",
        "runtime_gate_subject",
        ["gsr_semantic_content_ref"],
        context["unselected_semantic_content_ref"],
    )

    add("G90-gsr-relabel-v1", "COMPATIBILITY", "gsr_publish", ["subject_schema"], "gsr-publish-subject/1")
    add(
        "G91-reference-manifest-relabel-v1",
        "COMPATIBILITY",
        "reference_manifest",
        ["subject_schema"],
        "reference-manifest-subject/1",
    )
    add(
        "G92-execution-evidence-relabel-v1",
        "COMPATIBILITY",
        "concept_evidence",
        ["subject_schema"],
        "execution-evidence-subject/1",
    )
    add(
        "G93-scr-payload-relabel-v1",
        "COMPATIBILITY",
        "scr_payload",
        ["subject_schema"],
        "unknown-concept-payload-subject/1",
    )
    add(
        "G94-mixed-reference-manifest-ref",
        "COMPATIBILITY",
        "gsr_publish",
        ["selected_reference_manifest_ref", "subject_schema"],
        "reference-manifest-subject/1",
    )
    add(
        "G95-unknown-contract-version",
        "COMPATIBILITY",
        "gsr_publish",
        ["contract_version"],
        "shared-product-contract/latest",
    )
    add("G100-cleared-input-authority-deny", "AUTHORITY", "input_synthetic_authority", ["decision"], "DENY")
    add("G101-publish-authority-deny", "AUTHORITY", "publish_authority", ["decision"], "DENY")
    add("G102-selection-key-digest-forged", "RECEIPT", "selection_receipt", ["selection_key_digest"], v0.fake_digest("forged-selection-key"))
    add("G103-request-identity-digest-forged", "RECEIPT", "selection_receipt", ["request_identity_digest"], v0.fake_digest("forged-request-identity"))
    add("G104-journal-record-digest-forged", "RECEIPT", "selection_receipt", ["journal_record_digest"], v0.fake_digest("forged-journal-record"))
    add("G105-activation-wrong-attempt", "ELIGIBILITY", "activation_eligibility", ["verification_attempt_refs_by_gate", "SEMANTIC_APPROVAL"], graph.ref("binding_attempt"))
    add("G106-activation-future-evaluation", "ELIGIBILITY", "activation_eligibility", ["evaluated_at"], "2030-08-19T00:05:00.000Z")
    add("G107-release-eligibility-deny", "E01", "concept_release_eligibility", ["decision"], "DENY")
    add("G108-release-authority-deny", "E01", "concept_release_authority", ["decision"], "DENY")
    add("G109-release-policy-deny", "E01", "concept_release_policy", ["decision"], "DENY")
    add("G110-scr-enqueue-wrong-resource", "E01", "scr_enqueue_authority", ["proposed_action_subject_ref"], graph.ref("gsr_publish"))
    add("G111-payload-aux-oracle", "SELECTED_LINEAGE", "runtime_payload", ["oracle_provenance_ref"], context["aux_oracle_ref"])
    add("G112-control-gate-aux-oracle", "SELECTED_LINEAGE", "control_gate_subject", ["oracle_provenance_ref"], context["aux_oracle_ref"])
    add("G113-successor-false-changed-ref", "RECEIPT", "selection_transition", ["changed_component_refs"], [context["selected_candidate_ref"]])
    add("G114-successor-policy-alias", "RECEIPT", "candidate_set", ["selection_policy_ref"], artifact("selection-policy.adt.r01"))
    add("G115-cleared-input-authority-wrong-resource", "AUTHORITY", "input_synthetic_authority", ["proposed_action_subject_ref"], graph.ref("input_public_proposal"))
    add("G116-control-author-reviewer-collapse", "TRUTH", "control_synthetic", ["expected_value_author_ref"], artifact("principal.control-reviewer"))
    add("G117-oracle-author-reviewer-collapse", "TRUTH", "oracle_synthetic", ["author_ref"], artifact("principal.control-reviewer"))
    add("G118-selected-candidate-wrong-control", "TRUTH", "candidate_synthetic", ["control_manifest_ref"], context["unselected_control_ref"])
    add("G119-selected-proposal-nonmember", "TRUTH", "selection_proposal", ["selected_candidate_ref"], context["aux_candidate_ref"])
    add("G120-final-manifest-wrong-control", "TRUTH", "reference_manifest", ["control_manifest_ref"], context["unselected_control_ref"])
    add("G121-suite-denominator-drift", "TRUTH", "suite", ["denominator"], 9)
    add("G122-activation-policy-deny", "ELIGIBILITY", "activation_policy", ["decision"], "DENY")
    add("G123-prequery-authority-deny", "ELIGIBILITY", "prequery_authority", ["decision"], "DENY")
    add("G124-verification-attempt-wrong-authority", "FIVE_GATE", "binding_attempt", ["authority_decision_ref"], graph.ref("semantic_attest_authority"))
    add("G125-vrs-wrong-seal-authority", "SEAL", "vrs", ["seal_authority_decision_ref"], graph.ref("publish_authority"))
    add("G126-release-wrong-projection", "E01", "release_commit", ["user_projection_ref"], graph.ref("concept_projection"))
    add("G127-projection-execution-mismatch", "E01", "answer_projection", ["execution_id"], "exec.concept")
    add("G128-concept-policy-ref-substitution", "E01", "concept_resolution_evidence", ["policy_decision_ref"], graph.ref("release_policy"))
    add("G129-publish-wrong-purpose", "AUTHORITY", "publish_authority", ["purpose"], "ontology-build")
    add("G130-prequery-policy-wrong-resource", "ELIGIBILITY", "prequery_policy", ["resource_refs"], [context["selected_input_ref"]])
    add("G131-seal-attempt-alias", "SEAL", "seal_proposal", ["verification_attempt_refs_by_gate", "CONTROL_GOLDEN_EVALUATION"], graph.ref("binding_attempt"))
    add("G132-current-selection-wrong-decision", "RECEIPT", "reference_manifest", ["selection_authority_decision_ref"], context["predecessor_selection_authority_ref"])
    add("G133-candidate-set-denominator-drift", "TRUTH", "candidate_set", ["denominator"], 3)
    add("G134-disclosure-decision-wrong-authority", "E01", "scr_disclosure_decision", ["disclosure_authority_decision_ref"], graph.ref("scr_enqueue_authority"))
    add("G135-concept-evidence-status-mismatch", "E01", "concept_evidence", ["candidate_status"], "ANSWER_CANDIDATE")
    add("G136-binding-bundle-valid-substitution", "FIVE_GATE", "binding_gate_subject", ["binding_bundle_ref"], artifact("partition.q3", "runtime"))
    add("G137-disclosure-label-valid-substitution", "FIVE_GATE", "disclosure_gate_subject", ["gsr_disclosure_labels_ref"], artifact("binding-requirements.adt"))
    add("G138-runtime-capability-valid-substitution", "FIVE_GATE", "runtime_gate_subject", ["runtime_capability_manifest_ref"], artifact("runtime-build.adt", "runtime"))
    add("G139-gsr-aux-semantic-decision", "SELECTED_LINEAGE", "gsr_publish", ["decision_refs"], [context["semantic_decision_aux_ref"]])
    add(
        "G140-prequery-before-activation-commit",
        "ELIGIBILITY",
        "prequery_eligibility",
        ["evaluated_at"],
        "2026-08-19T00:04:30.000Z",
    )
    add(
        "G141-activation-commit-before-request",
        "ELIGIBILITY",
        "activation_intent",
        ["requested_at"],
        "2026-08-19T00:05:00.001Z",
    )
    add(
        "G142-prequery-cross-environment",
        "ELIGIBILITY",
        "prequery_eligibility",
        ["scope", "environment_id"],
        "other-environment",
    )
    add(
        "G143-release-eligibility-before-evidence",
        "E01",
        "release_eligibility",
        ["evaluated_at"],
        "2026-08-19T00:10:00.500Z",
    )
    add(
        "G144-release-commit-sequence-drift",
        "E01",
        "release_commit",
        ["commit_sequence"],
        2,
    )
    add(
        "G145-predecessor-proposal-nonmember",
        "RECEIPT",
        "selection_proposal_predecessor",
        ["selected_candidate_ref"],
        context["aux_candidate_ref"],
    )
    add(
        "G146-predecessor-manifest-wrong-control",
        "RECEIPT",
        "reference_manifest_predecessor",
        ["control_manifest_ref"],
        context["unselected_control_ref"],
    )
    add(
        "G147-initial-proposal-carries-transition",
        "RECEIPT",
        "selection_proposal_predecessor",
        ["reselection_transition_ref"],
        context["selection_transition_ref"],
    )
    add(
        "G148-cleared-input-locator-classification-drift",
        "TRUTH",
        "input_synthetic_proposal",
        ["opaque_source_locator_ref", "classification"],
        "INTERNAL",
    )
    add(
        "G149-disclosure-allowlist-omission",
        "E01",
        "scr_disclosure_evaluation",
        ["allowed_fields"],
        ["reason_code", "safe_detail_artifact_ref", "semantic_area_code"],
    )
    add(
        "G150-disclosure-no-raw-obligation-omitted",
        "E01",
        "scr_disclosure_evaluation",
        ["obligations"],
        ["REAUTHORIZE_REFS"],
    )
    add(
        "G151-disclosure-classification-drift",
        "E01",
        "scr_disclosure_evaluation",
        ["classification"],
        "INTERNAL",
    )
    add(
        "G152-enqueue-no-raw-limitation-omitted",
        "E01",
        "scr_enqueue_proposal",
        ["limitations"],
        ["synthetic-scope"],
    )
    add(
        "G153-selection-authority-before-set-freeze",
        "RECEIPT",
        "selection_authority",
        ["issued_at"],
        "2026-08-19T00:00:00.599Z",
    )
    add(
        "G154-gate-before-selection-commit",
        "FIVE_GATE",
        "semantic_evaluation",
        ["issued_at"],
        "2026-08-19T00:00:00.899Z",
    )
    add(
        "G155-data-frozen-after-gate",
        "FIVE_GATE",
        "data_identity",
        ["frozen_at"],
        "2026-08-19T00:02:00.001Z",
    )
    add(
        "G156-initial-activation-wrong-expected-epoch",
        "ELIGIBILITY",
        "activation_intent",
        ["expected_activation_epoch"],
        1,
    )
    add(
        "G157-semantic-content-before-selection-commit",
        "SELECTED_LINEAGE",
        "semantic_content",
        ["built_at"],
        "2026-08-19T00:00:00.899Z",
    )
    add(
        "G158-semantic-gate-before-content-build",
        "FIVE_GATE",
        "semantic_evaluation",
        ["issued_at"],
        "2026-08-19T00:00:00.999Z",
    )
    add(
        "G159-gsr-semantic-schema-substitution",
        "SELECTED_LINEAGE",
        "gsr_publish",
        ["semantic_schema_ref"],
        artifact("semantic-compiler-build.adt"),
    )
    return mutations


def main() -> None:
    EXTERNAL_ENTRIES.clear()
    graph, context = build_integrated_graph()
    positive = []
    for vector_id, subject in isolated_positive_subjects(graph, context):
        schema = subject["subject_schema"]
        canonical_json = v0.canonical(subject)
        _preimage, expected_digest = v0.digest(schema, canonical_json)
        positive.append(
            {
                "id": vector_id,
                "subject_schema": schema,
                "input_json": json.dumps(subject, ensure_ascii=False, separators=(",", ":")),
                "canonical_json": canonical_json,
                "subject_digest": expected_digest,
            }
        )

    negative = v0.negative_vectors() + semantic_negatives(context)
    schema_mutations = build_schema_mutation_matrix(positive)
    transaction_traces = logical_transaction_traces()
    integrated_mutations = build_integrated_mutations(graph, context)
    external_manifest = {
        "manifest_schema": EXTERNAL_MANIFEST_SCHEMA,
        "contract_version": v0.CONTRACT,
        "stage_profile_id": STAGE_PROFILE,
        "entries": sorted(EXTERNAL_ENTRIES.values(), key=lambda item: v0.canonical(item["ref"])),
        "entry_count": len(EXTERNAL_ENTRIES),
        "caller_supplied": False,
        "claim": "closed-relative-to-this-exact-pinned-manifest",
    }
    external_rendered = json.dumps(
        external_manifest, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    external_sha256 = hashlib.sha256(external_rendered.encode("utf-8")).hexdigest()
    conformance_sha256 = hashlib.sha256(CONFORMANCE_MANIFEST.read_bytes()).hexdigest()
    document = {
        "fixture_schema": FIXTURE_SCHEMA,
        "contract_version": v0.CONTRACT,
        "stage_profile_id": STAGE_PROFILE,
        "annex_profile_id": ANNEX_PROFILE,
        "canonicalization_profile": v0.PROFILE,
        "digest_algorithm": "sha-256",
        "domain_prefix_utf8": "spc-v0.1",
        "conformance_manifest": {
            "filename": CONFORMANCE_MANIFEST.name,
            "sha256": conformance_sha256,
        },
        "external_leaf_manifest": {
            "filename": "external-leaf-manifest-1.1.json",
            "sha256": external_sha256,
            "entry_count": len(EXTERNAL_ENTRIES),
        },
        "toolchain_provenance": {
            "predecessor_helper_filename": "generate_vectors.py",
            "predecessor_helper_sha256": PREDECESSOR_HELPER_SHA256,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "unicode_data_version": unicodedata.unidata_version,
        },
        "positive_count": len(positive),
        "negative_count": len(negative),
        "schema_mutation_count": len(schema_mutations),
        "integrated_mutation_count": len(integrated_mutations),
        "logical_transaction_trace_count": len(transaction_traces),
        "integrated_subject_count": len(graph.records),
        "integrated_assertion_count": 12,
        "positive": positive,
        "negative": negative,
        "schema_mutations": schema_mutations,
        "integrated_mutations": integrated_mutations,
        "logical_transaction_traces": transaction_traces,
        "integrated_graph": {
            "subjects": graph.records,
            "context": context,
        },
    }
    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if len(sys.argv) == 5 and sys.argv[1] == "--output" and sys.argv[3] == "--external-output":
        Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
        Path(sys.argv[4]).write_text(external_rendered, encoding="utf-8")
        return
    if len(sys.argv) != 1:
        raise SystemExit(
            "usage: generate_vectors_core_1_1.py "
            "[--output PATH --external-output PATH]"
        )
    print(rendered, end="")


if __name__ == "__main__":
    main()
