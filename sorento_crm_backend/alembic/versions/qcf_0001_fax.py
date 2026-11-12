"""Fax number: party, quotation document recipient snapshot, company settings.

QUOTE-COVER-FIELDS: plain optional text so the quotation cover page can print it. Idempotent
(`IF NOT EXISTS`), additive only.

Revision ID: qcf_0001_fax
Revises: ptag_0021_icon_conditions
"""
from __future__ import annotations

from alembic import op

revision = "qcf_0001_fax"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects.parties ADD COLUMN IF NOT EXISTS fax VARCHAR(50)")
    op.execute(
        "ALTER TABLE projects.quotation_documents "
        "ADD COLUMN IF NOT EXISTS recipient_fax_snapshot VARCHAR(200)"
    )
    op.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS fax VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS fax")
    op.execute(
        "ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS recipient_fax_snapshot"
    )
    op.execute("ALTER TABLE projects.parties DROP COLUMN IF EXISTS fax")
