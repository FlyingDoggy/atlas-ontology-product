from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .contracts import Sha256
from .models import StrictModel
from .product_context import Base, ProductInfrastructureSettings


class AnalyticConversationError(RuntimeError):
    """An analytic conversation could not be read or committed safely."""


class AnalyticConversationConflict(AnalyticConversationError):
    """A conversation ID was reused across incompatible solution scopes."""


class AnalyticConversationContextV1(StrictModel):
    """Small durable context needed to resolve an elliptical analytic follow-up.

    This is intentionally not a transcript.  It records the governed parameters
    selected by the previous execution so the next turn can inherit omitted
    metric, period, dimensions and filters without treating prose as a fact.
    """

    contract: Literal["analytic-conversation-context/v1"] = (
        "analytic-conversation-context/v1"
    )
    metric_id: str | None = Field(default=None, min_length=1, max_length=255)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    dimensions: tuple[str, ...] = Field(default=(), max_length=2)
    filters: dict[str, str] = Field(default_factory=dict)
    role: str = Field(min_length=1, max_length=100)
    last_execution_id: str | None = Field(
        default=None, pattern=r"^exec\.[0-9a-f]{32}$"
    )

    @model_validator(mode="after")
    def coherent_period(self) -> AnalyticConversationContextV1:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Conversation period requires both start and end dates")
        if self.start_date is not None and self.end_date is not None:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
            if start > end:
                raise ValueError("Conversation period start cannot be after end")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("Conversation dimensions must be unique")
        return self


class AnalyticTurnLeaseV1(StrictModel):
    contract: Literal["analytic-turn-lease/v1"] = "analytic-turn-lease/v1"
    conversation_id: str = Field(pattern=r"^conversation\.[0-9a-f]{32}$")
    turn_id: str = Field(pattern=r"^turn\.[0-9a-f]{32}$")
    turn_index: int = Field(ge=1)
    solution_id: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=100)
    snapshot_checksum: Sha256
    question: str = Field(min_length=1, max_length=1000)
    context_before: AnalyticConversationContextV1
    parent_execution_id: str | None = Field(
        default=None, pattern=r"^exec\.[0-9a-f]{32}$"
    )

    def response_fields(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "turn_index": self.turn_index,
            "parent_execution_id": self.parent_execution_id,
        }


class AnalyticTurnRecordV1(StrictModel):
    contract: Literal["analytic-turn-record/v1"] = "analytic-turn-record/v1"
    conversation_id: str = Field(pattern=r"^conversation\.[0-9a-f]{32}$")
    turn_id: str = Field(pattern=r"^turn\.[0-9a-f]{32}$")
    turn_index: int = Field(ge=1)
    solution_id: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=100)
    snapshot_checksum: Sha256
    question: str = Field(min_length=1, max_length=1000)
    status: Literal["ANSWERED", "CLARIFY", "REFUSED", "NO_DATA", "FAILED"]
    execution_id: str | None = Field(
        default=None, pattern=r"^exec\.[0-9a-f]{32}$"
    )
    parent_execution_id: str | None = Field(
        default=None, pattern=r"^exec\.[0-9a-f]{32}$"
    )
    context_before: AnalyticConversationContextV1
    context_after: AnalyticConversationContextV1
    response_payload: dict[str, Any] | None = None
    completed_at: datetime


class AnalyticConversationStore(Protocol):
    def begin_turn(
        self,
        *,
        conversation_id: str | None,
        solution_id: str,
        role: str,
        snapshot_checksum: Sha256,
        question: str,
    ) -> AnalyticTurnLeaseV1: ...

    def complete_turn(
        self,
        lease: AnalyticTurnLeaseV1,
        *,
        status: Literal["ANSWERED", "CLARIFY", "REFUSED", "NO_DATA", "FAILED"],
        execution_id: str | None,
        context_after: AnalyticConversationContextV1,
        response_payload: dict[str, Any],
    ) -> AnalyticTurnRecordV1: ...

    def turns(
        self, conversation_id: str, *, solution_id: str
    ) -> tuple[AnalyticTurnRecordV1, ...]: ...


@dataclass
class _MemoryConversation:
    solution_id: str
    role: str
    snapshot_checksum: str
    turn_count: int
    completed_turn_count: int
    context: AnalyticConversationContextV1


class InMemoryAnalyticConversationStore:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._conversations: dict[str, _MemoryConversation] = {}
        self._leases: dict[str, AnalyticTurnLeaseV1] = {}
        self._turns: dict[str, AnalyticTurnRecordV1] = {}
        self._lock = threading.RLock()

    def begin_turn(
        self,
        *,
        conversation_id: str | None,
        solution_id: str,
        role: str,
        snapshot_checksum: Sha256,
        question: str,
    ) -> AnalyticTurnLeaseV1:
        resolved_id = conversation_id or "conversation." + uuid.uuid4().hex
        with self._lock:
            current = self._conversations.get(resolved_id)
            if current is None:
                context = AnalyticConversationContextV1(role=role)
                current = _MemoryConversation(
                    solution_id=solution_id,
                    role=role,
                    snapshot_checksum=snapshot_checksum,
                    turn_count=0,
                    completed_turn_count=0,
                    context=context,
                )
                self._conversations[resolved_id] = current
            elif current.solution_id != solution_id:
                raise AnalyticConversationConflict(
                    "Conversation belongs to a different ontology solution"
                )
            context_before = current.context.model_copy(update={"role": role})
            current.turn_count += 1
            current.role = role
            current.snapshot_checksum = snapshot_checksum
            lease = AnalyticTurnLeaseV1(
                conversation_id=resolved_id,
                turn_id="turn." + uuid.uuid4().hex,
                turn_index=current.turn_count,
                solution_id=solution_id,
                role=role,
                snapshot_checksum=snapshot_checksum,
                question=question,
                context_before=context_before,
                parent_execution_id=context_before.last_execution_id,
            )
            self._leases[lease.turn_id] = lease
            return lease

    def complete_turn(
        self,
        lease: AnalyticTurnLeaseV1,
        *,
        status: Literal["ANSWERED", "CLARIFY", "REFUSED", "NO_DATA", "FAILED"],
        execution_id: str | None,
        context_after: AnalyticConversationContextV1,
        response_payload: dict[str, Any],
    ) -> AnalyticTurnRecordV1:
        with self._lock:
            stored = self._leases.get(lease.turn_id)
            current = self._conversations.get(lease.conversation_id)
            if stored != lease or current is None:
                raise AnalyticConversationConflict("Unknown analytic turn lease")
            if lease.turn_id in self._turns:
                raise AnalyticConversationConflict("Analytic turn is already complete")
            completed_at = self.clock()
            record = AnalyticTurnRecordV1(
                conversation_id=lease.conversation_id,
                turn_id=lease.turn_id,
                turn_index=lease.turn_index,
                solution_id=lease.solution_id,
                role=lease.role,
                snapshot_checksum=lease.snapshot_checksum,
                question=lease.question,
                status=status,
                execution_id=execution_id,
                parent_execution_id=lease.parent_execution_id,
                context_before=lease.context_before,
                context_after=context_after,
                response_payload=response_payload,
                completed_at=completed_at,
            )
            self._turns[lease.turn_id] = record
            if lease.turn_index >= current.completed_turn_count:
                current.completed_turn_count = lease.turn_index
                current.context = context_after
            return record

    def context(self, conversation_id: str) -> AnalyticConversationContextV1 | None:
        current = self._conversations.get(conversation_id)
        return current.context if current is not None else None

    def turns(
        self, conversation_id: str, *, solution_id: str
    ) -> tuple[AnalyticTurnRecordV1, ...]:
        current = self._conversations.get(conversation_id)
        if current is None:
            return ()
        if current.solution_id != solution_id:
            raise AnalyticConversationConflict(
                "Conversation belongs to a different ontology solution"
            )
        return tuple(
            sorted(
                (
                    item
                    for item in self._turns.values()
                    if item.conversation_id == conversation_id
                ),
                key=lambda item: item.turn_index,
            )
        )


class AnalyticConversationRow(Base):
    __tablename__ = "analytic_conversation"

    conversation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_execution_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    context: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AnalyticConversationTurnRow(Base):
    __tablename__ = "analytic_conversation_turn"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "turn_index", name="uq_analytic_conversation_turn_index"
        ),
    )

    turn_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("analytic_conversation.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parent_execution_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    context_before: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    context_after: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PostgresAnalyticConversationStore:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresAnalyticConversationStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise AnalyticConversationError(
                "Analytic conversation storage requires PostgreSQL"
            )
        return cls(settings.database_url)

    @staticmethod
    def _context(value: dict[str, object]) -> AnalyticConversationContextV1:
        try:
            return AnalyticConversationContextV1.model_validate(value)
        except ValueError as exc:
            raise AnalyticConversationError(
                "Stored analytic conversation context is invalid"
            ) from exc

    def begin_turn(
        self,
        *,
        conversation_id: str | None,
        solution_id: str,
        role: str,
        snapshot_checksum: Sha256,
        question: str,
    ) -> AnalyticTurnLeaseV1:
        resolved_id = conversation_id or "conversation." + uuid.uuid4().hex
        turn_id = "turn." + uuid.uuid4().hex
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(AnalyticConversationRow)
                    .where(AnalyticConversationRow.conversation_id == resolved_id)
                    .with_for_update()
                )
                if row is None:
                    context_before = AnalyticConversationContextV1(role=role)
                    row = AnalyticConversationRow(
                        conversation_id=resolved_id,
                        solution_id=solution_id,
                        role=role,
                        snapshot_checksum=snapshot_checksum,
                        turn_count=1,
                        completed_turn_count=0,
                        context=context_before.model_dump(mode="json"),
                    )
                    session.add(row)
                    turn_index = 1
                else:
                    if row.solution_id != solution_id:
                        raise AnalyticConversationConflict(
                            "Conversation belongs to a different ontology solution"
                        )
                    context_before = self._context(row.context).model_copy(
                        update={"role": role}
                    )
                    turn_index = row.turn_count + 1
                    row.turn_count = turn_index
                    row.role = role
                    row.snapshot_checksum = snapshot_checksum
                lease = AnalyticTurnLeaseV1(
                    conversation_id=resolved_id,
                    turn_id=turn_id,
                    turn_index=turn_index,
                    solution_id=solution_id,
                    role=role,
                    snapshot_checksum=snapshot_checksum,
                    question=question,
                    context_before=context_before,
                    parent_execution_id=context_before.last_execution_id,
                )
                session.add(
                    AnalyticConversationTurnRow(
                        turn_id=turn_id,
                        conversation_id=resolved_id,
                        turn_index=turn_index,
                        solution_id=solution_id,
                        role=role,
                        snapshot_checksum=snapshot_checksum,
                        question=question,
                        status="RUNNING",
                        parent_execution_id=lease.parent_execution_id,
                        context_before=context_before.model_dump(mode="json"),
                    )
                )
                session.flush()
                return lease
        except AnalyticConversationError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise AnalyticConversationError(
                "Analytic conversation turn could not be started"
            ) from exc

    def complete_turn(
        self,
        lease: AnalyticTurnLeaseV1,
        *,
        status: Literal["ANSWERED", "CLARIFY", "REFUSED", "NO_DATA", "FAILED"],
        execution_id: str | None,
        context_after: AnalyticConversationContextV1,
        response_payload: dict[str, Any],
    ) -> AnalyticTurnRecordV1:
        completed_at = datetime.now(timezone.utc)
        try:
            with Session(self.engine) as session, session.begin():
                conversation = session.scalar(
                    select(AnalyticConversationRow)
                    .where(
                        AnalyticConversationRow.conversation_id
                        == lease.conversation_id
                    )
                    .with_for_update()
                )
                turn = session.scalar(
                    select(AnalyticConversationTurnRow)
                    .where(AnalyticConversationTurnRow.turn_id == lease.turn_id)
                    .with_for_update()
                )
                if conversation is None or turn is None:
                    raise AnalyticConversationConflict("Unknown analytic turn lease")
                if (
                    turn.conversation_id != lease.conversation_id
                    or turn.turn_index != lease.turn_index
                    or turn.status != "RUNNING"
                ):
                    raise AnalyticConversationConflict(
                        "Analytic turn lease no longer owns the pending turn"
                    )
                turn.status = status
                turn.execution_id = execution_id
                turn.context_after = context_after.model_dump(mode="json")
                turn.response_payload = response_payload
                turn.completed_at = completed_at
                if lease.turn_index >= conversation.completed_turn_count:
                    conversation.completed_turn_count = lease.turn_index
                    conversation.last_execution_id = context_after.last_execution_id
                    conversation.context = context_after.model_dump(mode="json")
                session.flush()
        except AnalyticConversationError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise AnalyticConversationError(
                "Analytic conversation turn could not be completed"
            ) from exc
        return AnalyticTurnRecordV1(
            conversation_id=lease.conversation_id,
            turn_id=lease.turn_id,
            turn_index=lease.turn_index,
            solution_id=lease.solution_id,
            role=lease.role,
            snapshot_checksum=lease.snapshot_checksum,
            question=lease.question,
            status=status,
            execution_id=execution_id,
            parent_execution_id=lease.parent_execution_id,
            context_before=lease.context_before,
            context_after=context_after,
            response_payload=response_payload,
            completed_at=completed_at,
        )

    def turns(
        self, conversation_id: str, *, solution_id: str
    ) -> tuple[AnalyticTurnRecordV1, ...]:
        try:
            with Session(self.engine) as session:
                conversation = session.scalar(
                    select(AnalyticConversationRow).where(
                        AnalyticConversationRow.conversation_id == conversation_id
                    )
                )
                if conversation is None:
                    return ()
                if conversation.solution_id != solution_id:
                    raise AnalyticConversationConflict(
                        "Conversation belongs to a different ontology solution"
                    )
                rows = session.scalars(
                    select(AnalyticConversationTurnRow)
                    .where(
                        AnalyticConversationTurnRow.conversation_id == conversation_id,
                        AnalyticConversationTurnRow.completed_at.is_not(None),
                        AnalyticConversationTurnRow.context_after.is_not(None),
                    )
                    .order_by(AnalyticConversationTurnRow.turn_index)
                ).all()
                return tuple(
                    AnalyticTurnRecordV1(
                        conversation_id=row.conversation_id,
                        turn_id=row.turn_id,
                        turn_index=row.turn_index,
                        solution_id=row.solution_id,
                        role=row.role,
                        snapshot_checksum=row.snapshot_checksum,
                        question=row.question,
                        status=row.status,
                        execution_id=row.execution_id,
                        parent_execution_id=row.parent_execution_id,
                        context_before=self._context(row.context_before),
                        context_after=self._context(row.context_after or {}),
                        response_payload=row.response_payload,
                        completed_at=row.completed_at,
                    )
                    for row in rows
                )
        except AnalyticConversationError:
            raise
        except SQLAlchemyError as exc:
            raise AnalyticConversationError(
                "Analytic conversation transcript could not be read"
            ) from exc
