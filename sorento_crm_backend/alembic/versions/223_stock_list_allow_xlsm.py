"""Allow `.xlsm` uploads for the Stock List attachment type.

Dealers send a macro-enabled stock workbook; the upload pipeline strips VBA
and keeps only the Template sheet before storage (see
`app/services/excel_macro_stripper.py`), so accepting `xlsm` here is safe  - 
macro bytes never reach S3/R2 or the n8n webhook.

Idempotent: appends `xlsm` only where it is not already present, so re-runs
and pre-configured environments are no-ops. Matches both the UI name
("Stock List") and the legacy seed name ("Stock_List").

Revision ID: 223_stock_list_allow_xlsm
Revises: 222_brands_access_levels
Create Date: 2026-06-04
"""
from __future__ import annotations

from alembic import op


revision = "223_stock_list_allow_xlsm"
down_revision = "222_brands_access_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE attachment_types
        SET allowed_extensions = allowed_extensions || ',xlsm'
        WHERE type_name IN ('Stock List', 'Stock_List')
          AND NOT (',' || replace(lower(allowed_extensions), '.', '') || ',') LIKE '%,xlsm,%'
        """
    )


def downgrade() -> None:
    # Strip xlsm back out (handles leading/middle/trailing position).
    op.execute(
        """
        UPDATE attachment_types
        SET allowed_extensions = trim(both ',' from replace(',' || allowed_extensions || ',', ',xlsm,', ','))
        WHERE type_name IN ('Stock List', 'Stock_List')
        """
    )
