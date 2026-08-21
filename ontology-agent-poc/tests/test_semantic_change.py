from __future__ import annotations

import json

import pytest

from ontology_agent.semantic_change import (
    CreateSemanticChangeRequestV1,
    FileSemanticChangeRequestStore,
    SemanticChangeError,
    build_semantic_change_request,
)


def _execution(snapshot: str) -> dict[str, object]:
    return {
        "status": "ANSWERED",
        "execution_id": "exec." + "a" * 32,
        "snapshot_checksum": snapshot,
        "plan": {"question": "Why did the metric change?"},
        "evidence": [
            {"claim_id": "claim.metric.delta"},
            {"claim_id": "claim.metric.limit"},
        ],
    }


def _request(snapshot: str) -> CreateSemanticChangeRequestV1:
    return CreateSemanticChangeRequestV1(
        execution_id="exec." + "a" * 32,
        snapshot_checksum=snapshot,
        request_type="MISSING_RELATIONSHIP",
        title="Instrument relationship is missing",
        observation="The answer cannot traverse from a trade to its instrument class.",
        proposed_change="Review a governed Trade-to-Instrument relationship.",
        claim_refs=("claim.metric.delta",),
    )


def test_request_is_bound_to_active_execution_evidence_and_persists_immutably(
    tmp_path,
) -> None:
    snapshot = "b" * 64
    request = build_semantic_change_request(
        solution_id="ontology.exchange_analytics.adt",
        environment_id="adt-poc",
        active_snapshot_checksum=snapshot,
        request=_request(snapshot),
        execution=_execution(snapshot),
    )
    store = FileSemanticChangeRequestStore(tmp_path / "scr")

    stored = store.append(request)

    assert stored.status == "PROPOSED_UNTRIAGED"
    assert store.list(request.solution_id) == (request,)
    assert store.append(request) == request


def test_request_rejects_unknown_claim_or_stale_snapshot() -> None:
    snapshot = "b" * 64
    unknown_claim = _request(snapshot).model_copy(
        update={"claim_refs": ("claim.unknown",)}
    )
    with pytest.raises(SemanticChangeError, match="unknown execution claims"):
        build_semantic_change_request(
            solution_id="ontology.exchange_analytics.adt",
            environment_id="adt-poc",
            active_snapshot_checksum=snapshot,
            request=unknown_claim,
            execution=_execution(snapshot),
        )
    with pytest.raises(SemanticChangeError, match="active snapshot"):
        build_semantic_change_request(
            solution_id="ontology.exchange_analytics.adt",
            environment_id="adt-poc",
            active_snapshot_checksum="c" * 64,
            request=_request(snapshot),
            execution=_execution(snapshot),
        )


def test_tampered_inbox_fails_closed(tmp_path) -> None:
    snapshot = "b" * 64
    request = build_semantic_change_request(
        solution_id="ontology.exchange_analytics.adt",
        environment_id="adt-poc",
        active_snapshot_checksum=snapshot,
        request=_request(snapshot),
        execution=_execution(snapshot),
    )
    store = FileSemanticChangeRequestStore(tmp_path / "scr")
    store.append(request)
    path = next((tmp_path / "scr" / request.solution_id).glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["title"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SemanticChangeError, match="digest mismatch"):
        store.list(request.solution_id)
