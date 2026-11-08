"""Products list "List price changed at" (LIST-PRICE-CHANGE-UI,
documentation/plans/products/PLAN-list-price-change-ui-08nov.md).

Data only, both halves idempotent:

* ``backfill_changed_at``: owner Q1 (8 Nov). #2228 backfilled the watermark price but not its
  time, so ``list_price_notified_at`` is NULL for every product not changed since. Stamp it
  with the product's latest audited list-price change, only where it is still NULL and the
  product is not pending (``list_price = list_price_notified``: a pending change gets its
  stamp from the next ``product_list_price_check`` tick, as before). The value is the audit
  time, not a 15-minute tick. A CREATE row is not a change and never stamps.
* ``seed``: the ``list_price_changed_at`` export column (owner Q4), the
  ``prod_discontinued_at_flt`` shape exactly. Export only (``filterable = false``) for the
  same reason: the advanced-filter compiler has no Malaysia-day conversion, and the Filters
  popover range is the one filter for this date.

Revision ID: lpcui_0001_list_price_changed
Revises: pfcn_0001_list_price_notify
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "lpcui_0001_list_price_changed"
down_revision = "pfcn_0001_list_price_notify"
branch_labels = None
depends_on = None

_FIELD_KEY = "list_price_changed_at"
_OPS = ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]

# A JSON price as numeric, or NULL when the stored text is not a plain decimal.
_NUM = "CASE WHEN ({x}) ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN ({x})::numeric END"


def backfill_changed_at(conn) -> int:
    """Stamp ``list_price_notified_at`` from the audit trail; returns the rows stamped."""
    old_num = _NUM.format(x="a.old_values ->> 'list_price'")
    new_num = _NUM.format(x="a.new_values ->> 'list_price'")
    result = conn.execute(
        sa.text(
            f"""
            UPDATE products p
            SET list_price_notified_at = latest.changed_at
            FROM (
                SELECT DISTINCT ON (a.entity_id) a.entity_id, a.changed_at
                FROM audit_logs a
                WHERE a.entity_type = 'product' AND a.action = 'UPDATE'
                  AND a.new_values ? 'list_price'
                  AND ({old_num}) IS DISTINCT FROM ({new_num})
                ORDER BY a.entity_id, a.changed_at DESC
            ) latest
            WHERE p.id::text = latest.entity_id
              AND p.list_price_notified_at IS NULL
              AND p.list_price_notified IS NOT NULL
              AND p.list_price = p.list_price_notified
            """
        )
    )
    return result.rowcount or 0


def seed(conn) -> bool:
    """Insert the ``list_price_changed_at`` field row; True if it was inserted.

    Split out of ``upgrade()`` so ``scripts/bootstrap_env.py`` replays the same body
    (``prod_discontinued_at_flt.seed`` is the precedent)."""
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
                CAST(:id AS uuid), CAST(:rid AS uuid), :fk, :label, 'date',
                'product.list_price_notified_at', CAST(:ops AS jsonb), false, true, :exp,
                false, :so
            )
            """
        ),
        {
            "id": str(uuid.uuid4()), "rid": rid, "fk": _FIELD_KEY,
            "label": "List price changed at", "ops": json.dumps(_OPS),
            "exp": "List price changed at", "so": 97,
        },
    )
    return True


def upgrade() -> None:
    conn = op.get_bind()
    backfill_changed_at(conn)
    seed(conn)


def downgrade() -> None:
    # The backfilled stamps stay: they are true facts about past changes, and the column
    # predates this revision (pfcn_0001_list_price_notify).
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
