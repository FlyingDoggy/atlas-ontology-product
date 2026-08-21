from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal, Protocol

from pydantic import Field
from sqlalchemy import DateTime, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..io import write_json
from ..models import StrictModel
from ..product_context import Base, ProductInfrastructureSettings
from .solutions import SolutionDisplayName


class SolutionManagementError(RuntimeError):
    """A mutable Studio solution directory action could not be committed."""


class SolutionDirectoryEntryV1(StrictModel):
    contract: Literal["studio-solution-directory-entry/v1"] = (
        "studio-solution-directory-entry/v1"
    )
    solution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    status: Literal["ACTIVE", "ARCHIVED", "DELETED"] = "ACTIVE"
    display_name: SolutionDisplayName
    description: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=200)
    creation_mode: Literal["INSTALLED", "TEMPLATE", "IMPORT", "BLANK"]
    template_solution_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SolutionDirectoryPatchV1(StrictModel):
    display_name: SolutionDisplayName
    description: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=200)


class StudioSolutionDirectoryRow(Base):
    __tablename__ = "studio_solution_directory"

    solution_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    creation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    template_solution_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SolutionDirectoryStore(Protocol):
    def get(self, solution_id: str) -> SolutionDirectoryEntryV1 | None: ...

    def list(self) -> tuple[SolutionDirectoryEntryV1, ...]: ...

    def put(self, entry: SolutionDirectoryEntryV1) -> SolutionDirectoryEntryV1: ...


class PostgresSolutionDirectoryStore:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _entry(row: StudioSolutionDirectoryRow) -> SolutionDirectoryEntryV1:
        return SolutionDirectoryEntryV1(
            solution_id=row.solution_id,
            status=row.status,
            display_name=SolutionDisplayName.model_validate(row.display_name),
            description=row.description,
            owner=row.owner,
            creation_mode=row.creation_mode,
            template_solution_id=row.template_solution_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get(self, solution_id: str) -> SolutionDirectoryEntryV1 | None:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioSolutionDirectoryRow, solution_id)
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise SolutionManagementError("Solution directory lookup failed") from exc
        return self._entry(row) if row is not None else None

    def list(self) -> tuple[SolutionDirectoryEntryV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(StudioSolutionDirectoryRow).order_by(
                        StudioSolutionDirectoryRow.solution_id
                    )
                ).scalars().all()
                for row in rows:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise SolutionManagementError("Solution directory listing failed") from exc
        return tuple(self._entry(row) for row in rows)

    def put(self, entry: SolutionDirectoryEntryV1) -> SolutionDirectoryEntryV1:
        values = entry.model_dump(
            mode="json", exclude={"contract", "created_at", "updated_at"}
        )
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    pg_insert(StudioSolutionDirectoryRow)
                    .values(
                        **values,
                        created_at=entry.created_at,
                        updated_at=entry.updated_at,
                    )
                    .on_conflict_do_update(
                        index_elements=[StudioSolutionDirectoryRow.solution_id],
                        set_={
                            "status": entry.status,
                            "display_name": entry.display_name.model_dump(mode="json"),
                            "description": entry.description,
                            "owner": entry.owner,
                            "creation_mode": entry.creation_mode,
                            "template_solution_id": entry.template_solution_id,
                            "updated_at": entry.updated_at,
                        },
                    )
                )
        except SQLAlchemyError as exc:
            raise SolutionManagementError("Solution directory commit failed") from exc
        persisted = self.get(entry.solution_id)
        if persisted is None:
            raise SolutionManagementError("Solution directory commit disappeared")
        return persisted


class FileSolutionDirectoryStore:
    """Single-node compatibility store used by local development and unit tests."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(".lock")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, SolutionDirectoryEntryV1]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("contract") != "studio-solution-directory/v1":
                raise ValueError("wrong contract")
            entries = tuple(
                SolutionDirectoryEntryV1.model_validate(item)
                for item in payload.get("entries", [])
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SolutionManagementError("Local solution directory is invalid") from exc
        if len({item.solution_id for item in entries}) != len(entries):
            raise SolutionManagementError("Local solution directory has duplicate IDs")
        return {item.solution_id: item for item in entries}

    def _write(self, entries: dict[str, SolutionDirectoryEntryV1]) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        write_json(
            temporary,
            {
                "contract": "studio-solution-directory/v1",
                "entries": [
                    item.model_dump(mode="json")
                    for item in sorted(entries.values(), key=lambda value: value.solution_id)
                ],
            },
        )
        os.replace(temporary, self.path)

    def get(self, solution_id: str) -> SolutionDirectoryEntryV1 | None:
        with self._lock():
            return self._read().get(solution_id)

    def list(self) -> tuple[SolutionDirectoryEntryV1, ...]:
        with self._lock():
            return tuple(self._read().values())

    def put(self, entry: SolutionDirectoryEntryV1) -> SolutionDirectoryEntryV1:
        with self._lock():
            entries = self._read()
            entries[entry.solution_id] = entry
            self._write(entries)
        return entry


class SolutionDirectoryService:
    def __init__(self, store: SolutionDirectoryStore) -> None:
        self.store = store

    @classmethod
    def from_settings(
        cls,
        settings: ProductInfrastructureSettings,
        *,
        local_path: Path,
    ) -> SolutionDirectoryService:
        if settings.mode == "postgresql-s3":
            if not settings.database_url:
                raise SolutionManagementError(
                    "Durable solution directory settings are incomplete"
                )
            return cls(PostgresSolutionDirectoryStore(settings.database_url))
        return cls(FileSolutionDirectoryStore(local_path))

    def resolve(
        self,
        *,
        solution_id: str,
        fallback_name: SolutionDisplayName,
        fallback_description: str,
    ) -> SolutionDirectoryEntryV1:
        existing = self.store.get(solution_id)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc)
        return SolutionDirectoryEntryV1(
            solution_id=solution_id,
            status="ACTIVE",
            display_name=fallback_name,
            description=fallback_description,
            owner="Ontology Product Team",
            creation_mode="INSTALLED",
            created_at=now,
            updated_at=now,
        )

    def create(
        self,
        *,
        solution_id: str,
        display_name: SolutionDisplayName,
        description: str,
        owner: str,
        creation_mode: Literal["TEMPLATE", "IMPORT", "BLANK"] = "TEMPLATE",
        template_solution_id: str | None = None,
    ) -> SolutionDirectoryEntryV1:
        if self.store.get(solution_id) is not None:
            raise SolutionManagementError("Solution directory entry already exists")
        if creation_mode == "TEMPLATE" and template_solution_id is None:
            raise SolutionManagementError("Template creation requires a template")
        if creation_mode != "TEMPLATE" and template_solution_id is not None:
            raise SolutionManagementError(
                "Only template creation can retain a template identity"
            )
        now = datetime.now(timezone.utc)
        return self.store.put(
            SolutionDirectoryEntryV1(
                solution_id=solution_id,
                display_name=display_name,
                description=description,
                owner=owner,
                creation_mode=creation_mode,
                template_solution_id=template_solution_id,
                created_at=now,
                updated_at=now,
            )
        )

    def patch(
        self,
        current: SolutionDirectoryEntryV1,
        update: SolutionDirectoryPatchV1,
    ) -> SolutionDirectoryEntryV1:
        return self.store.put(
            current.model_copy(
                update={
                    "display_name": update.display_name,
                    "description": update.description,
                    "owner": update.owner,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        )

    def transition(
        self,
        current: SolutionDirectoryEntryV1,
        status: Literal["ACTIVE", "ARCHIVED", "DELETED"],
    ) -> SolutionDirectoryEntryV1:
        if current.status == "DELETED":
            raise SolutionManagementError("Deleted solutions cannot transition")
        if current.status == status:
            return current
        return self.store.put(
            current.model_copy(
                update={"status": status, "updated_at": datetime.now(timezone.utc)}
            )
        )
