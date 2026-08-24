"""List query metadata tables for dynamic filters and exports.

Revision ID: 101_list_query_metadata
Revises: 100_drop_agent_pic
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "101_list_query_metadata"
down_revision = "100_drop_agent_pic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_query_resources",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("resource_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_list_query_resources_resource_key", "list_query_resources", ["resource_key"], unique=True)

    op.create_table(
        "list_query_fields",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("list_query_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(128), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("compile_key", sa.String(128), nullable=False),
        sa.Column("allowed_operators", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("filterable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("exportable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("export_column_name", sa.String(128), nullable=True),
        sa.Column("is_line_field", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("resource_id", "field_key", name="uq_list_query_fields_resource_field"),
    )
    op.create_index("ix_list_query_fields_resource_id", "list_query_fields", ["resource_id"])

    conn = op.get_bind()

    def ins_resource(key: str, name: str, desc: str) -> str:
        import uuid

        rid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO list_query_resources (id, resource_key, display_name, description, is_active)
                VALUES (:id, :k, :n, :d, true)
                """
            ),
            {"id": rid, "k": key, "n": name, "d": desc},
        )
        return rid

    def ins_field(
        rid: str,
        fk: str,
        label: str,
        dtype: str,
        ckey: str,
        ops: list,
        sort_order: int,
        line: bool = False,
        exp_name: str | None = None,
    ) -> None:
        import uuid

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
                    true, true, :exp, :line, :so
                )
                """
            ),
            {
                "id": fid,
                "rid": rid,
                "fk": fk,
                "label": label,
                "dtype": dtype,
                "ckey": ckey,
                "ops": json.dumps(ops),
                "exp": exp_name,
                "line": line,
                "so": sort_order,
            },
        )

    std_ops = ["eq", "ne", "contains", "starts_with", "in"]
    str_ops = ["eq", "ne", "contains", "starts_with", "in", "is_null"]
    num_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]
    bool_ops = ["eq", "is_null"]
    uuid_ops = ["eq", "ne", "in", "is_null"]
    date_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

    ro = ins_resource("orders", "Orders", "Order list filter/export metadata")
    ins_field(ro, "order_number", "Order number", "string", "order.order_number", str_ops, 10)
    ins_field(ro, "order_date", "Order date", "date", "order.order_date", date_ops, 20)
    ins_field(ro, "debtor_name", "Debtor name", "string", "order.debtor_name", str_ops, 30)
    ins_field(ro, "debtor_code", "Debtor code", "string", "order.debtor_code", str_ops, 40)
    ins_field(ro, "agent", "Agent", "string", "order.agent", str_ops, 50)
    ins_field(ro, "order_status_id", "Order status", "uuid", "order.order_status_id", uuid_ops, 60)
    ins_field(ro, "customer_id", "Customer", "uuid", "order.customer_id", uuid_ops, 70)
    ins_field(ro, "is_cancelled", "Cancelled", "boolean", "order.is_cancelled", bool_ops, 80)
    ins_field(ro, "total_amount", "Total amount", "number", "order.total_amount", num_ops, 90)
    ins_field(ro, "estimated_delivery_date", "Estimated delivery", "date", "order.estimated_delivery_date", date_ops, 100)
    ins_field(ro, "actual_delivery_date", "Actual delivery", "date", "order.actual_delivery_date", date_ops, 110)
    ins_field(ro, "order_type", "Order type", "string", "order.order_type", str_ops, 120)
    ins_field(ro, "remarks_cs", "Remarks CS", "string", "order.remarks_cs", str_ops, 130)
    ins_field(ro, "line_product_id", "Line - product", "uuid", "line.product_id", uuid_ops, 200, line=True, exp_name="line_product_id")
    ins_field(ro, "line_warehouse_id", "Line - warehouse", "uuid", "line.warehouse_id", uuid_ops, 210, line=True, exp_name="line_warehouse_id")
    ins_field(ro, "line_quantity", "Line - quantity", "number", "line.quantity", num_ops, 220, line=True, exp_name="line_quantity")

    rp = ins_resource("products", "Products", "Product list filter/export metadata")
    ins_field(rp, "product_code", "Product code", "string", "product.product_code", str_ops, 10)
    ins_field(rp, "product_name", "Product name", "string", "product.product_name", str_ops, 20)
    ins_field(rp, "category_id", "Category", "uuid", "product.category_id", uuid_ops, 30)
    ins_field(rp, "brand_id", "Brand", "uuid", "product.brand_id", uuid_ops, 40)
    ins_field(rp, "is_active", "Active", "boolean", "product.is_active", bool_ops, 50)
    ins_field(rp, "list_price", "List price", "number", "product.list_price", num_ops, 60)
    ins_field(rp, "item_type", "Item type", "string", "product.item_type", std_ops, 70)

    rs = ins_resource("suppliers", "Suppliers", "Supplier list filter/export metadata")
    ins_field(rs, "supplier_code", "Supplier code", "string", "supplier.supplier_code", str_ops, 10)
    ins_field(rs, "supplier_name", "Supplier name", "string", "supplier.supplier_name", str_ops, 20)
    ins_field(rs, "is_active", "Active", "boolean", "supplier.is_active", bool_ops, 30)
    ins_field(rs, "city", "City", "string", "supplier.city", str_ops, 40)
    ins_field(rs, "country", "Country", "string", "supplier.country", str_ops, 50)
    ins_field(rs, "email", "Email", "string", "supplier.email", str_ops, 60)


def downgrade() -> None:
    op.drop_table("list_query_fields")
    op.drop_table("list_query_resources")
