"""`products` list-query field catalog gains `discontinued_at` (issue #1287,
PLAN-products-discontinued-at-26sep.md).

Data-only, same shape as `503_product_exclude_planning_flt.py`: the products list
filters through `ListQueryFilterDialog`, driven entirely by the DB-seeded
`list_query_fields` catalog. `discontinued_at` is not a new column - it reads
`products.discontinued_notified_at` via `compile_key`.

Export only (`filterable = false`): the advanced-filter compiler compares the raw
naive-UTC stamp to a bare date with no Malaysia-day conversion, so offering the field
there would contradict the Filters popover range (`discontinued_from` /
`discontinued_to`), which is the one filter for this date.

Revision ID: prod_discontinued_at_flt
Revises: sales_0002_team_leader
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "prod_discontinued_at_flt"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

_FIELD_KEY = "discontinued_at"
_OPS = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]


def seed(conn) -> bool:
    """Insert the `discontinued_at` field row; True if it was inserted.

    Split out of `upgrade()` so `scripts/bootstrap_env.py` can call the SAME body a
    from-zero database needs (`503_product_exclude_planning_flt.py`'s `seed()` is
    the precedent) - bootstrap only STAMPS this migration rather than running it, so
    its data seed would otherwise never land on a bootstrapped database.
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
        # A database that ran this migration's first cut carries the row with
        # `filterable = true`; flip it so a re-run (bootstrap replay, downgrade/upgrade)
        # converges on the same export-only row a fresh insert writes.
        conn.execute(
            sa.text(
                "UPDATE list_query_fields SET filterable = false "
                "WHERE resource_id = CAST(:rid AS uuid) AND field_key = :fk AND filterable"
            ),
            {"rid": rid, "fk": _FIELD_KEY},
        )
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
                CAST(:id AS uuid), CAST(:rid AS uuid), :fk, :label, 'date',
                'product.discontinued_notified_at', CAST(:ops AS jsonb), false, true, :exp,
                false, :so
            )
            """
        ),
        {
            "id": str(uuid.uuid4()), "rid": rid, "fk": _FIELD_KEY,
            "label": "Discontinued at", "ops": json.dumps(_OPS),
            "exp": "Discontinued at", "so": 96,
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
