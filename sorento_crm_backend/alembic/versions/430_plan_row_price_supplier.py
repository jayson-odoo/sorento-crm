"""scm.plan_row_decision: the price mode, the supplier and the price the buyer chose.

AC-R13 / AC-R14 (`PLAN-scm-reorder-per-product.md`, Phase 2): on the plan row the
Suggested price pill becomes a switch (Use last price / Ask new price) and the Suggested
supplier a select over the product's suppliers. Both ride on the row's own decision and
both flow into the draft PO the plan confirms.

`price_mode` defaults to `use_last` on every row that already exists: that is what the
plan has always costed a line at, so backfilling anything else would rewrite decisions
nobody made. `supplier_id` / `unit_cost` stay NULL, which reads as "the engine's choice
stands" - the same fallback `_resolve_choice(rec, None)` already takes.

Revision ID: 430_plan_row_price_supplier
Revises: 429_merge_scm_uat_main
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "430_plan_row_price_supplier"
down_revision = "429_merge_scm_uat_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plan_row_decision",
        sa.Column("price_mode", sa.String(20), nullable=True),
        schema="scm",
    )
    op.add_column(
        "plan_row_decision",
        sa.Column(
            "supplier_id",
            UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", name="fk_scm_plan_row_decision_supplier_id",
                          ondelete="SET NULL"),
            nullable=True,
        ),
        schema="scm",
    )
    op.add_column(
        "plan_row_decision",
        sa.Column("unit_cost", sa.Numeric(), nullable=True),
        schema="scm",
    )
    # Every decision already recorded was costed at the last price - say so, rather than
    # leaving a NULL the reader has to guess at (idempotent "set where mismatch").
    op.execute(
        "UPDATE scm.plan_row_decision SET price_mode = 'use_last' "
        "WHERE price_mode IS DISTINCT FROM 'use_last' AND price_mode IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scm_plan_row_decision_supplier_id", "plan_row_decision",
        schema="scm", type_="foreignkey",
    )
    op.drop_column("plan_row_decision", "unit_cost", schema="scm")
    op.drop_column("plan_row_decision", "supplier_id", schema="scm")
    op.drop_column("plan_row_decision", "price_mode", schema="scm")
