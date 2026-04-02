"""Drop unused inbound shipment line FK from SPO allocations.

Revision ID: 126_drop_spo_allocation_inbound_shipment_line_fk
Revises: 125_user_daily_sla_summary_subscription
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "126_drop_spo_allocation_inbound_shipment_line_fk"
down_revision = "125_user_daily_sla_summary_subscription"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("spo_allocations")}

    if "inbound_shipment_lines_id" not in columns:
        return

    for fk in inspector.get_foreign_keys("spo_allocations"):
        constrained = fk.get("constrained_columns") or []
        if "inbound_shipment_lines_id" in constrained and fk.get("name"):
            op.drop_constraint(fk["name"], "spo_allocations", type_="foreignkey")

    op.drop_column("spo_allocations", "inbound_shipment_lines_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("spo_allocations")}

    if "inbound_shipment_lines_id" not in columns:
        op.add_column(
            "spo_allocations",
            sa.Column(
                "inbound_shipment_lines_id",
                postgresql.UUID(as_uuid=False),
                nullable=True,
            ),
        )

    foreign_keys = inspector.get_foreign_keys("spo_allocations")
    has_fk = any(
        "inbound_shipment_lines_id" in (fk.get("constrained_columns") or [])
        for fk in foreign_keys
    )
    if not has_fk:
        op.create_foreign_key(
            "spo_allocations_inbound_shipment_lines_id_fkey",
            "spo_allocations",
            "inbound_shipment_lines",
            ["inbound_shipment_lines_id"],
            ["id"],
            ondelete="CASCADE",
        )
