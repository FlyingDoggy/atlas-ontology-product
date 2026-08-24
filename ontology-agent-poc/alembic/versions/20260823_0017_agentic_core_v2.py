"""Add durable Agentic Builder checkpoint and execution journal.

Revision ID: 20260823_0017
Revises: 20260822_0016
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260823_0017"
down_revision: str | None = "20260822_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_agent_attempt",
        sa.Column("attempt_id", sa.String(length=80), nullable=False),
        sa.Column("job_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("lease_epoch", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=False),
        sa.Column("candidate_revision", sa.Integer(), nullable=False),
        sa.Column("step_sequence", sa.Integer(), nullable=False),
        sa.Column("state_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lease_epoch >= 1 AND candidate_revision >= 0 AND step_sequence >= 0",
            name="ck_studio_agent_attempt_counters",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["studio_construction_job.job_id"],
            name="fk_studio_agent_attempt_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id", name="pk_studio_agent_attempt"),
        sa.UniqueConstraint("run_id", name="uq_studio_agent_attempt_run"),
    )
    op.create_index(
        "ix_studio_agent_attempt_job_id",
        "studio_agent_attempt",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_studio_agent_attempt_workspace_id",
        "studio_agent_attempt",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "studio_agent_model_turn",
        sa.Column("turn_id", sa.String(length=80), nullable=False),
        sa.Column("attempt_id", sa.String(length=80), nullable=False),
        sa.Column("lease_epoch", sa.Integer(), nullable=False),
        sa.Column("step_sequence", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lease_epoch >= 1 AND step_sequence >= 1 AND char_length(request_digest) = 64",
            name="ck_studio_agent_model_turn_shape",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["studio_agent_attempt.attempt_id"],
            name="fk_studio_agent_model_turn_attempt",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id", name="pk_studio_agent_model_turn"),
        sa.UniqueConstraint(
            "attempt_id",
            "request_digest",
            name="uq_studio_agent_model_turn_request",
        ),
    )
    op.create_index(
        "ix_studio_agent_model_turn_attempt_id",
        "studio_agent_model_turn",
        ["attempt_id"],
        unique=False,
    )

    op.create_table(
        "studio_agent_tool_receipt",
        sa.Column("receipt_id", sa.String(length=80), nullable=False),
        sa.Column("attempt_id", sa.String(length=80), nullable=False),
        sa.Column("lease_epoch", sa.Integer(), nullable=False),
        sa.Column("step_sequence", sa.Integer(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=500), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("arguments_digest", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lease_epoch >= 1 AND step_sequence >= 1 AND char_length(arguments_digest) = 64",
            name="ck_studio_agent_tool_receipt_shape",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["studio_agent_attempt.attempt_id"],
            name="fk_studio_agent_tool_receipt_attempt",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("receipt_id", name="pk_studio_agent_tool_receipt"),
        sa.UniqueConstraint(
            "attempt_id",
            "tool_call_id",
            name="uq_studio_agent_tool_receipt_call",
        ),
    )
    op.create_index(
        "ix_studio_agent_tool_receipt_attempt_id",
        "studio_agent_tool_receipt",
        ["attempt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_agent_tool_receipt_attempt_id",
        table_name="studio_agent_tool_receipt",
    )
    op.drop_table("studio_agent_tool_receipt")
    op.drop_index(
        "ix_studio_agent_model_turn_attempt_id",
        table_name="studio_agent_model_turn",
    )
    op.drop_table("studio_agent_model_turn")
    op.drop_index(
        "ix_studio_agent_attempt_workspace_id",
        table_name="studio_agent_attempt",
    )
    op.drop_index(
        "ix_studio_agent_attempt_job_id",
        table_name="studio_agent_attempt",
    )
    op.drop_table("studio_agent_attempt")
