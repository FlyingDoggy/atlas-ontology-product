from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..cash_trading_scenario import CashTradingScenarioAdapter
from ..contracts import ReleaseRef
from ..io import file_checksum, load_package, package_checksum, sha256_value, write_json
from ..models import OntologyPackage
from ..release import PublishedReleaseHandle, StudioReleases
from ..validation import validate_semantic_package
from .workspace import (
    WorkspaceConflictError,
    WorkspaceError,
    WorkspaceStateError,
    WorkspaceUnavailableError,
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


CASH_WORKSPACE_SCHEMA = "cash-trading-draft-workspace/v1"
CASH_WORKSPACE_ID = "workspace.cash_trading.reference"
_DIMENSIONS = {
    "dimension.business_date",
    "dimension.instrument",
    "dimension.participant",
    "dimension.market_segment",
}
_FIELDS = (
    "self_trade_definition",
    "self_trade_identity_level",
    "exclude_corrections",
    "latency_percentile_method",
    "allowed_dimensions",
)


class CashWorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CashDraftFields(CashWorkspaceModel):
    self_trade_definition: str = Field(min_length=1)
    self_trade_identity_level: Literal["participant_id"] = "participant_id"
    exclude_corrections: bool
    latency_percentile_method: Literal["nearest_rank"] = "nearest_rank"
    allowed_dimensions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_closed_surface(self) -> CashDraftFields:
        if len(set(self.allowed_dimensions)) != len(self.allowed_dimensions):
            raise ValueError("Allowed dimensions must be unique")
        if not set(self.allowed_dimensions).issubset(_DIMENSIONS):
            raise ValueError("Unsupported Cash Trading dimension")
        return self


class CashDraftUpdate(CashWorkspaceModel):
    self_trade_definition: str | None = Field(default=None, min_length=1)
    self_trade_identity_level: Literal["participant_id"] | None = None
    exclude_corrections: bool | None = None
    latency_percentile_method: Literal["nearest_rank"] | None = None
    allowed_dimensions: tuple[str, ...] | None = None


class CashDraftValidation(CashWorkspaceModel):
    status: Literal["NOT_RUN", "STALE", "PASS", "FAIL"]
    revision: int | None = None
    draft_checksum: str | None = None
    validated_at: datetime | None = None
    report: dict[str, Any] | None = None


class CashDraftWorkspace(CashWorkspaceModel):
    schema_version: Literal["cash-trading-draft-workspace/v1"] = CASH_WORKSPACE_SCHEMA
    workspace_id: str = Field(
        default=CASH_WORKSPACE_ID,
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
    source_anchors: tuple[dict[str, str], ...]
    modified_fields: tuple[str, ...] = ()
    draft: CashDraftFields
    package_operations: tuple[PackageDraftOperation, ...] = ()
    draft_checksum: str
    validation: CashDraftValidation
    last_published: ReleaseRef | None = None


class CashDraftRevisionRecord(CashWorkspaceModel):
    schema_version: Literal["cash-trading-draft-revision/v1"] = (
        "cash-trading-draft-revision/v1"
    )
    workspace_id: str
    revision: int
    base_version: str | None = None
    target_version: str
    recorded_at: datetime
    draft: CashDraftFields
    draft_checksum: str
    modified_fields: tuple[str, ...]
    package_operations: tuple[PackageDraftOperation, ...] | None = None
    record_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class CashIntakeSummary(CashWorkspaceModel):
    contract: Literal["cash-trading-intake-summary/v1"] = (
        "cash-trading-intake-summary/v1"
    )
    submission_id: str
    content_checksum: str
    classification: Literal["constructed_synthetic"]
    source_file_count: int
    source_files: tuple[dict[str, Any], ...]
    assumption_count: int
    confirmation_count: int
    response_required_count: int
    reference_source_pack: dict[str, Any]
    construction_profile: dict[str, Any]
    reviewed_baseline: dict[str, Any]
    claim_ceiling: Literal["CONSTRUCTED_SYNTHETIC_NOT_CUSTOMER_VALIDATED"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_patch(version: str) -> str:
    try:
        major, minor, patch = (int(part) for part in version.split("."))
    except (TypeError, ValueError) as exc:
        raise WorkspaceStateError(f"Invalid semantic version: {version}") from exc
    return f"{major}.{minor}.{patch + 1}"


def _replace_by_id(items: tuple[Any, ...], item_id: str, replacement: Any) -> tuple[Any, ...]:
    output = tuple(replacement if item.id == item_id else item for item in items)
    if output == items and all(item.id != item_id for item in items):
        raise WorkspaceStateError(f"Required package object is missing: {item_id}")
    return output


def _by_id(items: tuple[Any, ...], item_id: str) -> Any:
    try:
        return next(item for item in items if item.id == item_id)
    except StopIteration as exc:
        raise WorkspaceStateError(
            f"Required package object is missing: {item_id}"
        ) from exc


def materialize_cash_package(
    base: OntologyPackage, workspace: CashDraftWorkspace
) -> OntologyPackage:
    draft = workspace.draft
    rule = _by_id(base.rules, "rule.potential_self_trade").model_copy(
        update={"definition": draft.self_trade_definition}
    )
    rules = _replace_by_id(base.rules, rule.id, rule)
    metrics = base.metrics
    for metric_id in (
        "metric.self_trade_eligible_trade_count",
        "metric.potential_self_trade_count",
        "metric.potential_self_trade_rate",
    ):
        metric = _by_id(metrics, metric_id)
        updates: dict[str, Any] = {"allowed_dimensions": draft.allowed_dimensions}
        if metric_id == "metric.potential_self_trade_rate":
            updates["definition"] = (
                f"{draft.self_trade_definition} Candidate count divided by the "
                "eligible population with both participant IDs present."
            )
        metrics = _replace_by_id(metrics, metric_id, metric.model_copy(update=updates))
    candidate = base.model_copy(
        update={
            "version": workspace.target_version,
            "rules": rules,
            "metrics": metrics,
        }
    )
    return materialize_package_operations(candidate, workspace.package_operations)


def _revision_record(workspace: CashDraftWorkspace) -> CashDraftRevisionRecord:
    payload = {
        "schema_version": "cash-trading-draft-revision/v1",
        "workspace_id": workspace.workspace_id,
        "revision": workspace.revision,
        "base_version": workspace.base_version,
        "target_version": workspace.target_version,
        "recorded_at": workspace.revision_created_at or workspace.created_at,
        "draft": workspace.draft,
        "draft_checksum": workspace.draft_checksum,
        "modified_fields": workspace.modified_fields,
    }
    if workspace.package_operations:
        payload["package_operations"] = workspace.package_operations
    return CashDraftRevisionRecord(**payload, record_checksum=sha256_value(payload))


def _verify_revision_record(path: Path) -> CashDraftRevisionRecord:
    try:
        record = CashDraftRevisionRecord.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise WorkspaceStateError("Cash Trading draft revision is invalid") from exc
    unsigned = record.model_dump(
        mode="python", exclude={"record_checksum"}, exclude_none=True
    )
    if sha256_value(unsigned) != record.record_checksum:
        raise WorkspaceStateError("Cash Trading draft revision checksum mismatch")
    return record


class CashTradingDraftWorkspaceService:
    """Scenario-owned Studio draft lifecycle over the common CAS/artifact store."""

    def __init__(
        self,
        root: Path,
        scenario_dir: Path,
        releases: StudioReleases,
        *,
        state_store: WorkspaceStateStore | None = None,
        identity: WorkspaceIdentity | None = None,
    ) -> None:
        if (state_store is None) != (identity is None):
            raise WorkspaceStateError(
                "Workspace durable store and identity must be configured together"
            )
        self.root = root.resolve()
        self.scenario_dir = scenario_dir.resolve()
        self.releases = releases
        self.state_store = state_store
        self.identity = identity
        self._state_tokens: dict[str, str | None] = {}

    def _directory(self, workspace_id: str) -> Path:
        expected = self.identity.workspace_id if self.identity else CASH_WORKSPACE_ID
        if workspace_id != expected:
            raise WorkspaceError("Cash Trading workspace identity mismatch")
        return self.root / workspace_id

    def _bound_workspace_id(self, workspace_id: str | None) -> str:
        """Resolve an omitted ID to the identity bound to this service instance."""
        if workspace_id is not None:
            return workspace_id
        return self.identity.workspace_id if self.identity else CASH_WORKSPACE_ID

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
        with (directory / "workspace.lock").open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _base(self) -> OntologyPackage:
        return load_package(self.scenario_dir / "ontology" / "package.yaml")

    def _intake_payload(self) -> CashIntakeSummary:
        source_path = self.scenario_dir / "intake" / "source-manifest.json"
        reference_pack_path = (
            self.scenario_dir / "intake" / "reference-source-pack.json"
        )
        construction_profile_path = (
            self.scenario_dir / "intake" / "construction-profile.json"
        )
        assumptions_path = self.scenario_dir / "governance" / "assumption-register.json"
        confirmations_path = (
            self.scenario_dir / "governance" / "external-confirmation-register.json"
        )
        reviewed_path = self.scenario_dir / "governance" / "reviewed-baseline.json"
        try:
            sources = json.loads(source_path.read_text(encoding="utf-8"))
            reference_pack = json.loads(reference_pack_path.read_text(encoding="utf-8"))
            construction_profile = json.loads(
                construction_profile_path.read_text(encoding="utf-8")
            )
            assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"))
            confirmations = json.loads(confirmations_path.read_text(encoding="utf-8"))
            reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise WorkspaceStateError("Cash Trading intake manifests are invalid") from exc
        files = tuple(sources.get("files", ()))
        decisions = tuple(assumptions.get("decisions", ()))
        items = tuple(confirmations.get("items", ()))
        base = self._base()
        metric_ids = {item.id for item in base.metrics}
        runtime_metric_ids = {
            metric_id
            for pattern in base.analysis_patterns
            for metric_id in pattern.required_metrics
        }
        assumption_ids = {str(item.get("decision_id")) for item in decisions}
        reviewed_metrics = tuple(reviewed.get("metric_set", ()))
        reviewed_source_ids = {
            str(item.get("source_metric_id")) for item in reviewed_metrics
        }
        manifest_files = {
            str(item.get("source_id")): (
                str(item.get("sha256")),
                int(item.get("size_bytes", 0)),
            )
            for item in files
        }
        packed_files = {
            str(item.get("file_id")): (
                str(item.get("sha256")),
                int(item.get("size_bytes", 0)),
            )
            for item in reference_pack.get("files", ())
        }
        baseline_valid = (
            reviewed.get("contract") == "ontology-reviewed-baseline/v1"
            and reviewed.get("package_id") == base.package_id
            and reviewed.get("semantic_version") == base.version
            and reviewed.get("review_status")
            == "INTERNAL_REVIEWED_WITH_PROVISIONAL_ASSUMPTIONS"
            and reviewed_source_ids == {f"M-{index:02d}" for index in range(1, 9)}
            and all(
                str(item.get("canonical_metric_id")) in metric_ids
                and set(item.get("assumption_ids", ())).issubset(assumption_ids)
                and (
                    item.get("agent_runtime_status") == "SUPPORTED"
                )
                == (str(item.get("canonical_metric_id")) in runtime_metric_ids)
                for item in reviewed_metrics
            )
        )
        reference_pack_valid = (
            reference_pack.get("contract") == "ontology-reference-source-pack/v1"
            and reference_pack.get("physical_file_count") == len(packed_files) == 4
            and packed_files == manifest_files
        )
        expected_collections = {
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
            "analysis_patterns",
            "policies",
            "questions",
        }
        construction_profile_valid = (
            construction_profile.get("contract")
            == "packaged-case-construction-profile/v1"
            and construction_profile.get("package_id") == base.package_id
            and construction_profile.get("required_pack_id")
            == reference_pack.get("pack_id")
            and construction_profile.get("reviewed_baseline_id")
            == reviewed.get("baseline_id")
            and set(construction_profile.get("candidate_collections", ()))
            == expected_collections
            and construction_profile.get("human_review_required") is True
            and construction_profile.get("direct_publish_allowed") is False
        )
        if not baseline_valid or not reference_pack_valid or not construction_profile_valid:
            raise WorkspaceStateError(
                "Cash Trading reviewed baseline, source pack or construction profile is inconsistent"
            )
        content_checksum = sha256_value(
            {
                "source_manifest": file_checksum(source_path),
                "reference_source_pack": file_checksum(reference_pack_path),
                "construction_profile": file_checksum(construction_profile_path),
                "assumption_register": file_checksum(assumptions_path),
                "confirmation_register": file_checksum(confirmations_path),
                "reviewed_baseline": file_checksum(reviewed_path),
            }
        )
        return CashIntakeSummary(
            submission_id="cash-trading.external-reviewer-transcription.v0.2",
            content_checksum=content_checksum,
            classification="constructed_synthetic",
            source_file_count=len(files),
            source_files=files,
            assumption_count=len(decisions),
            confirmation_count=len(items),
            response_required_count=sum(bool(item.get("response_required")) for item in items),
            reference_source_pack=reference_pack,
            construction_profile=construction_profile,
            reviewed_baseline=reviewed,
            claim_ceiling="CONSTRUCTED_SYNTHETIC_NOT_CUSTOMER_VALIDATED",
        )

    def _read(self, workspace_id: str) -> CashDraftWorkspace | None:
        if self.state_store is not None and self.identity is not None:
            try:
                loaded = self.state_store.load(self.identity)
            except WorkspaceStoreError as exc:
                raise WorkspaceUnavailableError(str(exc)) from exc
            if loaded is None:
                self._state_tokens[workspace_id] = None
                return None
            try:
                workspace = CashDraftWorkspace.model_validate(loaded.payload)
            except ValueError as exc:
                raise WorkspaceStateError(
                    "Durable Cash Trading workspace is invalid"
                ) from exc
            self._state_tokens[workspace_id] = loaded.token
            return workspace
        path = self._path(workspace_id)
        if not path.is_file():
            return None
        try:
            return CashDraftWorkspace.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise WorkspaceStateError("Cash Trading workspace is unreadable") from exc

    def _write(
        self,
        workspace: CashDraftWorkspace,
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
            if _verify_revision_record(revision_path) != record:
                raise WorkspaceStateError("Cash Trading draft revision is immutable")
        else:
            write_json(revision_path, record.model_dump(mode="json"))
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        write_json(temporary, workspace.model_dump(mode="json"))
        os.replace(temporary, path)

    def _initial_target(self, base: OntologyPackage) -> str:
        refs = self.releases.list(base.package_id)
        latest = max(
            (base.version, *(ref.version for ref in refs)),
            key=lambda version: tuple(int(part) for part in version.split(".")),
        )
        return _next_patch(latest)

    @staticmethod
    def _default_draft(base: OntologyPackage) -> CashDraftFields:
        rate = _by_id(base.metrics, "metric.potential_self_trade_rate")
        rule = _by_id(base.rules, "rule.potential_self_trade")
        return CashDraftFields(
            self_trade_definition=rule.definition,
            self_trade_identity_level="participant_id",
            exclude_corrections=True,
            latency_percentile_method="nearest_rank",
            allowed_dimensions=rate.allowed_dimensions,
        )

    def _new(self) -> CashDraftWorkspace:
        base = self._base()
        intake = self._intake_payload()
        now = _utc_now()
        provisional = CashDraftWorkspace(
            workspace_id=(
                self.identity.workspace_id
                if self.identity is not None
                else CASH_WORKSPACE_ID
            ),
            package_id=base.package_id,
            base_version=base.version,
            target_version=self._initial_target(base),
            revision=1,
            created_at=now,
            updated_at=now,
            revision_created_at=now,
            intake_submission_id=intake.submission_id,
            intake_checksum=intake.content_checksum,
            source_anchors=(
                {
                    "field": "self_trade_definition",
                    "source": "governance/assumption-register.json",
                    "anchor": "CT-ASM-005..CT-ASM-007",
                },
                {
                    "field": "latency_percentile_method",
                    "source": "governance/assumption-register.json",
                    "anchor": "CT-ASM-008",
                },
                {
                    "field": "allowed_dimensions",
                    "source": "ontology/package.yaml",
                    "anchor": "metric.potential_self_trade_rate",
                },
            ),
            draft=self._default_draft(base),
            draft_checksum="pending",
            validation=CashDraftValidation(status="NOT_RUN"),
        )
        return provisional.model_copy(
            update={
                "draft_checksum": package_checksum(
                    materialize_cash_package(base, provisional)
                )
            }
        )

    def _rebase(
        self,
        current: CashDraftWorkspace,
        base: OntologyPackage,
    ) -> CashDraftWorkspace:
        if current.package_id != base.package_id:
            raise WorkspaceStateError("Cash Trading draft package identity changed")
        intake = self._intake_payload()
        default = self._default_draft(base)
        now = _utc_now()
        rebased = current.model_copy(
            update={
                "base_version": base.version,
                "target_version": self._initial_target(base),
                "revision": current.revision + 1,
                "updated_at": now,
                "revision_created_at": now,
                "intake_submission_id": intake.submission_id,
                "intake_checksum": intake.content_checksum,
                "modified_fields": tuple(
                    field
                    for field in _FIELDS
                    if getattr(current.draft, field) != getattr(default, field)
                ),
                "validation": CashDraftValidation(status="STALE"),
            }
        )
        try:
            checksum = package_checksum(materialize_cash_package(base, rebased))
        except (ValueError, WorkspaceStateError) as exc:
            raise WorkspaceStateError(
                "Cash Trading draft cannot be rebased onto the reviewed package"
            ) from exc
        return rebased.model_copy(update={"draft_checksum": checksum})

    def _ensure(self, workspace_id: str) -> CashDraftWorkspace:
        current = self._read(workspace_id)
        if current is not None:
            base = self._base()
            if current.base_version != base.version:
                rebased = self._rebase(current, base)
                self._write(rebased)
                return rebased
            return current
        created = self._new()
        try:
            self._write(created)
        except WorkspaceConflictError:
            concurrent = self._read(workspace_id)
            if concurrent is None:
                raise
            return concurrent
        return created

    def get(self, workspace_id: str | None = None) -> CashDraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            return self._ensure(workspace_id)

    def candidate_package(
        self, workspace_id: str | None = None
    ) -> OntologyPackage:
        """Materialize the exact candidate represented by the current draft."""
        workspace_id = self._bound_workspace_id(workspace_id)
        return materialize_cash_package(self._base(), self.get(workspace_id))

    def get_intake(self, workspace_id: str | None = None) -> CashIntakeSummary:
        workspace_id = self._bound_workspace_id(workspace_id)
        self.get(workspace_id)
        return self._intake_payload()

    def patch(
        self,
        update: CashDraftUpdate,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> CashDraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            values = current.draft.model_dump(mode="python")
            for field in _FIELDS:
                value = getattr(update, field)
                if value is not None:
                    values[field] = value
            draft = CashDraftFields.model_validate(values)
            if draft == current.draft:
                return current
            target_version = current.target_version
            if current.last_published is not None and (
                current.last_published.version == current.target_version
            ):
                target_version = _next_patch(target_version)
            initial = self._new().draft
            now = _utc_now()
            updated = current.model_copy(
                update={
                    "target_version": target_version,
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "draft": draft,
                    "modified_fields": tuple(
                        field for field in _FIELDS if getattr(draft, field) != getattr(initial, field)
                    ),
                    "validation": CashDraftValidation(status="STALE"),
                }
            )
            updated = updated.model_copy(
                update={
                    "draft_checksum": package_checksum(
                        materialize_cash_package(self._base(), updated)
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
            Callable[[CashDraftWorkspace], Callable[[Any], None]] | None
        ) = None,
    ) -> CashDraftWorkspace:
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
                    "validation": CashDraftValidation(status="STALE"),
                }
            )
            updated = updated.model_copy(
                update={
                    "draft_checksum": package_checksum(
                        materialize_cash_package(self._base(), updated)
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
    ) -> tuple[CashDraftRevisionRecord, ...]:
        workspace_id = self._bound_workspace_id(workspace_id)
        self.get(workspace_id)
        if self.state_store is not None and self.identity is not None:
            try:
                durable = self.state_store.list_revisions(self.identity)
                return tuple(
                    CashDraftRevisionRecord.model_validate(record.subject.payload)
                    for record in durable
                )
            except (WorkspaceStoreError, ValueError) as exc:
                raise WorkspaceUnavailableError(
                    "Durable Cash Trading revision history is invalid"
                ) from exc
        return tuple(
            _verify_revision_record(path)
            for path in sorted(
                (self._directory(workspace_id) / "revisions").glob("r*.json")
            )
        )

    def validate(
        self,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> CashDraftWorkspace:
        workspace_id = self._bound_workspace_id(workspace_id)
        with self._lock(workspace_id):
            current = self._ensure(workspace_id)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            package = materialize_cash_package(self._base(), current)
            semantic = validate_semantic_package(package)
            adapter = CashTradingScenarioAdapter().validate(package)
            compatibility_defects: list[str] = []
            lowered = current.draft.self_trade_definition.lower()
            if any(term in lowered for term in ("market abuse", "misconduct", "违规结论")):
                compatibility_defects.append(
                    "self-trade definition exceeds the triage-only claim ceiling"
                )
            if not current.draft.exclude_corrections:
                compatibility_defects.append(
                    "the installed runtime requires correction-lineage exclusion"
                )
            adapter_failures = [
                check.check_id for check in adapter.checks if check.status == "FAIL"
            ]
            status = (
                "PASS"
                if semantic.status == "PASS"
                and not adapter_failures
                and not compatibility_defects
                else "FAIL"
            )
            report = {
                "contract": "cash-trading-draft-validation/v1",
                "status": status,
                "semantic_validation": semantic.model_dump(mode="json"),
                "adapter_checks": [check.model_dump(mode="json") for check in adapter.checks],
                "compatibility_defects": compatibility_defects,
            }
            updated = current.model_copy(
                update={
                    "updated_at": _utc_now(),
                    "validation": CashDraftValidation(
                        status=status,
                        revision=current.revision,
                        draft_checksum=current.draft_checksum,
                        validated_at=_utc_now(),
                        report=report,
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
    ) -> tuple[CashDraftWorkspace, PublishedReleaseHandle]:
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
                    "The exact current Cash Trading draft must pass validation before publication"
                )
            publication = self.releases.publish(
                materialize_cash_package(self._base(), current),
                limitations=(
                    "constructed synthetic; not customer validated",
                    "External Reviewer/customer confirmation remains open and is not runtime authority",
                ),
            )
            updated = current.model_copy(
                update={"updated_at": _utc_now(), "last_published": publication.ref}
            )
            self._write(updated)
            return updated, publication
