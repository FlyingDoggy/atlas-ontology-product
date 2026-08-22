"""Add fenced construction job progress snapshots.

Revision ID: 20260822_0016
Revises: 20260822_0015
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260822_0016"
down_revision: str | None = "20260822_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "studio_construction_job",
        sa.Column("current_stage", sa.String(length=64), server_default="QUEUED", nullable=False),
    )
    op.add_column(
        "studio_construction_job",
        sa.Column("completed_stages", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "studio_construction_job",
        sa.Column("total_stages", sa.Integer(), server_default="6", nullable=False),
    )
    op.add_column(
        "studio_construction_job",
        sa.Column("progress_message", sa.String(length=100), server_default="JOB_QUEUED", nullable=False),
    )
    op.create_check_constraint(
        "ck_studio_construction_job_progress_range",
        "studio_construction_job",
        "completed_stages >= 0 AND total_stages > 0 AND completed_stages <= total_stages",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_studio_construction_job_progress_range",
        "studio_construction_job",
        type_="check",
    )
    op.drop_column("studio_construction_job", "progress_message")
    op.drop_column("studio_construction_job", "total_stages")
    op.drop_column("studio_construction_job", "completed_stages")
    op.drop_column("studio_construction_job", "current_stage")
