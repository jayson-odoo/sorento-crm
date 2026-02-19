"""Inbound shipment supplier_id: optional (nullable), SET NULL on delete

Packing lists (inbound shipments) may be created without a supplier. External API
may omit supplier_id. When a supplier is deleted, set supplier_id to NULL instead
of RESTRICT.

Revision ID: 053_inbound_supplier_nullable
Revises: 052_uom_is_active
Create Date: 2026-02-10

"""
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "053_inbound_supplier_nullable"
down_revision = "052_uom_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Make supplier_id nullable
    op.alter_column(
        "inbound_shipments",
        "supplier_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    # 2. Drop existing FK (RESTRICT) and create new one with SET NULL
    op.drop_constraint(
        "inbound_shipments_supplier_id_fkey",
        "inbound_shipments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "inbound_shipments_supplier_id_fkey",
        "inbound_shipments",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "inbound_shipments_supplier_id_fkey",
        "inbound_shipments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "inbound_shipments_supplier_id_fkey",
        "inbound_shipments",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Revert nullable - will fail if any rows have NULL supplier_id
    op.alter_column(
        "inbound_shipments",
        "supplier_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
