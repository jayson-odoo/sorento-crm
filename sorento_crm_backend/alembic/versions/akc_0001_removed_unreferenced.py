"""AC-REMOVED-KEEP-CANCELLED follow-up: mark the lines the sweep keeps instead of deleting.

Revision ID: akc_0001_removed_unreferenced
Revises: eem_0002_span_version_on_diet
Create Date: 2026-10-27

Before #1905 the ingest's leftover sweep hard-deleted an AutoCount PO / SO line a push no
longer carried when nothing pointed at it; now it keeps it as Cancelled (owner, 27 Oct).
Owner via crew, 27 Oct: those lines must not start counting in any aggregate, while every
other cancelled line keeps counting exactly as today. Which lines those are is only known
when the sweep runs, so the sweep records it here. `false` for every existing row: nothing
was kept this way before this column, and lines the recovery script restores set it.
"""
from __future__ import annotations

from alembic import op

revision = "akc_0001_removed_unreferenced"
down_revision = "eem_0002_span_version_on_diet"
branch_labels = None
depends_on = None

TABLES = ("sales_order_lines", "purchase_order_lines")


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS removed_unreferenced "
            "BOOLEAN NOT NULL DEFAULT false"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS removed_unreferenced")
