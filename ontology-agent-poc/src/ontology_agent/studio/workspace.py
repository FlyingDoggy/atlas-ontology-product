from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts import ReleaseRef
from ..io import load_package, package_checksum, sha256_value, write_json
from ..models import Condition, FormulaNode, OntologyPackage
from ..release import PublishedReleaseHandle, StudioReleases
from ..validation import validate_semantic_package
from .intake import (
    ADTIntakeRegistry,
    IntakeSubmission,
    REFERENCE_SUBMISSION_ID,
    SourceAnchor,
)
from .package_authoring import (
    PackageDraftOperation,
    PackageDraftOperationsV1,
    apply_package_operations as materialize_package_operations,
)
from .workspace_store import (
    WorkspaceIdentity,
    WorkspaceStateStore,
    WorkspaceStoreConflict,
    WorkspaceStoreError,
)


WORKSPACE_SCHEMA = "adt-draft-workspace/v1"
REFERENCE_WORKSPACE_ID = "workspace.adt.reference"
_SUPPORTED_DIMENSIONS = {"dimension.period", "dimension.segment"}
_SUPPORTED_AMOUNT_COLUMNS = {
    "executed_value_hkd_mn",
    "order_value_hkd_mn",
}


class WorkspaceError(RuntimeError):
    pass


class WorkspaceConflictError(WorkspaceError):
    pass


class WorkspaceStateError(WorkspaceError):
    pass


class WorkspaceUnavailableError(WorkspaceError):
    pass


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EligibilityDraft(WorkspaceModel):
    include_status: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    exclude_cancelled: bool


class DraftFields(WorkspaceModel):
    metric_definition: str = Field(min_length=1)
    eligibility_rule: EligibilityDraft
    allowed_dimensions: tuple[str, ...] = Field(min_length=1)
    amount_mapping: str

    @model_validator(mode="after")
    def validate_fixed_adt_surface(self) -> DraftFields:
        if len(set(self.allowed_dimensions)) != len(self.allowed_dimensions):
            raise ValueError("Allowed dimensions must be unique")
        if not set(self.allowed_dimensions).issubset(_SUPPORTED_DIMENSIONS):
            raise ValueError("Unsupported ADT dimension")
        if self.amount_mapping not in _SUPPORTED_AMOUNT_COLUMNS:
            raise ValueError("Unsupported ADT amount mapping")
        return self


class EligibilityUpdate(WorkspaceModel):
    include_status: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9_]*$"
    )
    exclude_cancelled: bool | None = None


class DraftUpdate(WorkspaceModel):
    metric_definition: str | None = Field(default=None, min_length=1)
    eligibility_rule: EligibilityUpdate | None = None
    allowed_dimensions: tuple[str, ...] | None = None
    amount_mapping: str | None = None


class DraftValidation(WorkspaceModel):
    status: Literal["NOT_RUN", "STALE", "PASS", "FAIL"]
    revision: int | None = None
    draft_checksum: str | None = None
    validated_at: datetime | None = None
    report: dict[str, Any] | None = None


class DraftWorkspace(WorkspaceModel):
    schema_version: Literal["adt-draft-workspace/v1"] = WORKSPACE_SCHEMA
    workspace_id: str = Field(
        default=REFERENCE_WORKSPACE_ID,
        pattern=r"^workspace\.[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    package_id: str
    base_version: str
    target_version: str
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime | None = None
    intake_submission_id: str
    intake_checksum: str
    source_anchors: tuple[SourceAnchor, ...]
    modified_fields: tuple[
        Literal[
            "metric_definition",
            "eligibility_rule",
            "allowed_dimensions",
            "amount_mapping",
        ],
        ...,
    ] = ()
    draft: DraftFields
    package_operations: tuple[PackageDraftOperation, ...] = ()
    draft_checksum: str
    validation: DraftValidation
    last_published: ReleaseRef | None = None


class DraftRevisionRecord(WorkspaceModel):
    schema_version: Literal["adt-draft-revision/v1"] = "adt-draft-revision/v1"
    workspace_id: str
    revision: int
    target_version: str
    recorded_at: datetime
    draft: DraftFields
    draft_checksum: str
    modified_fields: tuple[str, ...]
    package_operations: tuple[PackageDraftOperation, ...] | None = None
    record_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


def _revision_record(workspace: DraftWorkspace) -> DraftRevisionRecord:
    payload = {
        "schema_version": "adt-draft-revision/v1",
        "workspace_id": workspace.workspace_id,
        "revision": workspace.revision,
        "target_version": workspace.target_version,
        "recorded_at": workspace.revision_created_at or workspace.created_at,
        "draft": workspace.draft,
        "draft_checksum": workspace.draft_checksum,
        "modified_fields": workspace.modified_fields,
    }
    if workspace.package_operations:
        payload["package_operations"] = workspace.package_operations
    return DraftRevisionRecord(**payload, record_checksum=sha256_value(payload))


def _verify_revision_record(path: Path) -> DraftRevisionRecord:
    try:
        record = DraftRevisionRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkspaceStateError("Draft revision record is invalid") from exc
    return _validate_revision_record(record)


def _validate_revision_record(record: DraftRevisionRecord) -> DraftRevisionRecord:
    unsigned = record.model_dump(
        mode="python", exclude={"record_checksum"}, exclude_none=True
    )
    if sha256_value(unsigned) != record.record_checksum:
        raise WorkspaceStateError("Draft revision record checksum mismatch")
    return record


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_patch(version: str) -> str:
    try:
        major, minor, patch = (int(part) for part in version.split("."))
    except (TypeError, ValueError) as exc:
        raise WorkspaceStateError(f"Invalid semantic version: {version}") from exc
    return f"{major}.{minor}.{patch + 1}"


def _replace_by_id(items: tuple[Any, ...], item_id: str, replacement: Any) -> tuple[Any, ...]:
    found = False
    output: list[Any] = []
    for item in items:
        if item.id == item_id:
            output.append(replacement)
            found = True
        else:
            output.append(item)
    if not found:
        raise WorkspaceStateError(f"Required package object is missing: {item_id}")
    return tuple(output)


def _by_id(items: tuple[Any, ...], item_id: str) -> Any:
    for item in items:
        if item.id == item_id:
            return item
    raise WorkspaceStateError(f"Required package object is missing: {item_id}")


def materialize_package(base: OntologyPackage, workspace: DraftWorkspace) -> OntologyPackage:
    """Compile the small ADT draft surface into an exact OntologyPackage candidate."""
    draft = workspace.draft
    adt = _by_id(base.metrics, "metric.average_daily_turnover").model_copy(
        update={
            "definition": draft.metric_definition,
            "allowed_dimensions": draft.allowed_dimensions,
        }
    )

    amount_binding = next(
        (
            binding
            for binding in base.bindings
            if binding.table == "trade_fact"
            and binding.column == draft.amount_mapping
            and binding.data_type == "decimal"
        ),
        None,
    )
    if amount_binding is None:
        raise WorkspaceStateError("The selected amount field has no approved decimal binding")
    eligible_turnover = _by_id(base.metrics, "metric.eligible_turnover")
    eligible_turnover = eligible_turnover.model_copy(
        update={
            "formula": FormulaNode(
                op="sum",
                args=(FormulaNode(op="field_ref", ref=amount_binding.logical_target),),
            ),
            "query": eligible_turnover.query.model_copy(
                update={"measure_property": amount_binding.logical_target}
            ),
        }
    )

    eligibility = draft.eligibility_rule
    conditions: list[Condition] = [
        Condition(
            property="property.trade.status",
            op="eq",
            value=eligibility.include_status,
        )
    ]
    if eligibility.exclude_cancelled:
        conditions.append(
            Condition(property="property.trade.cancellation_flag", op="is_false")
        )
    rule = _by_id(base.rules, "rule.eligible_trade").model_copy(
        update={
            "definition": (
                f"Include {eligibility.include_status} trades"
                + (
                    " and exclude cancelled records."
                    if eligibility.exclude_cancelled
                    else ", including cancelled records."
                )
            ),
            "all": tuple(conditions),
        }
    )

    metrics = _replace_by_id(base.metrics, eligible_turnover.id, eligible_turnover)
    metrics = _replace_by_id(metrics, adt.id, adt)
    rules = _replace_by_id(base.rules, rule.id, rule)
    candidate = base.model_copy(
        update={
            "version": workspace.target_version,
            "metrics": metrics,
            "rules": rules,
        }
    )
    return materialize_package_operations(candidate, workspace.package_operations)


class DraftWorkspaceService:
    """ADT authoring adapter behind one workspace use-case boundary.

    Local compatibility keeps the existing locked files. New product deployments inject
    a PostgreSQL/S3 store, so the same transitions use a durable CAS head and exact
    immutable revision artifacts without making the repository understand ADT fields.
    """

    def __init__(
        self,
        root: Path,
        scenario_dir: Path,
        releases: StudioReleases,
        *,
        state_store: WorkspaceStateStore | None = None,
        identity: WorkspaceIdentity | None = None,
    ):
        if (state_store is None) != (identity is None):
            raise WorkspaceStateError(
                "Workspace durable store and identity must be configured together"
            )
        self.root = root.resolve()
        self.scenario_dir = scenario_dir.resolve()
        self.releases = releases
        self.intake = ADTIntakeRegistry(self.root / "submissions", self.scenario_dir)
        self.state_store = state_store
        self.identity = identity
        self._state_tokens: dict[str, str | None] = {}

    def _directory(self, workspace_id: str) -> Path:
        expected_workspace_id = (
            self.identity.workspace_id if self.identity is not None else REFERENCE_WORKSPACE_ID
        )
        if workspace_id != expected_workspace_id:
            raise WorkspaceError("Only the fixed ADT reference workspace is supported")
        return self.root / workspace_id

    def _bound_workspace_id(self, workspace_id: str | None) -> str:
        """Resolve an omitted ID to the identity bound to this service instance."""
        if workspace_id is not None:
            return workspace_id
        return (
            self.identity.workspace_id
            if self.identity is not None
            else REFERENCE_WORKSPACE_ID
        )

    def _path(self, workspace_id: str) -> Path:
        return self._directory(workspace_id) / "workspace.json"

    @contextmanager
    def _lock(self, workspace_id: str) -> Iterator[None]:
        if self.state_store is not None:
            self._directory(workspace_id)
            yield
            return
        directory = self._directory(workspace_id)
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / "workspace.lock"
        with lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _read(self, workspace_id: str) -> DraftWorkspace | None:
        if self.state_store is not None and self.identity is not None:
            try:
                loaded = self.state_store.load(self.identity)
            except WorkspaceStoreError as exc:
                raise WorkspaceUnavailableError(str(exc)) from exc
            if loaded is None:
                self._state_tokens[workspace_id] = None
                return None
            try:
                workspace = DraftWorkspace.model_validate(loaded.payload)
            except ValueError as exc:
                raise WorkspaceStateError("Durable draft workspace is invalid") from exc
            self._state_tokens[workspace_id] = loaded.token
            return workspace
        path = self._path(workspace_id)
        if not path.is_file():
            return None
        try:
            return DraftWorkspace.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkspaceStateError("Draft workspace is unreadable") from exc

    def _write(
        self,
        workspace: DraftWorkspace,
        *,
        transaction_hook: Callable[[Any], None] | None = None,
    ) -> None:
        record = _revision_record(workspace)
        if self.state_store is not None and self.identity is not None:
            try:
                committed = self.state_store.commit(
                    self.identity,
                    payload=workspace.model_dump(mode="json"),
                    revision_payload=record.model_dump(
                        mode="json", exclude_none=True
                    ),
                    expected_subject_checksum=self._state_tokens.get(
                        workspace.workspace_id
                    ),
                    transaction_hook=transaction_hook,
                )
            except WorkspaceStoreConflict as exc:
                raise WorkspaceConflictError("Draft revision conflict") from exc
            except WorkspaceStoreError as exc:
                raise WorkspaceUnavailableError(str(exc)) from exc
            self._state_tokens[workspace.workspace_id] = committed.token
            return
        if transaction_hook is not None:
            raise WorkspaceStateError(
                "Transactional review apply requires the PostgreSQL workspace authority"
            )
        path = self._path(workspace.workspace_id)
        revision_path = (
            self._directory(workspace.workspace_id)
            / "revisions"
            / f"r{workspace.revision:06d}.json"
        )
        if revision_path.exists():
            existing = _verify_revision_record(revision_path)
            if existing != record:
                raise WorkspaceStateError("Draft revision record is immutable")
        else:
            write_json(revision_path, record.model_dump(mode="json"))
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        write_json(temporary, workspace.model_dump(mode="json"))
        os.replace(temporary, path)

    def _base(self) -> OntologyPackage:
        return load_package(self.scenario_dir / "ontology" / "package.yaml")

    def _initial_target(self, base: OntologyPackage) -> str:
        refs = self.releases.list(base.package_id)
        latest = refs[0].version if refs else base.version
        return _next_patch(latest)

    def _new(self, submission: IntakeSubmission) -> DraftWorkspace:
        base = self._base()
        extracted = submission.extracted_draft
        now = _utc_now()
        provisional = DraftWorkspace(
            workspace_id=(
                self.identity.workspace_id
                if self.identity is not None
                else REFERENCE_WORKSPACE_ID
            ),
            package_id=base.package_id,
            base_version=base.version,
            target_version=self._initial_target(base),
            revision=1,
            created_at=now,
            updated_at=now,
            revision_created_at=now,
            intake_submission_id=submission.submission_id,
            intake_checksum=submission.content_checksum,
            source_anchors=submission.anchors,
            modified_fields=(),
            draft=DraftFields(
                metric_definition=extracted.metric_definition,
                eligibility_rule=EligibilityDraft(
                    **extracted.eligibility_rule.model_dump(mode="python")
                ),
                allowed_dimensions=extracted.allowed_dimensions,
                amount_mapping=extracted.amount_mapping,
            ),
            draft_checksum="pending",
            validation=DraftValidation(status="NOT_RUN"),
        )
        return provisional.model_copy(
            update={"draft_checksum": package_checksum(materialize_package(base, provisional))}
        )

    def _ensure(self, workspace_id: str) -> DraftWorkspace:
        current = self._read(workspace_id)
        if current is not None:
            return current
        submission = self.intake.register_reference()
        created = self._new(submission)
        try:
            self._write(created)
        except WorkspaceConflictError:
            # Another replica may have initialized the exact registered workspace first.
            concurrent = self._read(workspace_id)
            if concurrent is None:
                raise
            return concurrent
        return created

    def get(self, workspace_id: str | None = None) -> DraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            return self._ensure(workspace_id)

    def candidate_package(
        self, workspace_id: str | None = None
    ) -> OntologyPackage:
        """Materialize the exact candidate represented by the current draft."""
        workspace_id = self._bound_workspace_id(workspace_id)
        return materialize_package(self._base(), self.get(workspace_id))

    def get_intake(
        self, workspace_id: str | None = None
    ) -> IntakeSubmission:
        workspace_id = self._bound_workspace_id(workspace_id)
        workspace = self.get(workspace_id)
        return self.intake.load(workspace.intake_submission_id)

    def patch(
        self,
        update: DraftUpdate,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> DraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")

            target_version = current.target_version
            if (
                current.last_published is not None
                and current.last_published.version == current.target_version
            ):
                target_version = _next_patch(current.target_version)

            draft_values = current.draft.model_dump(mode="python")
            if update.metric_definition is not None:
                draft_values["metric_definition"] = update.metric_definition
            if update.allowed_dimensions is not None:
                draft_values["allowed_dimensions"] = update.allowed_dimensions
            if update.amount_mapping is not None:
                draft_values["amount_mapping"] = update.amount_mapping
            if update.eligibility_rule is not None:
                eligibility = current.draft.eligibility_rule.model_dump(mode="python")
                if update.eligibility_rule.include_status is not None:
                    eligibility["include_status"] = update.eligibility_rule.include_status
                if update.eligibility_rule.exclude_cancelled is not None:
                    eligibility["exclude_cancelled"] = (
                        update.eligibility_rule.exclude_cancelled
                    )
                draft_values["eligibility_rule"] = eligibility
            draft = DraftFields.model_validate(draft_values)
            if draft == current.draft:
                return current

            extracted = self.intake.load(current.intake_submission_id).extracted_draft
            extracted_draft = DraftFields(
                metric_definition=extracted.metric_definition,
                eligibility_rule=EligibilityDraft(
                    **extracted.eligibility_rule.model_dump(mode="python")
                ),
                allowed_dimensions=extracted.allowed_dimensions,
                amount_mapping=extracted.amount_mapping,
            )
            modified_fields = tuple(
                field
                for field in (
                    "metric_definition",
                    "eligibility_rule",
                    "allowed_dimensions",
                    "amount_mapping",
                )
                if getattr(draft, field) != getattr(extracted_draft, field)
            )
            now = _utc_now()
            updated = current.model_copy(
                update={
                    "target_version": target_version,
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "draft": draft,
                    "modified_fields": modified_fields,
                    "validation": DraftValidation(status="STALE"),
                }
            )
            updated = updated.model_copy(
                update={
                    "draft_checksum": package_checksum(
                        materialize_package(self._base(), updated)
                    )
                }
            )
            self._write(updated)
            return updated

    def apply_package_operations(
        self,
        request: PackageDraftOperationsV1,
        *,
        workspace_id: str | None = None,
        transaction_hook_factory: (
            Callable[[DraftWorkspace], Callable[[Any], None]] | None
        ) = None,
    ) -> DraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != request.expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            operations = (*current.package_operations, *request.operations)
            target_version = current.target_version
            if current.last_published is not None and (
                current.last_published.version == current.target_version
            ):
                target_version = _next_patch(target_version)
            now = _utc_now()
            updated = current.model_copy(
                update={
                    "target_version": target_version,
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "package_operations": operations,
                    "validation": DraftValidation(status="STALE"),
                }
            )
            updated = updated.model_copy(
                update={
                    "draft_checksum": package_checksum(
                        materialize_package(self._base(), updated)
                    )
                }
            )
            transaction_hook = (
                transaction_hook_factory(updated)
                if transaction_hook_factory is not None
                else None
            )
            self._write(updated, transaction_hook=transaction_hook)
            return updated

    def list_revisions(
        self, workspace_id: str | None = None
    ) -> tuple[DraftRevisionRecord, ...]:
        workspace_id = self._bound_workspace_id(workspace_id)
        self.get(workspace_id)
        if self.state_store is not None and self.identity is not None:
            try:
                durable = self.state_store.list_revisions(self.identity)
                return tuple(
                    _validate_revision_record(
                        DraftRevisionRecord.model_validate(record.subject.payload)
                    )
                    for record in durable
                )
            except (WorkspaceStoreError, ValueError) as exc:
                raise WorkspaceUnavailableError(
                    "Durable draft revision history is invalid"
                ) from exc
        revision_root = self._directory(workspace_id) / "revisions"
        records = tuple(
            _verify_revision_record(path)
            for path in sorted(revision_root.glob("r*.json"))
        )
        return records

    def validate(
        self,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> DraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            package = materialize_package(self._base(), current)
            report = validate_semantic_package(package)
            updated = current.model_copy(
                update={
                    "updated_at": _utc_now(),
                    "validation": DraftValidation(
                        status=report.status,
                        revision=current.revision,
                        draft_checksum=current.draft_checksum,
                        validated_at=report.validated_at,
                        report=report.model_dump(mode="json"),
                    ),
                }
            )
            self._write(updated)
            return updated

    def publish(
        self,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> tuple[DraftWorkspace, PublishedReleaseHandle]:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            if (
                current.validation.status != "PASS"
                or current.validation.revision != current.revision
                or current.validation.draft_checksum != current.draft_checksum
            ):
                raise WorkspaceStateError(
                    "The exact current draft must pass validation before publication"
                )
            package = materialize_package(self._base(), current)
            publication = self.releases.publish(
                package,
                limitations=(
                    "constructed synthetic; not HKEX validated",
                    "existing SQL registered for human comparison; not automatically reconciled",
                ),
            )
            updated = current.model_copy(
                update={
                    "updated_at": _utc_now(),
                    "last_published": publication.ref,
                }
            )
            self._write(updated)
            return updated, publication
