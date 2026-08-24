"""Persist Candidate continuation lineage on construction jobs.

Revision ID: 20260823_0019
Revises: 20260823_0018
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260823_0019"
down_revision: str | None = "20260823_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "studio_construction_job",
        sa.Column("resume_from_attempt_id", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("studio_construction_job", "resume_from_attempt_id")
