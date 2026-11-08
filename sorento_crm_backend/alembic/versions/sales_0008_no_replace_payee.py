"""Sales targets: drop "Replaced by" and the single "Pays to" (lane TARGET-PER-ACCOUNT-PAYOUT,
owner rulings 8 Nov, card Q1 (a) and Q2 (a)).

Separate targets stack, so no target zeroes another: `sales.targets.replaced_by_target_id` and
its check go (every link is cleared with the column). Each counted account of a dealer target
is its own payee, so `sales.targets.payout_customer_id` and its check go too. Downgrade adds both
columns back empty (the links and payees are not restored).

Revision ID: sales_0008_no_replace_payee
Revises: panel_att_0001_ai_asst_type
Create Date: 2026-11-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.models.sales import translated_schema

revision = "sales_0008_no_replace_payee"
down_revision = "panel_att_0001_ai_asst_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.execute(f'ALTER TABLE "{schema}".targets DROP CONSTRAINT IF EXISTS ck_sales_targets_replaced_by_dealer')
    op.execute(f'ALTER TABLE "{schema}".targets DROP COLUMN IF EXISTS replaced_by_target_id')
    op.execute(f'ALTER TABLE "{schema}".targets DROP CONSTRAINT IF EXISTS ck_sales_targets_payout_dealer')
    op.execute(f'ALTER TABLE "{schema}".targets DROP COLUMN IF EXISTS payout_customer_id')


def downgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.add_column(
        "targets",
        sa.Column(
            "payout_customer_id",
            UUID(as_uuid=False),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_sales_targets_payout_dealer",
        "targets",
        "payout_customer_id IS NULL OR subject_kind = 'dealer'",
        schema=schema,
    )
    op.add_column(
        "targets",
        sa.Column(
            "replaced_by_target_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{schema}.targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_sales_targets_replaced_by_dealer",
        "targets",
        "replaced_by_target_id IS NULL OR subject_kind = 'dealer'",
        schema=schema,
    )
