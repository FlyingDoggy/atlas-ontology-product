"""Persist analytic conversation context and per-turn execution lineage.

Revision ID: 20260825_0020
Revises: 20260823_0019
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0020"
down_revision: str | None = "20260823_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytic_conversation",
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("completed_turn_count", sa.Integer(), nullable=False),
        sa.Column("last_execution_id", sa.String(length=80), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_analytic_conversation_solution_id",
        "analytic_conversation",
        ["solution_id"],
        unique=False,
    )
    op.create_table(
        "analytic_conversation_turn",
        sa.Column("turn_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("execution_id", sa.String(length=80), nullable=True),
        sa.Column("parent_execution_id", sa.String(length=80), nullable=True),
        sa.Column(
            "context_before", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "context_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["analytic_conversation.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id"),
        sa.UniqueConstraint(
            "conversation_id",
            "turn_index",
            name="uq_analytic_conversation_turn_index",
        ),
    )
    op.create_index(
        "ix_analytic_conversation_turn_conversation_id",
        "analytic_conversation_turn",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analytic_conversation_turn_conversation_id",
        table_name="analytic_conversation_turn",
    )
    op.drop_table("analytic_conversation_turn")
    op.drop_index(
        "ix_analytic_conversation_solution_id", table_name="analytic_conversation"
    )
    op.drop_table("analytic_conversation")
