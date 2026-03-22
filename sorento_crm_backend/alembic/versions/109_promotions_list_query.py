"""Add promotions resource to list_query metadata.

Revision ID: 109_promotions_list_query
Revises: 108_seed_annual_dinner_sponsorship_workflow
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "109_promotions_list_query"
down_revision = "108_seed_annual_dinner_sponsorship_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    bool_ops = ["eq", "is_null"]
    date_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

    rp = ins_resource("promotions", "Promotions", "Promotion list filter/export metadata")
    ins_field(rp, "promo_code", "Promo code", "string", "promotion.promo_code", str_ops, 10)
    ins_field(rp, "name", "Name", "string", "promotion.name", str_ops, 20)
    ins_field(rp, "promo_type", "Type", "string", "promotion.promo_type", std_ops, 30)
    ins_field(rp, "description", "Description", "string", "promotion.description", str_ops, 40)
    ins_field(rp, "start_date", "Start date", "date", "promotion.start_date", date_ops, 50)
    ins_field(rp, "end_date", "End date", "date", "promotion.end_date", date_ops, 60)
    ins_field(rp, "is_active", "Active", "boolean", "promotion.is_active", bool_ops, 70)
    ins_field(rp, "created_at", "Created", "date", "promotion.created_at", date_ops, 80)


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = :k"),
        {"k": "promotions"},
    ).fetchone()
    if not row:
        return
    rid = row[0]
    conn.execute(sa.text("DELETE FROM list_query_fields WHERE resource_id = :rid"), {"rid": rid})
    conn.execute(sa.text("DELETE FROM list_query_resources WHERE id = :rid"), {"rid": rid})
