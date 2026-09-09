"""`products` list-query field catalog gains `exclude_from_planning` (S6, Phase 3 fix
round, PLAN-reorder-feedback-9sep.md).

The products list filters through `ListQueryFilterDialog`, driven entirely by the DB-seeded
`list_query_fields` catalog (`101_list_query_metadata.py` established the pattern; `128_
products_list_query_all_master_fields.py` is the closest sibling seeding). Adding the column
in S5's own migration was not enough - the column exists and the field's own value round-
trips, but a buyer cannot FILTER the list by it until a catalog row exists for it too.

Revision ID: 503_product_exclude_planning_flt
Revises: 502_order_summary_sheet_cols
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "503_product_exclude_planning_flt"
down_revision = "502_order_summary_sheet_cols"
branch_labels = None
depends_on = None

_FIELD_KEY = "exclude_from_planning"
_BOOL_OPS = ["eq", "is_null"]


def seed(conn) -> bool:
    """Insert the `exclude_from_planning` field row; True if it was inserted.

    Split out of `upgrade()` so `scripts/bootstrap_env.py` can call the SAME body a
    from-zero database needs (`seed_customer_import_aliases`'s 353 already does this) -
    bootstrap only STAMPS this migration rather than running it, so its data seed would
    otherwise never land on a bootstrapped database.
    """
    row = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'products' LIMIT 1")
    ).fetchone()
    if not row:
        return False
    rid = str(row[0])
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM list_query_fields "
            "WHERE resource_id = CAST(:rid AS uuid) AND field_key = :fk LIMIT 1"
        ),
        {"rid": rid, "fk": _FIELD_KEY},
    ).fetchone()
    if exists:
        return False
    conn.execute(
        sa.text(
            """
            INSERT INTO list_query_fields (
                id, resource_id, field_key, label, data_type, compile_key,
                allowed_operators, filterable, exportable, export_column_name,
                is_line_field, sort_order
            )
            VALUES (
                CAST(:id AS uuid), CAST(:rid AS uuid), :fk, :label, 'boolean',
                'product.exclude_from_planning', CAST(:ops AS jsonb), true, true, :exp,
                false, :so
            )
            """
        ),
        {
            "id": str(uuid.uuid4()), "rid": rid, "fk": _FIELD_KEY,
            "label": "Excluded from planning", "ops": json.dumps(_BOOL_OPS),
            "exp": "Excluded from planning", "so": 97,
        },
    )
    return True


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM list_query_resources WHERE resource_key = 'products' LIMIT 1")
    ).fetchone()
    if not row:
        return
    conn.execute(
        sa.text(
            "DELETE FROM list_query_fields "
            "WHERE resource_id = CAST(:rid AS uuid) AND field_key = :fk"
        ),
        {"rid": str(row[0]), "fk": _FIELD_KEY},
    )
