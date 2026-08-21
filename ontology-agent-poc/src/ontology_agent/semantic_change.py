from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .contracts import Sha256
from .io import sha256_value, write_json
from .models import StrictModel

SemanticChangeRequestType = Literal[
    "MISSING_CONCEPT",
    "WRONG_DEFINITION",
    "MISSING_RELATIONSHIP",
    "METRIC_LOGIC",
    "DATA_BINDING",
    "ANALYSIS_CAPABILITY",
    "OTHER",
]


class SemanticChangeError(RuntimeError):
    pass


class CreateSemanticChangeRequestV1(StrictModel):
    contract: Literal["semantic-change-request-create/v1"] = (
        "semantic-change-request-create/v1"
    )
    execution_id: str = Field(pattern=r"^exec\.[0-9a-f]{32}$")
    snapshot_checksum: Sha256
    request_type: SemanticChangeRequestType
    title: str = Field(min_length=3, max_length=200)
    observation: str = Field(min_length=3, max_length=2_000)
    proposed_change: str = Field(min_length=3, max_length=2_000)
    claim_refs: tuple[str, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_claim_refs(self) -> CreateSemanticChangeRequestV1:
        if len(self.claim_refs) != len(set(self.claim_refs)):
            raise ValueError("Semantic change request claim refs must be unique")
        return self


class SemanticChangeRequestV1(StrictModel):
    contract: Literal["semantic-change-request/v1"] = "semantic-change-request/v1"
    request_id: str = Field(pattern=r"^scr\.[0-9a-f]{32}$")
    classification: Literal["constructed_synthetic"] = "constructed_synthetic"
    solution_id: str
    environment_id: str
    snapshot_checksum: Sha256
    execution_id: str
    question: str
    request_type: SemanticChangeRequestType
    title: str
    observation: str
    proposed_change: str
    claim_refs: tuple[str, ...]
    status: Literal["PROPOSED_UNTRIAGED"] = "PROPOSED_UNTRIAGED"
    created_at: datetime
    request_digest: Sha256


def build_semantic_change_request(
    *,
    solution_id: str,
    environment_id: str,
    active_snapshot_checksum: str,
    request: CreateSemanticChangeRequestV1,
    execution: dict[str, Any],
) -> SemanticChangeRequestV1:
    if request.snapshot_checksum != active_snapshot_checksum:
        raise SemanticChangeError("Semantic change request is not bound to the active snapshot")
    if execution.get("execution_id") != request.execution_id:
        raise SemanticChangeError("Semantic change request execution identity mismatch")
    if execution.get("snapshot_checksum") != request.snapshot_checksum:
        raise SemanticChangeError("Semantic change request execution snapshot mismatch")
    plan = execution.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("question"), str):
        raise SemanticChangeError("Semantic change request requires an answered execution plan")
    evidence = execution.get("evidence")
    if not isinstance(evidence, list):
        raise SemanticChangeError("Semantic change request execution evidence is missing")
    available_claims = {
        item.get("claim_id")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    }
    if not set(request.claim_refs).issubset(available_claims):
        raise SemanticChangeError("Semantic change request cites unknown execution claims")
    subject = {
        "contract": "semantic-change-request/v1",
        "request_id": f"scr.{uuid.uuid4().hex}",
        "classification": "constructed_synthetic",
        "solution_id": solution_id,
        "environment_id": environment_id,
        "snapshot_checksum": request.snapshot_checksum,
        "execution_id": request.execution_id,
        "question": plan["question"],
        "request_type": request.request_type,
        "title": request.title,
        "observation": request.observation,
        "proposed_change": request.proposed_change,
        "claim_refs": request.claim_refs,
        "status": "PROPOSED_UNTRIAGED",
        "created_at": datetime.now(timezone.utc),
    }
    return SemanticChangeRequestV1(
        **subject,
        request_digest=sha256_value(subject),
    )


class FileSemanticChangeRequestStore:
    """Immutable PoC inbox. Durable product deployments can replace this port."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _solution_dir(self, solution_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", solution_id):
            raise SemanticChangeError("Invalid semantic change solution identity")
        return self.root / solution_id

    def append(self, request: SemanticChangeRequestV1) -> SemanticChangeRequestV1:
        directory = self._solution_dir(request.solution_id)
        path = directory / f"{request.request_id}.json"
        if path.exists():
            existing = SemanticChangeRequestV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if existing != request:
                raise SemanticChangeError("Semantic change request identity conflict")
            return existing
        directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        write_json(temporary, request.model_dump(mode="json"))
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = SemanticChangeRequestV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if existing != request:
                raise SemanticChangeError("Semantic change request identity conflict")
        finally:
            temporary.unlink(missing_ok=True)
        return request

    def list(self, solution_id: str) -> tuple[SemanticChangeRequestV1, ...]:
        directory = self._solution_dir(solution_id)
        if not directory.is_dir():
            return ()
        requests: list[SemanticChangeRequestV1] = []
        for path in sorted(directory.glob("scr.*.json")):
            try:
                item = SemanticChangeRequestV1.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise SemanticChangeError("Semantic change request inbox is invalid") from exc
            unsigned = item.model_dump(mode="python", exclude={"request_digest"})
            if sha256_value(unsigned) != item.request_digest:
                raise SemanticChangeError("Semantic change request digest mismatch")
            requests.append(item)
        return tuple(sorted(requests, key=lambda item: item.created_at, reverse=True))
