"""Make warehouses.warehouse_name nullable (system location description optional).

Revision ID: 189_warehouse_name_nullable
Revises: 188_forms_form_type_lookup
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op


revision = "189_warehouse_name_nullable"
down_revision = "188_forms_form_type_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "warehouses",
        "warehouse_name",
        existing_type=sa.String(length=150),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE warehouses SET warehouse_name = warehouse_code WHERE warehouse_name IS NULL"
    )
    op.alter_column(
        "warehouses",
        "warehouse_name",
        existing_type=sa.String(length=150),
        nullable=False,
    )
