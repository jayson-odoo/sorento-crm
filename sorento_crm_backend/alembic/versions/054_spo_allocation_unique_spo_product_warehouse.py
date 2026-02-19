"""SPO allocation uniqueness: spo_number + product_id + warehouse_id (drop spo_number + line)

Uniqueness is now (spo_number, product_id, warehouse_id). SPO line number is no longer
part of the key. Existing rows with duplicate (spo_number, product_id, warehouse_id)
will cause this migration to fail; consolidate or delete duplicates before running.

Revision ID: 054_spo_spo_product_wh_unique
Revises: 053_inbound_supplier_nullable
Create Date: 2026-02-10

"""
from alembic import op


revision = "054_spo_spo_product_wh_unique"
down_revision = "053_inbound_supplier_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraint on (spo_number, spo_line_number)
    op.drop_constraint(
        "uk_spo_allocations_spo_number_line_number",
        "spo_allocations",
        type_="unique",
    )
    # Add new unique constraint on (spo_number, product_id, warehouse_id)
    op.create_unique_constraint(
        "uk_spo_allocations_spo_number_product_warehouse",
        "spo_allocations",
        ["spo_number", "product_id", "warehouse_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uk_spo_allocations_spo_number_product_warehouse",
        "spo_allocations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uk_spo_allocations_spo_number_line_number",
        "spo_allocations",
        ["spo_number", "spo_line_number"],
    )
