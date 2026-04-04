"""Add all product master columns to list_query_fields for advanced filter/export.

Revision ID: 128_products_list_query_all_master_fields
Revises: 127_system_settings_default_product_supplier
Create Date: 2026-04-03
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "128_products_list_query_all_master_fields"
down_revision = "127_system_settings_default_product_supplier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'products' LIMIT 1")
    ).fetchone()
    if not row:
        return
    rid = row[0]

    str_ops = ["eq", "ne", "contains", "starts_with", "in", "is_null"]
    num_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]
    bool_ops = ["eq", "is_null"]
    uuid_ops = ["eq", "ne", "in", "is_null"]
    date_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

    def ins_field(
        fk: str,
        label: str,
        dtype: str,
        ckey: str,
        ops: list,
        sort_order: int,
        exp_name: str | None = None,
    ) -> None:
        import uuid

        exists_row = conn.execute(
            sa.text(
                "SELECT 1 FROM list_query_fields WHERE resource_id = CAST(:rid AS uuid) AND field_key = :fk LIMIT 1"
            ),
            {"rid": str(rid), "fk": fk},
        ).fetchone()
        if exists_row:
            return
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
                    CAST(:id AS uuid), CAST(:rid AS uuid), :fk, :label, :dtype, :ckey,
                    CAST(:ops AS jsonb), true, true, :exp, false, :so
                )
                """
            ),
            {
                "id": fid,
                "rid": str(rid),
                "fk": fk,
                "label": label,
                "dtype": dtype,
                "ckey": ckey,
                "ops": json.dumps(ops),
                "exp": exp_name,
                "so": sort_order,
            },
        )

    ins_field("description", "Description", "string", "product.description", str_ops, 75)
    ins_field("base_uom_id", "Base UOM", "uuid", "product.base_uom_id", uuid_ops, 77)
    ins_field("cost_price", "Cost price", "number", "product.cost_price", num_ops, 78)
    ins_field("invoice_price", "Invoice price", "number", "product.invoice_price", num_ops, 79)
    ins_field("weight", "Weight", "number", "product.weight", num_ops, 81)
    ins_field("dimensions_length", "Length", "number", "product.dimensions_length", num_ops, 82)
    ins_field("dimensions_width", "Width", "number", "product.dimensions_width", num_ops, 83)
    ins_field("dimensions_height", "Height", "number", "product.dimensions_height", num_ops, 84)
    ins_field("warranty_months", "Warranty (months)", "number", "product.warranty_months", num_ops, 86)
    ins_field("has_serial_tracking", "Serial tracking", "boolean", "product.has_serial_tracking", bool_ops, 87)
    ins_field("has_batch_tracking", "Batch tracking", "boolean", "product.has_batch_tracking", bool_ops, 88)
    ins_field("reorder_level", "Reorder level", "number", "product.reorder_level", num_ops, 89)
    ins_field("reorder_quantity", "Reorder quantity", "number", "product.reorder_quantity", num_ops, 91)
    ins_field("created_by", "Created by", "string", "product.created_by", str_ops, 92)
    ins_field("updated_by", "Updated by", "string", "product.updated_by", str_ops, 93)
    ins_field("created_at", "Created at", "date", "product.created_at", date_ops, 94)
    ins_field("updated_at", "Updated at", "date", "product.updated_at", date_ops, 95)


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'products' LIMIT 1")
    ).fetchone()
    if not row:
        return
    rid = row[0]
    keys = (
        "description",
        "base_uom_id",
        "cost_price",
        "invoice_price",
        "weight",
        "dimensions_length",
        "dimensions_width",
        "dimensions_height",
        "warranty_months",
        "has_serial_tracking",
        "has_batch_tracking",
        "reorder_level",
        "reorder_quantity",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    rid_s = str(rid)
    for fk in keys:
        conn.execute(
            sa.text(
                "DELETE FROM list_query_fields WHERE resource_id = CAST(:rid AS uuid) AND field_key = :fk"
            ),
            {"rid": rid_s, "fk": fk},
        )
