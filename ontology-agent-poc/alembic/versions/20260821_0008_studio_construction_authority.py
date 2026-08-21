"""Add durable Studio construction run and review authority.

Revision ID: 20260821_0008
Revises: 20260820_0007
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260821_0008"
down_revision: str | None = "20260820_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_construction_run",
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("run_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "subject",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "artifact",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(run_checksum) = 64 AND char_length(subject_checksum) = 64",
            name="ck_studio_construction_run_checksum_lengths",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_studio_construction_run"),
        sa.UniqueConstraint(
            "run_checksum", name="uq_studio_construction_run_checksum"
        ),
        sa.UniqueConstraint(
            "subject_checksum", name="uq_studio_construction_run_subject_checksum"
        ),
    )
    op.create_index(
        "ix_studio_construction_run_workspace",
        "studio_construction_run",
        ["workspace_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "studio_construction_decision",
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("decision_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("decision_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "subject",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "artifact",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(request_digest) = 64 AND char_length(decision_checksum) = 64 "
            "AND char_length(subject_checksum) = 64",
            name="ck_studio_construction_decision_checksum_lengths",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["studio_construction_run.run_id"],
            name="fk_studio_construction_decision_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", name="pk_studio_construction_decision"
        ),
        sa.UniqueConstraint(
            "decision_id", name="uq_studio_construction_decision_id"
        ),
        sa.UniqueConstraint(
            "decision_checksum", name="uq_studio_construction_decision_checksum"
        ),
        sa.UniqueConstraint(
            "subject_checksum",
            name="uq_studio_construction_decision_subject_checksum",
        ),
    )
    op.create_index(
        "ix_studio_construction_decision_workspace",
        "studio_construction_decision",
        ["workspace_id", "decided_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_construction_decision_workspace",
        table_name="studio_construction_decision",
    )
    op.drop_table("studio_construction_decision")
    op.drop_index(
        "ix_studio_construction_run_workspace",
        table_name="studio_construction_run",
    )
    op.drop_table("studio_construction_run")
