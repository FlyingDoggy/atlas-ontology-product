"""Bind activation event snapshot references to durable snapshots.

Revision ID: 20260820_0003
Revises: 20260820_0002
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260820_0003"
down_revision: str | None = "20260820_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_lifecycle_event_previous_snapshot",
        "lifecycle_activation_event",
        "lifecycle_runtime_snapshot",
        ["previous_snapshot_checksum"],
        ["snapshot_checksum"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_lifecycle_event_active_snapshot",
        "lifecycle_activation_event",
        "lifecycle_runtime_snapshot",
        ["active_snapshot_checksum"],
        ["snapshot_checksum"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_lifecycle_event_expected_snapshot",
        "lifecycle_activation_event",
        "lifecycle_runtime_snapshot",
        ["expected_snapshot_checksum"],
        ["snapshot_checksum"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_lifecycle_event_expected_snapshot",
        "lifecycle_activation_event",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_lifecycle_event_active_snapshot",
        "lifecycle_activation_event",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_lifecycle_event_previous_snapshot",
        "lifecycle_activation_event",
        type_="foreignkey",
    )
