from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from ontology_semantica_worker.app import app


client = TestClient(app)


def _request() -> dict[str, object]:
    return {
        "contract": "semantica-construction-request/v1",
        "run_id": "construction-run." + "a" * 32,
        "workspace_id": "workspace.adt.reference",
        "source_set_digest": "b" * 64,
        "requirements": [],
        "metric_candidates": [],
        "canonical_context": {
            "entities": [
                {
                    "id": "entity.trade",
                    "name": {"en": "Trade", "zh": "成交"},
                    "definition": "A trade event.",
                },
                {
                    "id": "entity.instrument",
                    "name": {"en": "Instrument", "zh": "证券"},
                    "definition": "A listed instrument.",
                },
            ],
            "relationships": [
                {
                    "id": "relationship.trade.instrument",
                    "from_entity": "entity.trade",
                    "to_entity": "entity.instrument",
                    "predicate": "referencesInstrument",
                }
            ],
        },
    }


def test_worker_returns_closed_non_authoritative_semantica_proposals() -> None:
    response = client.post("/v1/proposals", json=_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"] == "semantica-construction-result/v1"
    assert payload["engine"] == "semantica"
    assert {item["candidate_type"] for item in payload["candidates"]} >= {
        "OBJECT",
        "LINK",
    }
    serialized = json.dumps(
        payload["candidates"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(serialized).hexdigest() == payload["raw_result_digest"]


def test_worker_rejects_empty_semantic_context_instead_of_reporting_success() -> None:
    request = _request()
    request["canonical_context"] = {"entities": [], "relationships": []}

    response = client.post("/v1/proposals", json=request)

    assert response.status_code == 422


def test_worker_uses_source_supported_builder_context_for_a_blank_solution() -> None:
    request = _request()
    request["canonical_context"] = {"entities": [], "relationships": []}
    request["proposed_context"] = {
        "entities": [
            {
                "id": "entity.service_request",
                "name": {"en": "Service Request", "zh": "服务请求"},
                "definition": "A request submitted for service.",
            }
        ],
        "relationships": [],
        "properties": [],
        "source_anchor_ids": ["evidence." + "1" * 32],
    }

    response = client.post("/v1/proposals", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"][0]["label"].replace(" ", "").casefold() == "servicerequest"
    assert payload["candidates"][0]["source_anchor_ids"] == [
        "evidence." + "1" * 32
    ]
