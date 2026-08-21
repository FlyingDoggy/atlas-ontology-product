from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


SEMANTICA_COMMIT = os.environ.get(
    "SEMANTICA_BUILD_REF", "c5d382ee81edc0727d07907c932970c762ec33bd"
)


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposalRequest(ClosedModel):
    contract: Literal["semantica-construction-request/v1"]
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    workspace_id: str = Field(min_length=1, max_length=255)
    source_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requirements: tuple[dict[str, Any], ...]
    metric_candidates: tuple[dict[str, Any], ...]
    canonical_context: dict[str, Any]
    proposed_context: dict[str, Any] | None = None


class WorkerCandidate(ClosedModel):
    occurrence_id: str = Field(min_length=1, max_length=500)
    candidate_type: Literal["OBJECT", "LINK", "PROPERTY"]
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=500)
    predicate: str | None = Field(default=None, max_length=500)
    object: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)
    source_anchor_ids: tuple[str, ...] = ()


class ProposalResponse(ClosedModel):
    contract: Literal["semantica-construction-result/v1"] = (
        "semantica-construction-result/v1"
    )
    engine: Literal["semantica"] = "semantica"
    build_ref: str
    candidates: tuple[WorkerCandidate, ...]
    raw_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _source_anchor_ids(request: ProposalRequest) -> tuple[str, ...]:
    values: set[str] = set()
    for row in (*request.requirements, *request.metric_candidates):
        anchor = row.get("source_anchor")
        if isinstance(anchor, dict) and anchor.get("snippet_checksum"):
            values.add(str(anchor["snippet_checksum"]))
    if request.proposed_context is not None:
        proposed = request.proposed_context.get("source_anchor_ids", ())
        if isinstance(proposed, list):
            values.update(str(item) for item in proposed if item)
    return tuple(sorted(values))


def build_proposal(request: ProposalRequest) -> ProposalResponse:
    # The import remains inside the worker call so Studio API never imports the
    # Semantica dependency tree. Semantica receives only product-selected,
    # structured context—not a bucket path or workspace filesystem.
    from semantica.ontology.ontology_generator import OntologyGenerator

    context = (
        request.proposed_context
        if request.proposed_context is not None
        else request.canonical_context
    )
    entities = context.get("entities", [])
    relationships = context.get("relationships", [])
    if not isinstance(entities, list) or not isinstance(relationships, list):
        raise ValueError("construction context must contain entity and relationship lists")
    semantica_entities = [
        {
            "id": item.get("id"),
            "name": (item.get("name") or {}).get("en") or item.get("id"),
            "type": ((item.get("name") or {}).get("en") or item.get("id") or "Thing").replace(" ", ""),
            "definition": item.get("definition", ""),
        }
        for item in entities
        if isinstance(item, dict) and item.get("id")
    ]
    semantica_relationships = [
        {
            "type": item.get("predicate"),
            "source": item.get("from_entity"),
            "target": item.get("to_entity"),
        }
        for item in relationships
        if isinstance(item, dict)
        and item.get("predicate")
        and item.get("from_entity")
        and item.get("to_entity")
    ]
    ontology = OntologyGenerator(
        base_uri="https://ontology.local/proposal/",
        min_occurrences=1,
    ).generate_ontology(
        {"entities": semantica_entities, "relationships": semantica_relationships},
        name="StudioConstructionProposal",
        validate=False,
    )
    anchors = _source_anchor_ids(request)
    candidates: list[WorkerCandidate] = []
    for index, item in enumerate(ontology.get("classes", []), start=1):
        label = str(item.get("label") or item.get("name") or "Unnamed class")
        candidates.append(
            WorkerCandidate(
                occurrence_id=f"class:{index}:{label}",
                candidate_type="OBJECT",
                label=label,
                definition=str(item.get("comment") or f"Semantica class proposal for {label}."),
                confidence=0.5,
                source_anchor_ids=anchors,
            )
        )
    by_predicate = {
        str(item.get("predicate")): item
        for item in relationships
        if isinstance(item, dict) and item.get("predicate")
    }
    for index, item in enumerate(ontology.get("properties", []), start=1):
        label = str(item.get("label") or item.get("name") or "Unnamed property")
        relation = by_predicate.get(str(item.get("name")))
        if relation is not None:
            candidates.append(
                WorkerCandidate(
                    occurrence_id=f"link:{index}:{label}",
                    candidate_type="LINK",
                    label=label,
                    definition=str(item.get("comment") or f"Semantica link proposal for {label}."),
                    subject=str(relation.get("from_entity")),
                    predicate=str(relation.get("predicate")),
                    object=str(relation.get("to_entity")),
                    confidence=0.5,
                    source_anchor_ids=anchors,
                )
            )
    serialized = [item.model_dump(mode="json") for item in candidates]
    return ProposalResponse(
        build_ref=SEMANTICA_COMMIT,
        candidates=tuple(candidates),
        raw_result_digest=_digest(serialized),
    )


app = FastAPI(
    title="Ontology Studio Semantica Proposal Worker",
    version="0.1.0",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "engine": "semantica", "build_ref": SEMANTICA_COMMIT}


@app.post("/v1/proposals", response_model=ProposalResponse)
def proposals(request: ProposalRequest) -> ProposalResponse:
    try:
        result = build_proposal(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Semantica proposal failed") from exc
    if not result.candidates:
        raise HTTPException(status_code=422, detail="Semantica returned no candidates")
    return result
