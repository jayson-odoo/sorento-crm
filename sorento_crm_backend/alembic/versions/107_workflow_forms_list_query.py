"""List-query resources for workflow form definitions and submissions.

Revision ID: 107_workflow_forms_list_query
Revises: 106_notifications_event_type_varchar255
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "107_workflow_forms_list_query"
down_revision = "106_notifications_event_type_varchar255"
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
        filterable: bool = True,
        exportable: bool = True,
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
                    :filt, :expb, :exp, :line, :so
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
                "filt": filterable,
                "expb": exportable,
                "exp": exp_name,
                "line": line,
                "so": sort_order,
            },
        )

    str_ops = ["eq", "ne", "contains", "starts_with", "in", "is_null"]
    bool_ops = ["eq", "is_null"]
    uuid_ops = ["eq", "ne", "in", "is_null"]
    date_ops = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

    r1 = ins_resource(
        "workflow_form_definitions",
        "Workflow form definitions",
        "Filter and export workflow form definitions",
    )
    ins_field(r1, "code", "Code", "string", "def.code", str_ops, 10)
    ins_field(r1, "name", "Name", "string", "def.name", str_ops, 20)
    ins_field(r1, "description", "Description", "string", "def.description", str_ops, 30)
    ins_field(r1, "is_active", "Active", "boolean", "def.is_active", bool_ops, 40)
    ins_field(r1, "published_version_id", "Published version id", "uuid", "def.published_version_id", uuid_ops, 50)
    ins_field(r1, "created_at", "Created at", "date", "def.created_at", date_ops, 60)
    ins_field(r1, "updated_at", "Updated at", "date", "def.updated_at", date_ops, 70)

    r2 = ins_resource(
        "workflow_form_submissions",
        "Workflow form submissions",
        "Filter and export workflow form submissions",
    )
    ins_field(r2, "id", "Submission id", "uuid", "sub.id", uuid_ops, 10)
    ins_field(r2, "definition_id", "Form definition id", "uuid", "sub.definition_id", uuid_ops, 20)
    ins_field(r2, "current_state_code", "State", "string", "sub.current_state_code", str_ops, 30)
    ins_field(r2, "created_by_user_id", "Created by user id", "string", "sub.created_by_user_id", str_ops, 40)
    ins_field(r2, "created_at", "Created at", "date", "sub.created_at", date_ops, 50)
    ins_field(r2, "updated_at", "Updated at", "date", "sub.updated_at", date_ops, 60)
    ins_field(
        r2,
        "definition_name",
        "Form name",
        "string",
        "rel.definition_name",
        [],
        70,
        filterable=False,
        exportable=True,
        exp_name="Form name",
    )


def downgrade() -> None:
    conn = op.get_bind()
    for key in ("workflow_form_submissions", "workflow_form_definitions"):
        row = conn.execute(
            sa.text("SELECT id FROM list_query_resources WHERE resource_key = :k"),
            {"k": key},
        ).fetchone()
        if row:
            conn.execute(sa.text("DELETE FROM list_query_fields WHERE resource_id = :rid"), {"rid": row[0]})
            conn.execute(sa.text("DELETE FROM list_query_resources WHERE id = :rid"), {"rid": row[0]})
