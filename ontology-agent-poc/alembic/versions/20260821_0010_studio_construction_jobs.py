"""Add durable construction job/outbox authority.

Revision ID: 20260821_0010
Revises: 20260821_0009
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260821_0010"
down_revision: str | None = "20260821_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_construction_job",
        sa.Column("job_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("base_draft_checksum", sa.String(length=64), nullable=False),
        sa.Column("source_set_digest", sa.String(length=64), nullable=False),
        sa.Column("profile_ref", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=80), nullable=True),
        sa.Column("lease_epoch", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_run_id", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(base_draft_checksum) = 64 AND char_length(source_set_digest) = 64",
            name="ck_studio_construction_job_checksum_lengths",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMMITTING','CANCEL_REQUESTED','SUCCEEDED','FAILED','CANCELLED','STALE')",
            name="ck_studio_construction_job_status",
        ),
        sa.CheckConstraint(
            "lease_epoch >= 0",
            name="ck_studio_construction_job_lease_epoch",
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_studio_construction_job"),
        sa.UniqueConstraint("run_id", name="uq_studio_construction_job_run"),
    )
    op.create_index(
        "ix_studio_construction_job_workspace_created",
        "studio_construction_job",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_studio_construction_job_one_active_workspace",
        "studio_construction_job",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('QUEUED','RUNNING','COMMITTING','CANCEL_REQUESTED')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_studio_construction_job_one_active_workspace",
        table_name="studio_construction_job",
    )
    op.drop_index(
        "ix_studio_construction_job_workspace_created",
        table_name="studio_construction_job",
    )
    op.drop_table("studio_construction_job")
