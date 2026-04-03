"""System settings: default product supplier and standard lead time.

Revision ID: 127_system_settings_default_product_supplier
Revises: 126_drop_spo_allocation_inbound_shipment_line_fk
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import UUID


revision = "127_system_settings_default_product_supplier"
down_revision = "126_drop_spo_allocation_inbound_shipment_line_fk"
branch_labels = None
depends_on = None


def _fk_names(insp, table: str) -> set:
    return {fk["name"] for fk in insp.get_foreign_keys(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"]: c for c in insp.get_columns("system_settings")}

    if "default_product_supplier_id" not in cols:
        op.add_column(
            "system_settings",
            sa.Column(
                "default_product_supplier_id",
                UUID(as_uuid=False),
                nullable=True,
            ),
        )
    else:
        col = cols["default_product_supplier_id"]
        col_type = str(col["type"])
        if "UUID" not in col_type.upper():
            op.execute(
                text(
                    "ALTER TABLE system_settings "
                    "ALTER COLUMN default_product_supplier_id "
                    "TYPE uuid USING default_product_supplier_id::uuid"
                )
            )

    if "default_product_standard_lead_time_days" not in cols:
        op.add_column(
            "system_settings",
            sa.Column(
                "default_product_standard_lead_time_days",
                sa.Integer(),
                nullable=False,
                server_default="90",
            ),
        )
        op.alter_column(
            "system_settings",
            "default_product_standard_lead_time_days",
            server_default=None,
        )

    insp = inspect(bind)
    if "fk_system_settings_default_product_supplier_id" not in _fk_names(
        insp, "system_settings"
    ):
        op.create_foreign_key(
            "fk_system_settings_default_product_supplier_id",
            "system_settings",
            "suppliers",
            ["default_product_supplier_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE system_settings "
            "DROP CONSTRAINT IF EXISTS fk_system_settings_default_product_supplier_id"
        )
    )
    op.drop_column("system_settings", "default_product_standard_lead_time_days")
    op.drop_column("system_settings", "default_product_supplier_id")
