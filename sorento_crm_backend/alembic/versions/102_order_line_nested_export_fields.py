"""Nested order line export fields (product/warehouse attributes, not raw UUIDs).

Revision ID: 102_order_line_nested_export
Revises: 101_list_query_metadata
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "102_order_line_nested_export"
down_revision = "101_list_query_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    ro = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'orders' LIMIT 1")
    ).scalar()
    if not ro:
        return

    conn.execute(
        sa.text(
            """
            UPDATE list_query_fields
            SET exportable = false
            WHERE resource_id = :rid AND field_key IN ('line_product_id', 'line_warehouse_id')
            """
        ),
        {"rid": ro},
    )

    str_ops = ["eq", "ne", "contains", "starts_with", "in", "is_null"]
    num_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

    def ins(fk: str, label: str, dtype: str, ckey: str, ops: list, so: int, exp: str) -> None:
        fid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO list_query_fields (
                    id, resource_id, field_key, label, data_type, compile_key,
                    allowed_operators, filterable, exportable, export_column_name,
                    is_line_field, sort_order
                )
                VALUES (
                    :id, :rid, :fk, :label, :dtype, :ckey, CAST(:ops AS jsonb),
                    true, true, :exp, true, :so
                )
                """
            ),
            {
                "id": fid,
                "rid": ro,
                "fk": fk,
                "label": label,
                "dtype": dtype,
                "ckey": ckey,
                "ops": json.dumps(ops),
                "exp": exp,
                "so": so,
            },
        )

    ins("line_product_code", "Line — product code", "string", "line.product.product_code", str_ops, 201, "line_product_code")
    ins("line_product_name", "Line — product name", "string", "line.product.product_name", str_ops, 202, "line_product_name")
    ins("line_product_list_price", "Line — product list price", "number", "line.product.list_price", num_ops, 203, "line_product_list_price")
    ins("line_product_item_type", "Line — product item type", "string", "line.product.item_type", str_ops, 204, "line_product_item_type")
    ins("line_warehouse_code", "Line — warehouse code", "string", "line.warehouse.warehouse_code", str_ops, 211, "line_warehouse_code")
    ins("line_warehouse_name", "Line — warehouse name", "string", "line.warehouse.warehouse_name", str_ops, 212, "line_warehouse_name")


def downgrade() -> None:
    conn = op.get_bind()
    ro = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'orders' LIMIT 1")
    ).scalar()
    if not ro:
        return
    conn.execute(
        sa.text(
            """
            DELETE FROM list_query_fields
            WHERE resource_id = :rid
              AND field_key IN (
                'line_product_code', 'line_product_name', 'line_product_list_price',
                'line_product_item_type', 'line_warehouse_code', 'line_warehouse_name'
              )
            """
        ),
        {"rid": ro},
    )
    conn.execute(
        sa.text(
            """
            UPDATE list_query_fields
            SET exportable = true
            WHERE resource_id = :rid AND field_key IN ('line_product_id', 'line_warehouse_id')
            """
        ),
        {"rid": ro},
    )
