"""Allow multiple current Studio sources of the same material kind.

Revision ID: 20260821_0012
Revises: 20260821_0011
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260821_0012"
down_revision: str | None = "20260821_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "studio_source_head",
        sa.Column("source_id", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE studio_source_head AS head
        SET source_id = version.source_id
        FROM studio_source_version AS version
        WHERE version.source_version_id = head.source_version_id
        """
    )
    op.alter_column("studio_source_head", "source_id", nullable=False)
    op.drop_constraint("pk_studio_source_head", "studio_source_head", type_="primary")
    op.create_primary_key(
        "pk_studio_source_head",
        "studio_source_head",
        ["workspace_id", "source_id"],
    )
    op.create_index(
        "ix_studio_source_head_workspace_kind",
        "studio_source_head",
        ["workspace_id", "kind"],
        unique=False,
    )


def downgrade() -> None:
    # A legacy schema can retain only one current document per kind. Keep the most
    # recently updated head deterministically if an operator explicitly downgrades.
    op.execute(
        """
        DELETE FROM studio_source_head AS older
        USING studio_source_head AS newer
        WHERE older.workspace_id = newer.workspace_id
          AND older.kind = newer.kind
          AND (
            older.updated_at < newer.updated_at
            OR (
              older.updated_at = newer.updated_at
              AND older.source_id < newer.source_id
            )
          )
        """
    )
    op.drop_index(
        "ix_studio_source_head_workspace_kind",
        table_name="studio_source_head",
    )
    op.drop_constraint("pk_studio_source_head", "studio_source_head", type_="primary")
    op.create_primary_key(
        "pk_studio_source_head",
        "studio_source_head",
        ["workspace_id", "kind"],
    )
    op.drop_column("studio_source_head", "source_id")
