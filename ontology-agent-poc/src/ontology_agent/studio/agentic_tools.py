from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import Field, ValidationError, model_validator

from ..io import sha256_value
from ..metric_semantics import canonical_unit, expanded_formula_facts
from ..models import OntologyPackage, StrictModel
from ..validation import failed_checks, validate_candidate_package
from .agentic_contracts import (
    AgentRunCompletionV1,
    AgentToolCallV1,
    AgentToolDefinitionV1,
    CandidateClaimV1,
    CandidateMutationV1,
    ObligationDispositionV1,
    RunAuthorityContextV1,
    ToolInvocationV1,
)
from .agentic_evidence import EvidenceWorkspaceError, ExactEvidenceWorkspace
from .agentic_store import (
    AgentCheckpointStore,
    AgenticStoreConflict,
    CandidateWorkspaceView,
)
from .package_authoring import (
    PackageCollection,
    PackageDraftOperation,
    apply_package_operations,
    package_collection_items,
    package_collection_schemas,
)


class AgentToolError(RuntimeError):
    """A structured tool invocation was invalid or could not be completed."""


class EvidenceSearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    source_version_ids: tuple[str, ...] = Field(default=(), max_length=64)
    max_hits: int = Field(default=20, ge=1, le=100)


class EvidenceReadArgs(StrictModel):
    source_version_id: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class EvidenceListSourcesArgs(StrictModel):
    pass


class SpreadsheetListSheetsArgs(StrictModel):
    source_version_id: str


class SpreadsheetReadRangeArgs(StrictModel):
    source_version_id: str
    sheet_name: str = Field(min_length=1, max_length=255)
    cell_range: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z]+[1-9][0-9]*:[A-Za-z]+[1-9][0-9]*$",
    )


class SqlInspectArgs(StrictModel):
    source_version_id: str


class SqlReadStatementArgs(StrictModel):
    source_version_id: str
    ordinal: int = Field(ge=1)


class SchemaGetCollectionArgs(StrictModel):
    collection: Literal[
        "scenario",
        "sources",
        "decisions",
        "actors",
        "processes",
        "entities",
        "properties",
        "relationships",
        "dimensions",
        "rules",
        "metrics",
        "data_sources",
        "bindings",
        "joins",
        "sql_contracts",
        "analysis_patterns",
        "policies",
        "questions",
    ] | None = None
    collections: tuple[PackageCollection, ...] = Field(default=(), max_length=18)

    @model_validator(mode="after")
    def one_collection_selector(self) -> SchemaGetCollectionArgs:
        if (self.collection is None) == (not self.collections):
            raise ValueError("Provide collection or collections, but not both")
        if len(self.collections) != len(set(self.collections)):
            raise ValueError("Schema collections must be unique")
        return self


class CandidateListArgs(StrictModel):
    collection: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)


class CandidateGetArgs(StrictModel):
    collection: str
    object_id: str


class CandidateUpsertArgs(StrictModel):
    expected_candidate_revision: int = Field(ge=0)
    collection: PackageCollection
    object_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    payload: dict[str, Any]
    claims: tuple[CandidateClaimV1, ...] = Field(min_length=1, max_length=128)
    # Foundational ontology assets (for example the Scenario envelope, Actors,
    # Entities and Properties) can be required by the connected model without
    # directly closing one frozen analytical obligation.  Evidence is still
    # mandatory through claims; obligation coverage is an independent concern.
    obligation_ids: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_operation_shape(cls, value: Any) -> Any:
        """Read old journal fixtures while advertising only the simpler v2 shape.

        The model should not have to duplicate an object's identity inside a nested
        mutation envelope.  Existing immutable tool journals and regression fixtures
        still replay through this narrow compatibility adapter.
        """

        if not isinstance(value, dict) or "operation" not in value:
            return value
        normalized = dict(value)
        operation = normalized.pop("operation")
        if not isinstance(operation, dict) or operation.get("action") != "UPSERT":
            return value
        normalized["collection"] = operation.get("collection")
        normalized["object_id"] = operation.get("object_id")
        normalized["payload"] = operation.get("payload")
        return normalized


class CandidatePatchItemArgs(StrictModel):
    collection: PackageCollection
    object_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    payload: dict[str, Any]
    claims: tuple[CandidateClaimV1, ...] = Field(min_length=1, max_length=128)
    obligation_ids: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_operation_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "operation" not in value:
            return value
        normalized = dict(value)
        operation = normalized.pop("operation")
        if not isinstance(operation, dict) or operation.get("action") != "UPSERT":
            return value
        normalized["collection"] = operation.get("collection")
        normalized["object_id"] = operation.get("object_id")
        normalized["payload"] = operation.get("payload")
        return normalized


class CandidateApplyPatchArgs(StrictModel):
    expected_candidate_revision: int = Field(ge=0)
    items: tuple[CandidatePatchItemArgs, ...] = Field(min_length=1, max_length=32)


class ObligationCoverageItemArgs(StrictModel):
    obligation_id: str = Field(
        pattern=r"^obligation\.[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    candidate_targets: tuple[str, ...] = Field(min_length=1, max_length=128)
    explanation: str = Field(default="", max_length=2000)


class ObligationCoverArgs(StrictModel):
    expected_candidate_revision: int = Field(ge=0)
    items: tuple[ObligationCoverageItemArgs, ...] = Field(
        min_length=1, max_length=128
    )


class CandidateValidateArgs(StrictModel):
    pass


class GapRecordArgs(StrictModel):
    expected_candidate_revision: int = Field(ge=0)
    gap_id: str = Field(pattern=r"^gap\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    obligation_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    unsupported: bool = False


class WorkingMemoryUpdateArgs(StrictModel):
    notes: str = Field(min_length=1, max_length=20_000)


class CompletionArgs(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)


_TOOL_MODELS: tuple[
    tuple[str, str, type[StrictModel], bool], ...
] = (
    (
        "evidence.list_sources",
        "List every exact source in the frozen set, including parser completeness and unsupported formats.",
        EvidenceListSourcesArgs,
        False,
    ),
    (
        "evidence.search",
        "Search the frozen exact source set. Search hits are discovery aids and are not citeable evidence.",
        EvidenceSearchArgs,
        False,
    ),
    (
        "evidence.read",
        "Read an exact line range and receive a server-minted evidence receipt.",
        EvidenceReadArgs,
        False,
    ),
    (
        "spreadsheet.list_sheets",
        "List sheets and exact used ranges for one frozen XLSX source.",
        SpreadsheetListSheetsArgs,
        False,
    ),
    (
        "spreadsheet.read_range",
        "Read a bounded exact XLSX range and receive a server-minted evidence receipt.",
        SpreadsheetReadRangeArgs,
        False,
    ),
    (
        "sql.inspect",
        "List parsed SQL statement identities and types. Inspection is not itself citeable evidence.",
        SqlInspectArgs,
        False,
    ),
    (
        "sql.read_statement",
        "Read one exact parsed SQL statement and receive a server-minted evidence receipt.",
        SqlReadStatementArgs,
        False,
    ),
    (
        "schema.get_collection",
        "Inspect compact Candidate JSON Schemas for one collection or batch `collections` before authoring. Batch unfamiliar types once; do not repeatedly fetch unchanged schemas.",
        SchemaGetCollectionArgs,
        False,
    ),
    (
        "candidate.list",
        "Page through a compact Candidate identity index. Use candidate.get only for a target whose full payload is needed; do not re-list after a successful write merely to confirm it.",
        CandidateListArgs,
        False,
    ),
    (
        "candidate.get",
        "Read one current non-authoritative candidate object.",
        CandidateGetArgs,
        False,
    ),
    (
        "candidate.upsert",
        "Create or replace one typed Candidate. Pass collection, object_id and the collection payload fields; obligation_ids are optional for supporting assets. Omit payload.id, payload.status and payload.sources because the server derives authority/provenance fields from exact claim receipts. Scenario is singular and its authoritative object_id is bound by the server.",
        CandidateUpsertArgs,
        True,
    ),
    (
        "candidate.apply_patch",
        "Atomically create or replace up to 32 typed Candidates. Each item uses flat collection, object_id, payload, claims and optional obligation_ids; omit payload.id, payload.status and payload.sources because the server derives them. Scenario is singular and its authoritative object_id is bound by the server.",
        CandidateApplyPatchArgs,
        True,
    ),
    (
        "obligation.cover",
        "Close one or more frozen obligations with existing evidenced Candidate targets. The server verifies target existence, exact logical-source citation and exact Evidence Receipts; use Gap only for a real missing or unsupported boundary.",
        ObligationCoverArgs,
        True,
    ),
    (
        "gap.record",
        "Disposition a frozen obligation as an evidenced gap or unsupported input.",
        GapRecordArgs,
        True,
    ),
    (
        "candidate.validate",
        "Materialize the prospective package and run every deterministic candidate-stage structural, semantic, language, binding, SQL and SHACL check.",
        CandidateValidateArgs,
        False,
    ),
    (
        "run.update_working_memory",
        "Persist bounded non-authoritative Agent working notes across context checkpoints. Notes are not evidence, Candidate data, review findings, or release authority.",
        WorkingMemoryUpdateArgs,
        False,
    ),
    (
        "run.request_completion",
        "Request deterministic completion checking and immutable Candidate Bundle sealing. Ordinary model finish cannot complete a run.",
        CompletionArgs,
        False,
    ),
)


def tool_definitions() -> tuple[AgentToolDefinitionV1, ...]:
    return tuple(
        AgentToolDefinitionV1(
            name=name,
            description=description,
            input_schema=model.model_json_schema(),
            mutating=mutating,
        )
        for name, description, model, mutating in _TOOL_MODELS
    )


def tool_registry_digest() -> str:
    return sha256_value([item.model_dump(mode="json") for item in tool_definitions()])


_ARG_MODEL_BY_TOOL = {name: model for name, _, model, _ in _TOOL_MODELS}


class StudioToolHarness:
    """Server-owned tool registry. The model sees schemas, never authority fields."""

    def __init__(
        self,
        *,
        store: AgentCheckpointStore,
        evidence: ExactEvidenceWorkspace,
        context: RunAuthorityContextV1,
    ) -> None:
        if context.tool_registry_digest != tool_registry_digest():
            raise AgentToolError("Run Tool Registry digest does not match the server")
        self.store = store
        self.evidence = evidence
        self.context = context
        self.completion: AgentRunCompletionV1 | None = None

    @property
    def definitions(self) -> tuple[AgentToolDefinitionV1, ...]:
        return tool_definitions()

    def execute(self, call: AgentToolCallV1) -> dict[str, Any]:
        model = _ARG_MODEL_BY_TOOL.get(call.name)
        if model is None:
            raise AgentToolError(f"Unknown or unauthorized tool: {call.name}")
        try:
            args = model.model_validate(call.arguments)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors(include_url=False, include_input=False)[:12]
            )
            raise AgentToolError(
                f"Invalid arguments for {call.name}: {details}"
            ) from exc
        invocation = ToolInvocationV1(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            arguments=call.arguments,
            arguments_digest=sha256_value(call.arguments),
        )
        previous = self.store.get_tool_receipt(self.context, invocation)
        if previous is not None:
            return dict(previous.result)
        handler: Callable[[Any, ToolInvocationV1], dict[str, Any]] = getattr(
            self, "_" + call.name.replace(".", "_")
        )
        return handler(args, invocation)

    def execute_for_runtime(self, call: AgentToolCallV1) -> dict[str, Any]:
        """Execute one model call while keeping repairable mistakes in the loop.

        Invalid arguments, an out-of-range evidence read, or a candidate CAS miss are
        observations the model can repair.  Lease/authority failures and unexpected
        implementation errors still escape and terminate the worker.
        """

        try:
            return self.execute(call)
        except (AgentToolError, EvidenceWorkspaceError, AgenticStoreConflict) as exc:
            invocation = ToolInvocationV1(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                arguments=call.arguments,
                arguments_digest=sha256_value(call.arguments),
            )
            return self._commit_read(
                invocation,
                {
                    "ok": False,
                    "error_code": type(exc).__name__.upper(),
                    "message": str(exc),
                    "repairable": True,
                },
            )

    def _commit_read(
        self, invocation: ToolInvocationV1, result: dict[str, Any]
    ) -> dict[str, Any]:
        receipt = self.store.commit_tool_execution(
            self.context, invocation, result=result
        )
        return dict(receipt.result)

    def _evidence_search(
        self, args: EvidenceSearchArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        hits = self.evidence.search(
            args.query,
            source_version_ids=args.source_version_ids,
            max_hits=args.max_hits,
        )
        result = {
            "hits": [
                {
                    "source_version_id": item.source_version_id,
                    "logical_role_ids": list(item.logical_role_ids),
                    "canonical_locator": item.canonical_locator,
                    "snippet": item.snippet,
                    "snippet_checksum": item.snippet_checksum,
                    "citeable": False,
                }
                for item in hits
            ]
        }
        return self._commit_read(invocation, result)

    def _evidence_list_sources(
        self, args: EvidenceListSourcesArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        del args
        result = {
            "sources": [
                {
                    "source_version_id": item.source_version_id,
                    "source_id": item.source_id,
                    "candidate_source_id": item.source_id,
                    "title": item.title,
                    "original_name": item.original_name,
                    "media_type": item.media_type,
                    "kind": item.kind,
                    "evidence_kind": item.evidence_kind,
                    "logical_role_ids": list(item.logical_role_ids),
                    "index_receipt": item.index_receipt.model_dump(mode="json"),
                    "candidate_provenance_note": (
                        "Read exact content first; Candidate sources are then derived "
                        "by the server from the returned evidence_receipt.receipt_id."
                    ),
                }
                for item in self.evidence.list_sources()
            ]
        }
        return self._commit_read(invocation, result)

    def _evidence_read(
        self, args: EvidenceReadArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        read = self.evidence.read_lines(
            args.source_version_id,
            start_line=args.start_line,
            end_line=args.end_line,
        )
        result = {
            "content": read.content,
            "evidence_receipt": read.receipt.model_dump(mode="json"),
            "candidate_citation": {
                "evidence_receipt_id": read.receipt.receipt_id,
                "source_ids": list(read.receipt.logical_role_ids),
                "usage": "Put the receipt ID in claims[].evidence_receipt_ids; the server derives payload.sources.",
            },
        }
        receipt = self.store.commit_tool_execution(
            self.context,
            invocation,
            result=result,
            evidence_receipt=read.receipt,
        )
        return dict(receipt.result)

    def _spreadsheet_list_sheets(
        self, args: SpreadsheetListSheetsArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        sheets = self.evidence.list_sheets(args.source_version_id)
        return self._commit_read(
            invocation,
            {
                "source_version_id": args.source_version_id,
                "sheets": [
                    {
                        "name": item.name,
                        "used_range": item.used_range,
                        "indexed_cells": item.indexed_cells,
                        "total_cells": item.total_cells,
                    }
                    for item in sheets
                ],
            },
        )

    def _spreadsheet_read_range(
        self, args: SpreadsheetReadRangeArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        read = self.evidence.read_spreadsheet_range(
            args.source_version_id,
            sheet_name=args.sheet_name,
            cell_range=args.cell_range,
        )
        result = {
            "content": read.content,
            "evidence_receipt": read.receipt.model_dump(mode="json"),
            "candidate_citation": {
                "evidence_receipt_id": read.receipt.receipt_id,
                "source_ids": list(read.receipt.logical_role_ids),
                "usage": "Put the receipt ID in claims[].evidence_receipt_ids; the server derives payload.sources.",
            },
        }
        receipt = self.store.commit_tool_execution(
            self.context,
            invocation,
            result=result,
            evidence_receipt=read.receipt,
        )
        return dict(receipt.result)

    def _sql_inspect(
        self, args: SqlInspectArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        statements = self.evidence.inspect_sql(args.source_version_id)
        return self._commit_read(
            invocation,
            {
                "source_version_id": args.source_version_id,
                "statements": [
                    {
                        "ordinal": item.ordinal,
                        "statement_type": item.statement_type,
                        "query_checksum": item.query_checksum,
                    }
                    for item in statements
                ],
                "citeable": False,
            },
        )

    def _sql_read_statement(
        self, args: SqlReadStatementArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        read = self.evidence.read_sql_statement(
            args.source_version_id,
            ordinal=args.ordinal,
        )
        result = {
            "content": read.content,
            "evidence_receipt": read.receipt.model_dump(mode="json"),
            "candidate_citation": {
                "evidence_receipt_id": read.receipt.receipt_id,
                "source_ids": list(read.receipt.logical_role_ids),
                "usage": "Put the receipt ID in claims[].evidence_receipt_ids; the server derives payload.sources.",
            },
        }
        receipt = self.store.commit_tool_execution(
            self.context,
            invocation,
            result=result,
            evidence_receipt=read.receipt,
        )
        return dict(receipt.result)

    def _schema_get_collection(
        self, args: SchemaGetCollectionArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        selected = (
            (args.collection,) if args.collection is not None else args.collections
        )
        exact_schemas = package_collection_schemas(selected)

        def compact(collection: PackageCollection) -> dict[str, Any]:
            governed = collection not in {"sources", "decisions"}
            server_managed_fields = ["id"]
            if governed:
                server_managed_fields.extend(("status", "sources"))
            exact_schema = exact_schemas[collection]
            payload_schema = dict(exact_schema)
            payload_schema["properties"] = {
                key: value
                for key, value in exact_schema.get("properties", {}).items()
                if key not in server_managed_fields
            }
            payload_schema["required"] = [
                key
                for key in exact_schema.get("required", [])
                if key not in server_managed_fields
            ]
            return {
                "candidate_payload_schema": payload_schema,
                "server_managed_fields": server_managed_fields,
            }

        contracts = {collection: compact(collection) for collection in selected}
        result: dict[str, Any] = {
            "authoring_note": (
                "Pass only candidate_payload_schema fields in payload. The server "
                "sets id from object_id and derives status/sources from authority "
                "and exact claim receipts."
            )
        }
        if args.collection is not None:
            result.update({"collection": args.collection, **contracts[args.collection]})
        else:
            result.update({"collections": contracts})
        return self._commit_read(
            invocation,
            result,
        )

    def _candidate_list(
        self, args: CandidateListArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        operations = [
            item
            for item in view.operations
            if args.collection is None or item.collection == args.collection
        ]
        page = operations[args.offset : args.offset + args.limit]
        return self._commit_read(
            invocation,
            {
                "candidate_revision": view.candidate_revision,
                "total": len(operations),
                "offset": args.offset,
                "next_offset": (
                    args.offset + len(page)
                    if args.offset + len(page) < len(operations)
                    else None
                ),
                "candidates": [
                    {
                        "collection": item.collection,
                        "object_id": item.object_id,
                        "action": item.action,
                        "payload_digest": sha256_value(item.payload),
                    }
                    for item in page
                ],
            },
        )

    def _candidate_get(
        self, args: CandidateGetArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        operation = next(
            (
                item
                for item in view.operations
                if item.collection == args.collection and item.object_id == args.object_id
            ),
            None,
        )
        return self._commit_read(
            invocation,
            {
                "candidate_revision": view.candidate_revision,
                "candidate": operation.model_dump(mode="json") if operation else None,
            },
        )

    @staticmethod
    def _base_target_sources(
        operation: PackageDraftOperation,
        base_package: OntologyPackage,
    ) -> set[str]:
        for item in package_collection_items(base_package, operation.collection):
            if getattr(item, "id", None) == operation.object_id:
                return {str(source_id) for source_id in getattr(item, "sources", ())}
        return set()

    def _validate_declared_source_receipts(
        self,
        operation: PackageDraftOperation,
        claims: tuple[CandidateClaimV1, ...],
        *,
        view: CandidateWorkspaceView,
    ) -> None:
        """Reject provenance labels that the current Run cannot substantiate.

        A Candidate may preserve source identities already present on the same
        authoritative Draft object.  Every source newly declared by this Run must,
        however, be represented by at least one server-minted Evidence Receipt in
        the Candidate's claim set.  The claim's support class remains model-owned;
        this guard only prevents a source label from being asserted without reading
        that exact frozen source.
        """

        if operation.action != "UPSERT" or operation.payload is None:
            return
        declared_sources = {
            str(source_id) for source_id in operation.payload.get("sources", ())
        }
        if not declared_sources:
            return

        preserved_sources = self._base_target_sources(
            operation,
            view.base_package,
        )
        receipts = {item.receipt_id: item for item in view.evidence_receipts}
        evidenced_sources = {
            source_id
            for claim in claims
            for receipt_id in claim.evidence_receipt_ids
            if receipt_id in receipts
            for source_id in receipts[receipt_id].logical_role_ids
        }
        missing_sources = declared_sources - preserved_sources - evidenced_sources
        if missing_sources:
            raise AgentToolError(
                "Candidate declares sources without a current Run Evidence Receipt: "
                + ", ".join(sorted(missing_sources))
            )

    @staticmethod
    def _receipt_source_ids(
        claims: tuple[CandidateClaimV1, ...],
        *,
        view: CandidateWorkspaceView,
    ) -> set[str]:
        receipts = {item.receipt_id: item for item in view.evidence_receipts}
        return {
            source_id
            for claim in claims
            for receipt_id in claim.evidence_receipt_ids
            if receipt_id in receipts
            for source_id in receipts[receipt_id].logical_role_ids
        }

    def _author_candidate_operation(
        self,
        *,
        collection: PackageCollection,
        object_id: str,
        payload: dict[str, Any],
        claims: tuple[CandidateClaimV1, ...],
        view: CandidateWorkspaceView,
    ) -> PackageDraftOperation:
        """Form the typed mutation while keeping authority metadata server-owned."""

        # Scenario is a package singleton.  Its identity comes from the frozen
        # Draft, not from model judgment.  Binding it here lets the model author
        # the business meaning while the deterministic shell retains authority.
        if collection == "scenario":
            object_id = view.base_package.scenario.id

        normalized = dict(payload)
        normalized["id"] = object_id
        if collection not in {"sources", "decisions"}:
            normalized["status"] = "proposed"
            preserved_sources = {
                str(source_id)
                for item in package_collection_items(view.base_package, collection)
                if getattr(item, "id", None) == object_id
                for source_id in getattr(item, "sources", ())
            }
            evidenced_sources = self._receipt_source_ids(claims, view=view)
            authoritative_sources = preserved_sources | evidenced_sources
            if not authoritative_sources:
                raise AgentToolError(
                    "A governed Candidate requires at least one exact claim receipt; "
                    "read the supporting source and put evidence_receipt.receipt_id in "
                    "claims[].evidence_receipt_ids. payload.sources is server-managed."
                )
            normalized["sources"] = sorted(authoritative_sources)
        try:
            return PackageDraftOperation(
                action="UPSERT",
                collection=collection,
                object_id=object_id,
                payload=normalized,
            )
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors(include_url=False, include_input=False)[:12]
            )
            raise AgentToolError(
                f"Invalid {collection} Candidate payload for {object_id}: {details}. "
                "Call schema.get_collection and use candidate_payload_schema; omit "
                "payload.id, payload.status and payload.sources."
            ) from exc

    def _candidate_upsert(
        self, args: CandidateUpsertArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        operation = self._author_candidate_operation(
            collection=args.collection,
            object_id=args.object_id,
            payload=args.payload,
            claims=args.claims,
            view=view,
        )
        target = f"{operation.collection}:{operation.object_id}"
        self._validate_declared_source_receipts(
            operation,
            args.claims,
            view=view,
        )
        current = {
            item.obligation_id: item
            for item in view.obligation_dispositions
        }
        dispositions = tuple(
            ObligationDispositionV1(
                obligation_id=obligation_id,
                disposition="CANDIDATE",
                candidate_targets=tuple(
                    sorted(
                        {
                            target,
                            *(
                                current[obligation_id].candidate_targets
                                if obligation_id in current
                                and current[obligation_id].disposition == "CANDIDATE"
                                else ()
                            ),
                        }
                    )
                ),
            )
            for obligation_id in args.obligation_ids
        )
        result = {
            "accepted": True,
            "target": target,
            "candidate_revision": args.expected_candidate_revision + 1,
        }
        try:
            receipt = self.store.commit_tool_execution(
                self.context,
                invocation,
                result=result,
                mutation=CandidateMutationV1(
                    expected_candidate_revision=args.expected_candidate_revision,
                    operation=operation,
                    claims=args.claims,
                ),
                obligation_dispositions=dispositions,
            )
        except ValueError as exc:
            # A typed operation can be syntactically valid yet semantically invalid
            # against the current Candidate head (for example, deprecating an object
            # that does not exist).  This is model-correctable input, not a worker
            # failure.  Keep unexpected exceptions outside this narrow boundary.
            raise AgentToolError(str(exc)) from exc
        return dict(receipt.result)

    def _candidate_apply_patch(
        self, args: CandidateApplyPatchArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        operations = tuple(
            self._author_candidate_operation(
                collection=item.collection,
                object_id=item.object_id,
                payload=item.payload,
                claims=item.claims,
                view=view,
            )
            for item in args.items
        )
        targets = [
            f"{operation.collection}:{operation.object_id}"
            for operation in operations
        ]
        if len(targets) != len(set(targets)):
            raise AgentToolError("Candidate patch targets must be unique")

        for item, operation in zip(args.items, operations, strict=True):
            self._validate_declared_source_receipts(
                operation,
                item.claims,
                view=view,
            )

        current = {
            item.obligation_id: item
            for item in view.obligation_dispositions
        }
        targets_by_obligation: dict[str, set[str]] = {}
        for target, item in zip(targets, args.items, strict=True):
            for obligation_id in item.obligation_ids:
                targets_by_obligation.setdefault(obligation_id, set()).add(target)
        dispositions = tuple(
            ObligationDispositionV1(
                obligation_id=obligation_id,
                disposition="CANDIDATE",
                candidate_targets=tuple(
                    sorted(
                        {
                            *new_targets,
                            *(
                                current[obligation_id].candidate_targets
                                if obligation_id in current
                                and current[obligation_id].disposition == "CANDIDATE"
                                else ()
                            ),
                        }
                    )
                ),
            )
            for obligation_id, new_targets in sorted(targets_by_obligation.items())
        )
        mutations = tuple(
            CandidateMutationV1(
                expected_candidate_revision=args.expected_candidate_revision,
                operation=operation,
                claims=item.claims,
            )
            for item, operation in zip(args.items, operations, strict=True)
        )
        result = {
            "accepted": True,
            "targets": targets,
            "candidate_revision": args.expected_candidate_revision + 1,
        }
        try:
            receipt = self.store.commit_tool_execution(
                self.context,
                invocation,
                result=result,
                mutations=mutations,
                obligation_dispositions=dispositions,
            )
        except ValueError as exc:
            raise AgentToolError(str(exc)) from exc
        return dict(receipt.result)

    def _obligation_cover(
        self, args: ObligationCoverArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        objectives = {
            item.obligation_id: item for item in view.objective.obligations
        }
        operations = {
            f"{item.collection}:{item.object_id}": item
            for item in view.operations
        }
        receipts = {item.receipt_id: item for item in view.evidence_receipts}
        evidence_sources = {
            item.source_version_id: item for item in self.evidence.list_sources()
        }

        obligation_ids = [item.obligation_id for item in args.items]
        if len(obligation_ids) != len(set(obligation_ids)):
            raise AgentToolError("Covered obligation identities must be unique")

        current = {
            item.obligation_id: item for item in view.obligation_dispositions
        }
        dispositions: list[ObligationDispositionV1] = []
        for item in args.items:
            objective = objectives.get(item.obligation_id)
            if objective is None:
                raise AgentToolError(
                    f"Unknown frozen obligation: {item.obligation_id}"
                )
            if len(item.candidate_targets) != len(set(item.candidate_targets)):
                raise AgentToolError(
                    f"Candidate targets must be unique for {item.obligation_id}"
                )

            expected_versions = set(objective.source_version_ids)
            expected_source_ids = {
                evidence_sources[version_id].source_id
                for version_id in expected_versions
                if version_id in evidence_sources
            }
            if len(expected_source_ids) != len(expected_versions):
                raise AgentToolError(
                    f"Frozen evidence inventory is incomplete for {item.obligation_id}"
                )

            for target in item.candidate_targets:
                operation = operations.get(target)
                if operation is None:
                    raise AgentToolError(
                        f"Covered target does not exist in Candidate Workspace: {target}"
                    )
                payload_sources = {
                    str(value)
                    for value in (operation.payload or {}).get("sources", [])
                }
                if not payload_sources.intersection(expected_source_ids):
                    raise AgentToolError(
                        f"Candidate {target} does not cite the logical source for "
                        f"{item.obligation_id}; expected one of "
                        + ", ".join(sorted(expected_source_ids))
                    )

                claims = view.claims_by_target.get(target, ())
                if not claims:
                    raise AgentToolError(
                        f"Candidate {target} has no claim-level evidence"
                    )
                cited_receipts = [
                    receipts[receipt_id]
                    for claim in claims
                    for receipt_id in claim.evidence_receipt_ids
                    if receipt_id in receipts
                ]
                if not any(
                    receipt.source_version_id in expected_versions
                    for receipt in cited_receipts
                ):
                    raise AgentToolError(
                        f"Candidate {target} has no exact Evidence Receipt from the "
                        f"frozen source scope for {item.obligation_id}"
                    )

            previous_targets = (
                current[item.obligation_id].candidate_targets
                if item.obligation_id in current
                and current[item.obligation_id].disposition == "CANDIDATE"
                else ()
            )
            dispositions.append(
                ObligationDispositionV1(
                    obligation_id=item.obligation_id,
                    disposition="CANDIDATE",
                    candidate_targets=tuple(
                        sorted({*previous_targets, *item.candidate_targets})
                    ),
                    explanation=item.explanation,
                )
            )

        result = {
            "accepted": True,
            "covered_obligations": obligation_ids,
            "candidate_revision": args.expected_candidate_revision + 1,
        }
        receipt = self.store.commit_tool_execution(
            self.context,
            invocation,
            result=result,
            expected_candidate_revision=args.expected_candidate_revision,
            obligation_dispositions=tuple(dispositions),
        )
        return dict(receipt.result)

    def _gap_record(
        self, args: GapRecordArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        disposition: Literal["GAP", "UNSUPPORTED"] = (
            "UNSUPPORTED" if args.unsupported else "GAP"
        )
        values = tuple(
            ObligationDispositionV1(
                obligation_id=obligation_id,
                disposition=disposition,
                gap_id=args.gap_id,
                explanation=args.description,
            )
            for obligation_id in args.obligation_ids
        )
        result = {
            "accepted": True,
            "gap_id": args.gap_id,
            "candidate_revision": args.expected_candidate_revision + 1,
        }
        receipt = self.store.commit_tool_execution(
            self.context,
            invocation,
            result=result,
            expected_candidate_revision=args.expected_candidate_revision,
            obligation_dispositions=values,
        )
        return dict(receipt.result)

    def _materialize(self) -> tuple[OntologyPackage | None, tuple[str, ...], dict[str, Any] | None]:
        view = self.store.view(self.context)
        try:
            package = apply_package_operations(view.base_package, view.operations)
        except ValueError as exc:
            return None, (f"MATERIALIZATION: {exc}",), None
        report = validate_candidate_package(package)
        failures = tuple(failed_checks(report))
        errors = tuple(
            f"{item.check_id}: {item.message}; details={item.details}"
            for item in failures
        )
        return package, errors, report.model_dump(mode="json")

    def _obligation_shape_errors(self) -> tuple[str, ...]:
        """Ensure a claimed disposition contains the product artifacts it promises.

        The model chooses the ontology contents.  The shell only prevents it from
        declaring a requirement complete with the wrong kind of artifact (for
        example, metrics without a question and analysis pattern).
        """

        view = self.store.view(self.context)
        dispositions = {
            item.obligation_id: item for item in view.obligation_dispositions
        }
        errors: list[str] = []
        for obligation in view.objective.obligations:
            required = set(obligation.required_candidate_collections)
            if not required:
                continue
            disposition = dispositions.get(obligation.obligation_id)
            if disposition is None or disposition.disposition != "CANDIDATE":
                continue
            actual = {
                target.split(":", 1)[0]
                for target in disposition.candidate_targets
                if ":" in target
            }
            missing = sorted(required - actual)
            if missing:
                errors.append(
                    "OBLIGATION_SHAPE: "
                    f"{obligation.obligation_id} claims Candidate coverage but is "
                    "missing required collections: "
                    + ", ".join(missing)
                )
        return tuple(errors)

    def _metric_obligation_errors(
        self, package: OntologyPackage | None
    ) -> tuple[str, ...]:
        """Check source-frozen metric meaning without asking the shell to model it.

        These checks cover machine identity and mechanically explicit unit/scale
        conventions.  Natural-language business equivalence remains Builder and
        human-review work.
        """

        if package is None:
            return ()
        view = self.store.view(self.context)
        metric_obligations = tuple(
            item
            for item in view.objective.obligations
            if item.metric_semantic_contract is not None
        )
        if not metric_obligations:
            return ()

        errors: list[str] = []
        metrics = {item.id: item for item in package.metrics}
        invalid_ids = sorted(item for item in metrics if not item.startswith("metric."))
        if invalid_ids:
            errors.append(
                "METRIC_ID_NAMESPACE: metric Candidates must use the stable "
                "'metric.' namespace: " + ", ".join(invalid_ids)
            )

        dispositions = {
            item.obligation_id: item for item in view.obligation_dispositions
        }
        for obligation in metric_obligations:
            contract = obligation.metric_semantic_contract
            assert contract is not None
            disposition = dispositions.get(obligation.obligation_id)
            if disposition is None or disposition.disposition in {
                "UNRESOLVED",
                "GAP",
                "UNSUPPORTED",
                "NOOP",
            }:
                continue

            expected_target = f"metrics:{contract.expected_metric_id}"
            if expected_target not in disposition.candidate_targets:
                errors.append(
                    "METRIC_OBLIGATION_IDENTITY: "
                    f"{obligation.obligation_id} must be covered by {expected_target}; "
                    "a similarly labelled metric is not the same governed identity"
                )
                continue
            metric = metrics.get(contract.expected_metric_id)
            if metric is None:
                errors.append(
                    "METRIC_OBLIGATION_IDENTITY: expected Candidate is missing: "
                    f"{contract.expected_metric_id}"
                )
                continue

            defects: list[str] = []
            if (
                contract.expected_metric_type is not None
                and metric.metric_type != contract.expected_metric_type
            ):
                defects.append(
                    f"metric_type {metric.metric_type} != "
                    f"{contract.expected_metric_type}"
                )
            if (
                contract.expected_value_type is not None
                and metric.value_type != contract.expected_value_type
            ):
                defects.append(
                    f"value_type {metric.value_type} != "
                    f"{contract.expected_value_type}"
                )
            if contract.expected_unit is not None and canonical_unit(
                metric.unit
            ) != canonical_unit(contract.expected_unit):
                defects.append(f"unit {metric.unit} != {contract.expected_unit}")
            if (
                contract.required_formula_root is not None
                and metric.formula.op != contract.required_formula_root
            ):
                defects.append(
                    f"formula root {metric.formula.op} != "
                    f"{contract.required_formula_root}"
                )

            operations, literals, referenced_units = expanded_formula_facts(
                metric, metrics=metrics
            )
            missing_operations = sorted(
                set(contract.required_formula_operations) - operations
            )
            if missing_operations:
                defects.append(
                    "missing formula operations: " + ", ".join(missing_operations)
                )
            missing_literals = [
                str(item)
                for item in contract.required_formula_literals
                if item not in literals
            ]
            if missing_literals:
                defects.append(
                    "missing formula literals: " + ", ".join(missing_literals)
                )
            required_units = {
                canonical_unit(item) for item in contract.required_referenced_units
            }
            missing_units = sorted(
                item for item in required_units if item and item not in referenced_units
            )
            if missing_units:
                defects.append(
                    "missing referenced base-metric units: "
                    + ", ".join(missing_units)
                )
            if defects:
                errors.append(
                    "METRIC_OBLIGATION_SEMANTICS: "
                    f"{contract.expected_metric_id} violates the frozen source "
                    "contract: "
                    + "; ".join(defects)
                )
        return tuple(errors)

    def _candidate_validate(
        self, args: CandidateValidateArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        del args
        package, errors, report = self._materialize()
        errors = (
            *errors,
            *self._obligation_shape_errors(),
            *self._metric_obligation_errors(package),
        )
        result = {
            "valid": package is not None and not errors,
            "errors": list(errors),
            "prospective_package_checksum": sha256_value(package) if package else None,
            "validator_report": report,
            "validator_report_digest": sha256_value(report) if report else None,
        }
        return self._commit_read(invocation, result)

    def _run_update_working_memory(
        self, args: WorkingMemoryUpdateArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        return self._commit_read(
            invocation,
            {
                "accepted": True,
                "notes_digest": sha256_value(args.notes),
                "candidate_revision": view.candidate_revision,
                "authority": "NON_AUTHORITATIVE_AGENT_MEMORY",
            },
        )

    def _run_request_completion(
        self, args: CompletionArgs, invocation: ToolInvocationV1
    ) -> dict[str, Any]:
        view = self.store.view(self.context)
        unresolved = [
            item.obligation_id
            for item in view.obligation_dispositions
            if item.disposition == "UNRESOLVED"
        ]
        package, validation_errors, validator_report = self._materialize()
        obligation_shape_errors = self._obligation_shape_errors()
        metric_obligation_errors = self._metric_obligation_errors(package)
        blockers = [
            *(f"UNRESOLVED: {item}" for item in unresolved),
            *validation_errors,
            *obligation_shape_errors,
            *metric_obligation_errors,
        ]
        if package is None or blockers:
            return self._commit_read(
                invocation,
                {
                    "completed": False,
                    "repair_required": True,
                    "blockers": blockers,
                    "reason": args.reason,
                },
            )
        deterministic_report = {
            "validator": "ontology-studio/candidate-semantic-validator@3",
            "prospective_package_checksum": sha256_value(package),
            "report": validator_report,
        }
        report_digest = sha256_value(deterministic_report)
        bundle = self.store.seal(
            self.context,
            prospective_package_checksum=sha256_value(package),
            validator_report_digests=(report_digest,),
        )
        blocked_dispositions = [
            item
            for item in view.obligation_dispositions
            if item.disposition in {"GAP", "UNSUPPORTED"}
        ]
        outcome: Literal["REVIEW_READY", "BLOCKED"] = (
            "BLOCKED" if blocked_dispositions else "REVIEW_READY"
        )
        completion = AgentRunCompletionV1(
            outcome=outcome,
            bundle=bundle,
            blockers=tuple(item.explanation for item in blocked_dispositions),
        )
        result = {
            "completed": True,
            "outcome": outcome,
            "bundle_id": bundle.bundle_id,
            "bundle_checksum": bundle.bundle_checksum,
        }
        committed = self._commit_read(invocation, result)
        self.completion = completion
        return committed
