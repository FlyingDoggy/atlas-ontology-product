from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import Field

from ..contracts import ReleaseRef
from ..io import load_package, package_checksum, sha256_value, write_json
from ..language_policy import create_authoring_policy
from ..models import Actor, AuthoringLanguage, OntologyPackage, StrictModel
from ..release import PublishedReleaseHandle, StudioReleases
from ..validation import validate_semantic_package
from .package_authoring import (
    PackageDraftOperation,
    PackageDraftOperationsV1,
    ReviewFinalizationOperationsV1,
    apply_package_operations,
)
from .workspace import (
    DraftValidation,
    WorkspaceConflictError,
    WorkspaceStateError,
    WorkspaceUnavailableError,
)
from .workspace_store import (
    WorkspaceIdentity,
    WorkspaceStateStore,
    WorkspaceStoreConflict,
    WorkspaceStoreError,
)


GENERIC_WORKSPACE_SCHEMA = "generic-draft-workspace/v1"
_ONTOLOGY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GenericIntakeSnapshot(StrictModel):
    """The empty intake envelope used before the first exact source is registered."""

    contract: Literal["generic-intake-snapshot/v1"] = "generic-intake-snapshot/v1"
    workspace_id: str
    submission_id: str
    content_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    assets: tuple[dict[str, Any], ...] = ()


class GenericDraftWorkspace(StrictModel):
    schema_version: Literal["generic-draft-workspace/v1"] = GENERIC_WORKSPACE_SCHEMA
    workspace_id: str = Field(pattern=r"^workspace\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    package_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    base_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    target_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    solution_intent: str = Field(min_length=1, max_length=4000)
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    modified_fields: tuple[str, ...] = ()
    package_operations: tuple[PackageDraftOperation, ...] = ()
    draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation: DraftValidation
    last_published: ReleaseRef | None = None


class GenericDraftRevision(StrictModel):
    schema_version: Literal["generic-draft-revision/v1"] = (
        "generic-draft-revision/v1"
    )
    workspace_id: str
    revision: int = Field(ge=1)
    target_version: str
    recorded_at: datetime
    solution_intent: str
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    modified_fields: tuple[str, ...]
    package_operations: tuple[PackageDraftOperation, ...]
    draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


def _revision_record(workspace: GenericDraftWorkspace) -> GenericDraftRevision:
    unsigned = {
        "schema_version": "generic-draft-revision/v1",
        "workspace_id": workspace.workspace_id,
        "revision": workspace.revision,
        "target_version": workspace.target_version,
        "recorded_at": workspace.revision_created_at,
        "solution_intent": workspace.solution_intent,
        "authoring_language": workspace.authoring_language,
        "language_policy_digest": workspace.language_policy_digest,
        "modified_fields": workspace.modified_fields,
        "package_operations": workspace.package_operations,
        "draft_checksum": workspace.draft_checksum,
    }
    return GenericDraftRevision(
        **unsigned,
        record_checksum=sha256_value(
            {key: value for key, value in unsigned.items() if value is not None}
        ),
    )


def _validated_revision(payload: dict[str, Any]) -> GenericDraftRevision:
    record = GenericDraftRevision.model_validate(payload)
    unsigned = record.model_dump(
        mode="python", exclude={"record_checksum"}, exclude_none=True
    )
    if sha256_value(unsigned) != record.record_checksum:
        raise WorkspaceStateError("Generic draft revision checksum mismatch")
    return record


def _next_patch(version: str) -> str:
    try:
        major, minor, patch = (int(part) for part in version.split("."))
    except (TypeError, ValueError) as exc:
        raise WorkspaceStateError("Invalid semantic version") from exc
    return f"{major}.{minor}.{patch + 1}"


class GenericDraftWorkspaceService:
    """Case-neutral Draft authority used by blank, imported and future solutions.

    The service owns only lifecycle and typed package operations. Domain extraction is
    delegated to the Builder; publication remains gated by deterministic validation.
    """

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

    def _workspace_id(self, workspace_id: str | None = None) -> str:
        expected = self.identity.workspace_id if self.identity is not None else None
        value = workspace_id or expected
        if value is None or (expected is not None and value != expected):
            raise WorkspaceStateError("Generic workspace identity mismatch")
        return value

    def _directory(self, workspace_id: str) -> Path:
        return self.root / workspace_id

    @contextmanager
    def _lock(self, workspace_id: str) -> Iterator[None]:
        if self.state_store is not None:
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

    def _read(self, workspace_id: str) -> GenericDraftWorkspace | None:
        if self.state_store is not None and self.identity is not None:
            try:
                loaded = self.state_store.load(self.identity)
            except WorkspaceStoreError as exc:
                raise WorkspaceUnavailableError(str(exc)) from exc
            if loaded is None:
                self._state_tokens[workspace_id] = None
                return None
            try:
                workspace = GenericDraftWorkspace.model_validate(loaded.payload)
            except ValueError as exc:
                raise WorkspaceStateError("Generic durable Draft is invalid") from exc
            self._state_tokens[workspace_id] = loaded.token
            return workspace
        path = self._directory(workspace_id) / "workspace.json"
        if not path.is_file():
            return None
        try:
            return GenericDraftWorkspace.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise WorkspaceStateError("Generic Draft is unreadable") from exc

    def _write(
        self,
        workspace: GenericDraftWorkspace,
        *,
        transaction_hook: Callable[[Any], None] | None = None,
    ) -> None:
        record = _revision_record(workspace)
        if self.state_store is not None and self.identity is not None:
            try:
                committed = self.state_store.commit(
                    self.identity,
                    payload=workspace.model_dump(mode="json"),
                    revision_payload=record.model_dump(mode="json"),
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
                "Transactional review apply requires the durable workspace authority"
            )
        directory = self._directory(workspace.workspace_id)
        revision_path = directory / "revisions" / f"r{workspace.revision:06d}.json"
        if revision_path.exists():
            try:
                existing = _validated_revision(
                    json.loads(revision_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise WorkspaceStateError("Generic revision is invalid") from exc
            if existing != record:
                raise WorkspaceStateError("Generic revision record is immutable")
        else:
            write_json(revision_path, record.model_dump(mode="json"))
        path = directory / "workspace.json"
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        write_json(temporary, workspace.model_dump(mode="json"))
        os.replace(temporary, path)

    def _base(self) -> OntologyPackage:
        return load_package(self.scenario_dir / "ontology" / "package.yaml")

    def _candidate(self, workspace: GenericDraftWorkspace) -> OntologyPackage:
        base = self._base()
        actor_ids = {item.id for item in base.actors}
        scenario_owner = base.scenario.owner
        if scenario_owner not in actor_ids:
            owner_id = (
                scenario_owner
                if _ONTOLOGY_ID.fullmatch(scenario_owner)
                else "actor.solution_owner"
            )
            language = workspace.authoring_language or "en"
            owner = Actor.model_validate(
                {
                    "id": owner_id,
                    "version": base.version,
                    "status": "confirmed",
                    "name": {language: scenario_owner},
                    "definition": (
                        "Accountable owner of this Ontology Solution."
                        if language == "en"
                        else "本体解决方案的责任负责人。"
                    ),
                    "owner": owner_id,
                    "sources": ["source.solution_brief"],
                    "decisions": [],
                    "tags": ["governance:solution-owner"],
                    "roles": ["ontology_solution_owner"],
                }
            )
            base = base.model_copy(update={"actors": (*base.actors, owner)})
            scenario_owner = owner_id
        scenario = base.scenario.model_copy(
            update={
                "definition": workspace.solution_intent,
                "owner": scenario_owner,
            }
        )
        candidate = base.model_copy(
            update={
                "version": workspace.target_version,
                "scenario": scenario,
                "authoring_policy": (
                    create_authoring_policy(workspace.authoring_language)
                    if workspace.authoring_language is not None
                    else base.authoring_policy
                ),
            }
        )
        return apply_package_operations(candidate, workspace.package_operations)

    def _new(self, workspace_id: str) -> GenericDraftWorkspace:
        base = self._base()
        releases = self.releases.list(base.package_id)
        target = _next_patch(releases[0].version) if releases else base.version
        now = datetime.now(timezone.utc)
        provisional = GenericDraftWorkspace(
            workspace_id=workspace_id,
            package_id=base.package_id,
            base_version=base.version,
            target_version=target,
            revision=1,
            created_at=now,
            updated_at=now,
            revision_created_at=now,
            solution_intent=base.scenario.definition,
            draft_checksum="0" * 64,
            validation=DraftValidation(status="NOT_RUN"),
        )
        return provisional.model_copy(
            update={"draft_checksum": package_checksum(self._candidate(provisional))}
        )

    def _ensure(self, workspace_id: str) -> GenericDraftWorkspace:
        current = self._read(workspace_id)
        if current is not None:
            return current
        created = self._new(workspace_id)
        try:
            self._write(created)
        except WorkspaceConflictError:
            concurrent = self._read(workspace_id)
            if concurrent is None:
                raise
            return concurrent
        return created

    def get(self, workspace_id: str | None = None) -> GenericDraftWorkspace:
        resolved = self._workspace_id(workspace_id)
        with self._lock(resolved):
            return self._ensure(resolved)

    def candidate_package(
        self, workspace_id: str | None = None
    ) -> OntologyPackage:
        return self._candidate(self.get(workspace_id))

    def get_intake(self, workspace_id: str | None = None) -> GenericIntakeSnapshot:
        resolved = self._workspace_id(workspace_id)
        checksum = sha256_value({"workspace_id": resolved, "assets": []})
        return GenericIntakeSnapshot(
            workspace_id=resolved,
            submission_id=f"intake.{checksum[:24]}",
            content_checksum=checksum,
        )

    def update_intent(
        self,
        value: str,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> GenericDraftWorkspace:
        resolved = self._workspace_id(workspace_id)
        normalized = value.strip()
        if not normalized:
            raise WorkspaceStateError("Solution intent cannot be empty")
        with self._lock(resolved):
            current = self._ensure(resolved)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            if current.solution_intent == normalized:
                return current
            now = datetime.now(timezone.utc)
            provisional = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "solution_intent": normalized,
                    "modified_fields": ("solution_intent",),
                    "validation": DraftValidation(status="STALE"),
                }
            )
            updated = provisional.model_copy(
                update={"draft_checksum": package_checksum(self._candidate(provisional))}
            )
            self._write(updated)
            return updated

    def configure_authoring_language(
        self,
        language: AuthoringLanguage,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> GenericDraftWorkspace:
        """Set the Solution language once, before confirmed package assets exist."""

        resolved = self._workspace_id(workspace_id)
        with self._lock(resolved):
            current = self._ensure(resolved)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            if current.authoring_language is not None:
                if current.authoring_language != language:
                    raise WorkspaceConflictError(
                        "Ontology authoring language is locked for this Solution"
                    )
                return current
            if current.package_operations:
                raise WorkspaceConflictError(
                    "Ontology authoring language must be set before semantic assets"
                )
            policy = create_authoring_policy(language)
            now = datetime.now(timezone.utc)
            provisional = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "authoring_language": language,
                    "language_policy_digest": policy.policy_digest,
                    "modified_fields": tuple(
                        sorted({*current.modified_fields, "authoring_language"})
                    ),
                    "validation": DraftValidation(status="STALE"),
                }
            )
            updated = provisional.model_copy(
                update={"draft_checksum": package_checksum(self._candidate(provisional))}
            )
            self._write(updated)
            return updated

    def apply_package_operations(
        self,
        request: PackageDraftOperationsV1 | ReviewFinalizationOperationsV1,
        *,
        workspace_id: str | None = None,
        transaction_hook_factory: (
            Callable[[GenericDraftWorkspace], Callable[[Any], None]] | None
        ) = None,
    ) -> GenericDraftWorkspace:
        resolved = self._workspace_id(workspace_id)
        with self._lock(resolved):
            current = self._ensure(resolved)
            if current.revision != request.expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            operations = (*current.package_operations, *request.operations)
            target = current.target_version
            if current.last_published is not None and (
                current.last_published.version == target
            ):
                target = _next_patch(target)
            now = datetime.now(timezone.utc)
            provisional = current.model_copy(
                update={
                    "target_version": target,
                    "revision": current.revision + 1,
                    "updated_at": now,
                    "revision_created_at": now,
                    "package_operations": operations,
                    "modified_fields": tuple(
                        sorted(
                            {
                                *current.modified_fields,
                                *(f"{item.collection}.{item.object_id}" for item in request.operations),
                            }
                        )
                    ),
                    "validation": DraftValidation(status="STALE"),
                }
            )
            updated = provisional.model_copy(
                update={"draft_checksum": package_checksum(self._candidate(provisional))}
            )
            hook = (
                transaction_hook_factory(updated)
                if transaction_hook_factory is not None
                else None
            )
            self._write(updated, transaction_hook=hook)
            return updated

    def list_revisions(
        self, workspace_id: str | None = None
    ) -> tuple[GenericDraftRevision, ...]:
        resolved = self._workspace_id(workspace_id)
        self.get(resolved)
        if self.state_store is not None and self.identity is not None:
            try:
                return tuple(
                    _validated_revision(record.subject.payload)
                    for record in self.state_store.list_revisions(self.identity)
                )
            except (WorkspaceStoreError, ValueError) as exc:
                raise WorkspaceUnavailableError(
                    "Generic revision history is invalid"
                ) from exc
        revision_root = self._directory(resolved) / "revisions"
        try:
            return tuple(
                _validated_revision(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(revision_root.glob("r*.json"))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise WorkspaceStateError("Generic revision history is invalid") from exc

    def validate(
        self,
        *,
        expected_revision: int,
        workspace_id: str | None = None,
    ) -> GenericDraftWorkspace:
        resolved = self._workspace_id(workspace_id)
        with self._lock(resolved):
            current = self._ensure(resolved)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            report = validate_semantic_package(self._candidate(current))
            updated = current.model_copy(
                update={
                    "updated_at": datetime.now(timezone.utc),
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
    ) -> tuple[GenericDraftWorkspace, PublishedReleaseHandle]:
        resolved = self._workspace_id(workspace_id)
        with self._lock(resolved):
            current = self._ensure(resolved)
            if current.revision != expected_revision:
                raise WorkspaceConflictError("Draft revision conflict")
            if (
                current.validation.status != "PASS"
                or current.validation.revision != current.revision
                or current.validation.draft_checksum != current.draft_checksum
            ):
                raise WorkspaceStateError(
                    "The exact current Draft must pass validation before publication"
                )
            publication = self.releases.publish(
                self._candidate(current),
                limitations=(
                    "Human-reviewed analytical ontology; runtime activation is separate.",
                ),
            )
            updated = current.model_copy(
                update={
                    "updated_at": datetime.now(timezone.utc),
                    "last_published": publication.ref,
                }
            )
            self._write(updated)
            return updated, publication
