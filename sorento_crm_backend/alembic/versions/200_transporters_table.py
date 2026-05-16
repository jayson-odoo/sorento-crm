"""Create transporters lookup table and orders.transporter_id FK.

Seed transporters from distinct orders.transporter strings. The legacy
orders.transporter free-text column is retained for backwards-compat; the new
nullable FK transporter_id is the canonical link for embedding / linkage flows.

Revision ID: 200_transporters_table
Revises: 199_rename_orders_delivery_time_to_pickup_time
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "200_transporters_table"
down_revision = "199_rename_orders_delivery_time_to_pickup_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transporters",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_transporters_code"),
        sa.UniqueConstraint("normalized_name", name="uq_transporters_normalized_name"),
    )
    op.create_index("ix_transporters_normalized_name", "transporters", ["normalized_name"])

    op.execute(
        """
        INSERT INTO transporters (id, code, name, normalized_name, created_at)
        SELECT
            gen_random_uuid(),
            btrim(transporter) AS code,
            btrim(transporter) AS name,
            lower(btrim(transporter)) AS normalized_name,
            now()
        FROM (
            SELECT DISTINCT transporter
            FROM orders
            WHERE transporter IS NOT NULL AND btrim(transporter) <> ''
        ) src
        ON CONFLICT (normalized_name) DO NOTHING;
        """
    )

    op.add_column(
        "orders",
        sa.Column("transporter_id", UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_transporter_id",
        "orders",
        "transporters",
        ["transporter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_orders_transporter_id", "orders", ["transporter_id"])

    op.execute(
        """
        UPDATE orders o
        SET transporter_id = t.id
        FROM transporters t
        WHERE o.transporter IS NOT NULL
          AND lower(btrim(o.transporter)) = t.normalized_name
          AND (o.transporter_id IS DISTINCT FROM t.id);
        """
    )


def downgrade() -> None:
    op.drop_index("ix_orders_transporter_id", table_name="orders")
    op.drop_constraint("fk_orders_transporter_id", "orders", type_="foreignkey")
    op.drop_column("orders", "transporter_id")
    op.drop_index("ix_transporters_normalized_name", table_name="transporters")
    op.drop_table("transporters")
