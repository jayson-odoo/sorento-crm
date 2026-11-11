"""Add `products.spec_sheet_description` (SPEC-SHEET-DESIGNER-PARITY B1).

Staff copy for the project spec sheet. Nullable; the spec sheet falls back to
`products.description` when it is empty. Additive only.

Revision ID: ssd_0001_product_spec_desc
Revises: sca_0001_products_cost_view
Create Date: 2026-11-11
"""
from __future__ import annotations

from alembic import op

revision = "ssd_0001_product_spec_desc"
down_revision = "sca_0001_products_cost_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS spec_sheet_description TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS spec_sheet_description")
