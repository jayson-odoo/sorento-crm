"""complaint_fulfilment_orders - complaint <-> replacement DO link table.

Revision ID: 251_complaint_fulfilment_orders
Revises: 250_pr_submitted_at
Create Date: 2026-06-30

A replacement / fulfilment Delivery Order is auto-linked to the complaint(s)
named in its Remarks CS field. Many-to-many: one DO can name many complaints,
one complaint can accumulate many DOs (partial shipments). ``delivery_notified_at``
is the per-(complaint, DO) idempotency stamp for the delivery notification - set
when the notice is sent (or stamped-without-send by the backfill). The new
``fulfilled`` complaint status is just a String(50) value; no enum migration.
See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "251_complaint_fulfilment_orders"
down_revision = "250_pr_submitted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "complaint_fulfilment_orders",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "complaint_id",
            UUID(as_uuid=False),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            UUID(as_uuid=False),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivery_notified_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint(
            "complaint_id", "order_id", name="uq_complaint_fulfilment_order"
        ),
    )
    op.create_index(
        "ix_complaint_fulfilment_orders_complaint_id",
        "complaint_fulfilment_orders",
        ["complaint_id"],
    )
    op.create_index(
        "ix_complaint_fulfilment_orders_order_id",
        "complaint_fulfilment_orders",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_complaint_fulfilment_orders_order_id",
        table_name="complaint_fulfilment_orders",
    )
    op.drop_index(
        "ix_complaint_fulfilment_orders_complaint_id",
        table_name="complaint_fulfilment_orders",
    )
    op.drop_table("complaint_fulfilment_orders")
