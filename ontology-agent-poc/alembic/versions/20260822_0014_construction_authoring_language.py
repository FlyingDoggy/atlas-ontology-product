"""Freeze the ontology authoring language on durable construction jobs.

Revision ID: 20260822_0014
Revises: 20260821_0013
Create Date: 2026-08-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260822_0014"
down_revision: str | None = "20260821_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "studio_construction_job",
        sa.Column("authoring_language", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "studio_construction_job",
        sa.Column("language_policy_digest", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_studio_construction_job_authoring_language",
        "studio_construction_job",
        "authoring_language IS NULL OR authoring_language IN ('en', 'zh')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_studio_construction_job_authoring_language",
        "studio_construction_job",
        type_="check",
    )
    op.drop_column("studio_construction_job", "language_policy_digest")
    op.drop_column("studio_construction_job", "authoring_language")
