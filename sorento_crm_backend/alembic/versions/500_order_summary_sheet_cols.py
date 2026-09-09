"""`scm.order_summary_row` gains the printed sheet's own columns (S9,
PLAN-reorder-feedback-9sep.md, G6 ruling 9 Sep 2026).

Order summary already exists and is frozen per run; this grows it to the sheet the buyer
fills in with a pen: delivery quantities by month, the project/customer names behind the
Project quantity, the suggested supplier, and the PO/SPO/last-receipt/MOQ remarks. All
additive, all nullable, no backfill - written going forward by `summary_order_service
.write_rows` and left NULL on every run frozen before this migration.

Revision ID: 500_order_summary_sheet_cols
Revises: 499_consumption_v_wh_segment
"""
import sqlalchemy as sa
from alembic import op

revision = "500_order_summary_sheet_cols"
down_revision = "499_consumption_v_wh_segment"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("delivery_by_month", "JSONB"),
    ("project_customers", "JSONB"),
    ("supplier_name", "TEXT"),
    ("po_open_qty", "NUMERIC"),
    ("incoming_spo_qty", "NUMERIC"),
    ("last_receipt_date", "DATE"),
    ("last_receipt_qty", "NUMERIC"),
    ("moq", "NUMERIC"),
)


def apply(bind) -> None:
    for name, sql_type in _COLUMNS:
        bind.execute(
            sa.text(
                f"ALTER TABLE scm.order_summary_row ADD COLUMN IF NOT EXISTS "
                f"{name} {sql_type}"
            )
        )


def revert(bind) -> None:
    for name, _sql_type in reversed(_COLUMNS):
        bind.execute(
            sa.text(f"ALTER TABLE scm.order_summary_row DROP COLUMN IF EXISTS {name}")
        )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
