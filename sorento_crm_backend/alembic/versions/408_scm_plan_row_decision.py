"""scm: plan_row_decision - the buy/use-stock/use-PO/skip decision, recorded on the row.

`PLAN-scm-reorder-decision-to-autocount.md`. Captain, 21 Aug (third time requested): "I
want the decision made here... there is only buy / use stock / use SPO / mixture, right"
- the results grid used to send the buyer to the product sheet ("Decided on the Product
sheet - open it"); this table is that decision, recorded on the row it belongs to.

One row per recommendation (unique on `recommendation_id`), kept CURRENT rather than
append-only - see the model docstring (`PlanRowDecision`, `app/models/scm.py`) for why
this differs from `scm.recommendation_override`'s append-only shape.

Revision ID: 408_scm_plan_row_decision
Revises: 407_join_spo_portal_heads
Create Date: 2026-08-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "408_scm_plan_row_decision"
down_revision = "407_join_spo_portal_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_row_decision",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_plan_row_decision_company_id"),
            nullable=True,
        ),
        sa.Column(
            "recommendation_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.reorder_recommendation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("buy_qty", sa.Numeric(), nullable=True),
        sa.Column("stock_takes", JSONB(), nullable=True),
        sa.Column("po_qty", sa.Numeric(), nullable=True),
        sa.Column("po_refs", JSONB(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "uq_scm_plan_row_decision_recommendation_id", "plan_row_decision",
        ["recommendation_id"], unique=True, schema="scm",
    )
    op.create_index(
        "ix_scm_plan_row_decision_company_id", "plan_row_decision",
        ["company_id"], schema="scm",
    )


def downgrade() -> None:
    op.drop_table("plan_row_decision", schema="scm")
