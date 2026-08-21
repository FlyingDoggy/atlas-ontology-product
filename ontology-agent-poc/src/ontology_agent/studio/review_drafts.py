from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy import DateTime, Integer, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..contracts import Sha256
from ..io import sha256_value
from ..models import StrictModel
from ..product_context import Base, ProductInfrastructureSettings
from .construction import ConstructionDispositionV1, ConstructionRunV1


class ReviewDraftError(RuntimeError):
    """A resumable review batch could not be read or changed safely."""


class ReviewDraftConflict(ReviewDraftError):
    """A review batch CAS or terminal-state check failed."""


class ReviewDraftSaveV1(StrictModel):
    contract: Literal["construction-review-draft-save/v1"] = (
        "construction-review-draft-save/v1"
    )
    expected_review_revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=255)
    dispositions: tuple[ConstructionDispositionV1, ...]


class ConstructionReviewDraftV1(StrictModel):
    contract: Literal["construction-review-draft/v1"] = (
        "construction-review-draft/v1"
    )
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    run_checksum: Sha256
    workspace_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)
    review_revision: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=255)
    dispositions: tuple[ConstructionDispositionV1, ...]
    status: Literal["DRAFT", "FINAL"]
    submitted_batch_checksum: Sha256 | None = None
    final_decision_id: str | None = Field(
        default=None, pattern=r"^construction-decision\.[0-9a-f]{32}$"
    )
    updated_at: datetime
    batch_checksum: Sha256

    @model_validator(mode="after")
    def coherent_batch(self) -> ConstructionReviewDraftV1:
        ids = [item.candidate_id for item in self.dispositions]
        if len(ids) != len(set(ids)):
            raise ValueError("Review draft has duplicate candidate dispositions")
        if (self.status == "FINAL") != (self.final_decision_id is not None):
            raise ValueError("Final review draft must bind one final decision")
        if (self.status == "FINAL") != (self.submitted_batch_checksum is not None):
            raise ValueError("Final review draft must retain submitted batch identity")
        unsigned = self.model_dump(
            mode="json", exclude={"batch_checksum"}, exclude_none=True
        )
        if sha256_value(unsigned) != self.batch_checksum:
            raise ValueError("Review draft checksum mismatch")
        return self


class ReviewDraftStore(Protocol):
    def get(self, run_id: str) -> ConstructionReviewDraftV1 | None: ...

    def save(
        self, run: ConstructionRunV1, request: ReviewDraftSaveV1
    ) -> ConstructionReviewDraftV1: ...

    def finalization_hook(
        self, run_id: str, batch_checksum: str, decision_id: str
    ) -> Callable[[Session], None]: ...


def _build(
    run: ConstructionRunV1,
    request: ReviewDraftSaveV1,
    *,
    review_revision: int,
    updated_at: datetime,
) -> ConstructionReviewDraftV1:
    candidate_ids = {item.candidate_id for item in run.candidates}
    disposition_ids = {item.candidate_id for item in request.dispositions}
    if not disposition_ids.issubset(candidate_ids):
        raise ReviewDraftConflict("Review draft references an unknown candidate")
    unsigned = {
        "contract": "construction-review-draft/v1",
        "run_id": run.run_id,
        "run_checksum": run.run_checksum,
        "workspace_id": run.workspace_id,
        "base_revision": run.base_revision,
        "review_revision": review_revision,
        "reviewer": request.reviewer,
        "dispositions": request.dispositions,
        "status": "DRAFT",
        "updated_at": updated_at,
    }
    provisional = ConstructionReviewDraftV1.model_construct(
        **unsigned, batch_checksum="0" * 64
    )
    checksum_payload = provisional.model_dump(
        mode="json", exclude={"batch_checksum"}, exclude_none=True
    )
    return ConstructionReviewDraftV1(
        **unsigned, batch_checksum=sha256_value(checksum_payload)
    )


class InMemoryReviewDraftStore:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._values: dict[str, ConstructionReviewDraftV1] = {}
        self._lock = threading.RLock()

    def get(self, run_id: str) -> ConstructionReviewDraftV1 | None:
        return self._values.get(run_id)

    def save(
        self, run: ConstructionRunV1, request: ReviewDraftSaveV1
    ) -> ConstructionReviewDraftV1:
        with self._lock:
            existing = self.get(run.run_id)
            if existing and existing.status == "FINAL":
                raise ReviewDraftConflict("Review batch is already final")
            current_revision = existing.review_revision if existing else 0
            if request.expected_review_revision != current_revision:
                raise ReviewDraftConflict("Review draft revision conflict")
            if existing and (
                existing.reviewer == request.reviewer
                and existing.dispositions == request.dispositions
            ):
                return existing
            value = _build(
                run,
                request,
                review_revision=current_revision + 1,
                updated_at=self.clock(),
            )
            self._values[run.run_id] = value
            return value

    def finalization_hook(
        self, run_id: str, batch_checksum: str, decision_id: str
    ) -> Callable[[Session], None]:
        def finalize(session: Session) -> None:
            del session
            with self._lock:
                value = self.get(run_id)
                if value is None or value.batch_checksum != batch_checksum:
                    raise ReviewDraftConflict("Final review batch checksum mismatch")
                unsigned = value.model_dump(
                    mode="json", exclude={"batch_checksum"}, exclude_none=True
                )
                unsigned.update(
                    status="FINAL",
                    final_decision_id=decision_id,
                    submitted_batch_checksum=batch_checksum,
                )
                self._values[run_id] = ConstructionReviewDraftV1(
                    **unsigned, batch_checksum=sha256_value(unsigned)
                )

        return finalize


class StudioConstructionReviewDraftRow(Base):
    __tablename__ = "studio_construction_review_draft"

    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    final_decision_id: Mapped[str | None] = mapped_column(String(80))
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PostgresReviewDraftStore:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresReviewDraftStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise ReviewDraftError("Review draft storage requires PostgreSQL")
        return cls(settings.database_url)

    @staticmethod
    def _value(row: StudioConstructionReviewDraftRow) -> ConstructionReviewDraftV1:
        try:
            value = ConstructionReviewDraftV1.model_validate(row.subject)
        except ValueError as exc:
            raise ReviewDraftError("Review draft subject is invalid") from exc
        if (
            row.batch_checksum != value.batch_checksum
            or row.review_revision != value.review_revision
            or row.status != value.status
            or row.final_decision_id != value.final_decision_id
        ):
            raise ReviewDraftError("Review draft database identity mismatch")
        return value

    def get(self, run_id: str) -> ConstructionReviewDraftV1 | None:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioConstructionReviewDraftRow, run_id)
                return self._value(row) if row else None
        except ReviewDraftError:
            raise
        except SQLAlchemyError as exc:
            raise ReviewDraftError("Review draft read failed") from exc

    def save(
        self, run: ConstructionRunV1, request: ReviewDraftSaveV1
    ) -> ConstructionReviewDraftV1:
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(StudioConstructionReviewDraftRow)
                    .where(StudioConstructionReviewDraftRow.run_id == run.run_id)
                    .with_for_update()
                )
                existing = self._value(row) if row else None
                if existing and existing.status == "FINAL":
                    raise ReviewDraftConflict("Review batch is already final")
                current_revision = existing.review_revision if existing else 0
                if request.expected_review_revision != current_revision:
                    raise ReviewDraftConflict("Review draft revision conflict")
                if existing and (
                    existing.reviewer == request.reviewer
                    and existing.dispositions == request.dispositions
                ):
                    return existing
                value = _build(
                    run,
                    request,
                    review_revision=current_revision + 1,
                    updated_at=datetime.now(timezone.utc),
                )
                if row is None:
                    row = StudioConstructionReviewDraftRow(
                        run_id=value.run_id,
                        workspace_id=value.workspace_id,
                        run_checksum=value.run_checksum,
                        review_revision=value.review_revision,
                        batch_checksum=value.batch_checksum,
                        status=value.status,
                        final_decision_id=None,
                        subject=value.model_dump(mode="json"),
                        updated_at=value.updated_at,
                    )
                    session.add(row)
                else:
                    row.review_revision = value.review_revision
                    row.batch_checksum = value.batch_checksum
                    row.subject = value.model_dump(mode="json")
                    row.updated_at = value.updated_at
                session.flush()
                return value
        except ReviewDraftError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise ReviewDraftError("Review draft CAS failed") from exc

    def finalization_hook(
        self, run_id: str, batch_checksum: str, decision_id: str
    ) -> Callable[[Session], None]:
        def finalize(session: Session) -> None:
            row = session.scalar(
                select(StudioConstructionReviewDraftRow)
                .where(StudioConstructionReviewDraftRow.run_id == run_id)
                .with_for_update()
            )
            if row is None or row.batch_checksum != batch_checksum or row.status != "DRAFT":
                raise ReviewDraftConflict("Final review batch checksum mismatch")
            current = self._value(row)
            unsigned = current.model_dump(
                mode="json", exclude={"batch_checksum"}, exclude_none=True
            )
            unsigned.update(
                status="FINAL",
                final_decision_id=decision_id,
                submitted_batch_checksum=batch_checksum,
            )
            final = ConstructionReviewDraftV1(
                **unsigned, batch_checksum=sha256_value(unsigned)
            )
            row.status = "FINAL"
            row.final_decision_id = decision_id
            row.batch_checksum = final.batch_checksum
            row.subject = final.model_dump(mode="json")
            row.updated_at = final.updated_at

        return finalize
