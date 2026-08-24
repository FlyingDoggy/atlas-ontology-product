"""Freeze Agent Engine Contract and Build Objective on construction jobs.

Revision ID: 20260823_0018
Revises: 20260823_0017
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260823_0018"
down_revision: str | None = "20260823_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "studio_construction_job",
        sa.Column(
            "engine_contract",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "studio_construction_job",
        sa.Column(
            "build_objective",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_studio_construction_job_agentic_pair",
        "studio_construction_job",
        "(engine_contract IS NULL) = (build_objective IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_studio_construction_job_agentic_pair",
        "studio_construction_job",
        type_="check",
    )
    op.drop_column("studio_construction_job", "build_objective")
    op.drop_column("studio_construction_job", "engine_contract")
