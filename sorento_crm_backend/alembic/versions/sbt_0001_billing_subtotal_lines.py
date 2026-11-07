"""Billing lines: mark AutoCount subtotal lines and duplicate copies so line sums skip them.

SALES-SUBTOTAL-LINES (plan documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md): some
AutoCount invoices carry a blank-item line whose amount is the running subtotal of the lines above
it, others (MCH) an item-package parent row repeating its first child's quantity, price and
money; the line sum counted both as sales (line sum > header `local_net_total`).

1. `finance.billing_document_lines.is_subtotal` and `.is_duplicate`, boolean NOT NULL DEFAULT false.
2. Backfill: the exact rules (header guard included) of
   `app/services/finance/billing_subtotal_lines.py` in SQL, over each document that has a line
   naming no item (copied here so the migration stays frozen;
   `tests/test_billing_subtotal_lines.py` R4 runs this copy against the ingest's).

Idempotent (`IF NOT EXISTS`; the backfill sets the same verdict on a rerun and writes only rows
whose verdict changes). Additive only; the downgrade drops the columns.

Revision ID: sbt_0001_billing_subtotal_lines
Revises: ptag_0016_accessories
"""
from __future__ import annotations

from alembic import op

revision = "sbt_0001_billing_subtotal_lines"
down_revision = "ptag_0016_accessories"
branch_labels = None
depends_on = None

ADD_COLUMNS = (
    "ALTER TABLE finance.billing_document_lines "
    "ADD COLUMN IF NOT EXISTS is_subtotal boolean NOT NULL DEFAULT false, "
    "ADD COLUMN IF NOT EXISTS is_duplicate boolean NOT NULL DEFAULT false"
)

#: Only documents holding a line that names no item are decided (the rest stay false).
CANDIDATE_SCOPE = """l.document_id IN (
        SELECT c.document_id FROM finance.billing_document_lines c
        WHERE c.net_amount IS NOT NULL
          AND NULLIF(BTRIM(c.item_code), '') IS NULL AND c.product_id IS NULL
    )"""

#: One row per line in `{scope}` (a WHERE fragment over `finance.billing_document_lines l`):
#: `(id, document_id, is_subtotal, is_duplicate)`. Read-only.
VERDICT_SQL = """
WITH RECURSIVE scoped AS (
    SELECT l.* FROM finance.billing_document_lines l WHERE {scope}
),
balanced AS (
    -- A document whose lines already add up to its header has nothing to undo.
    SELECT s.document_id
    FROM scoped s
    JOIN finance.billing_documents d ON d.id = s.document_id
    GROUP BY s.document_id, d.net_total
    HAVING SUM(COALESCE(s.net_amount, 0)) = d.net_total
),
real AS (
    SELECT s.document_id, s.quantity, s.unit_price, s.discount_amount, s.net_amount, COUNT(*) AS n
    FROM scoped s
    WHERE (NULLIF(BTRIM(s.item_code), '') IS NOT NULL OR s.product_id IS NOT NULL)
      AND s.quantity IS NOT NULL AND s.unit_price IS NOT NULL AND s.net_amount IS NOT NULL
    GROUP BY s.document_id, s.quantity, s.unit_price, s.discount_amount, s.net_amount
),
copies AS (
    -- An item-package parent row: no item, no UOM, a quantity and a price.
    SELECT s.id, s.document_id, s.quantity, s.unit_price, s.discount_amount, s.net_amount,
           ROW_NUMBER() OVER (
               PARTITION BY s.document_id, s.quantity, s.unit_price, s.discount_amount, s.net_amount
               ORDER BY s.source_ref COLLATE "C"
           ) AS rk
    FROM scoped s
    WHERE NULLIF(BTRIM(s.item_code), '') IS NULL AND s.product_id IS NULL
      AND NULLIF(BTRIM(s.uom), '') IS NULL
      AND s.quantity IS NOT NULL AND s.unit_price IS NOT NULL AND s.net_amount IS NOT NULL
      AND s.document_id NOT IN (SELECT document_id FROM balanced)
),
dup AS (
    -- One real line excuses one copy (same document, quantity, price, discount and money).
    SELECT c.id
    FROM copies c
    JOIN real r ON r.document_id = c.document_id AND r.quantity = c.quantity
                AND r.unit_price = c.unit_price AND r.net_amount = c.net_amount
                AND r.discount_amount IS NOT DISTINCT FROM c.discount_amount
    WHERE c.rk <= r.n
),
ordered AS (
    SELECT s.id, s.document_id, s.net_amount,
           (s.net_amount IS NOT NULL
            AND NULLIF(BTRIM(s.item_code), '') IS NULL AND s.product_id IS NULL
            AND NULLIF(BTRIM(s.uom), '') IS NULL AND s.quantity IS NULL AND s.unit_price IS NULL
            AND s.document_id NOT IN (SELECT document_id FROM balanced)) AS shape,
           ROW_NUMBER() OVER (
               PARTITION BY s.document_id
               ORDER BY s.line_no NULLS LAST, s.source_ref COLLATE "C"
           ) AS rn
    FROM scoped s
    WHERE s.id NOT IN (SELECT id FROM dup)
),
walk AS (
    SELECT o.id, o.document_id, o.rn, FALSE AS is_subtotal,
           COALESCE(o.net_amount, 0) AS since_start,
           COALESCE(o.net_amount, 0) AS since_previous,
           1 AS counted
    FROM ordered o
    WHERE o.rn = 1
    UNION ALL
    SELECT o.id, o.document_id, o.rn, v.is_subtotal,
           CASE WHEN v.is_subtotal THEN w.since_start
                ELSE w.since_start + COALESCE(o.net_amount, 0) END,
           CASE WHEN v.is_subtotal THEN 0
                ELSE w.since_previous + COALESCE(o.net_amount, 0) END,
           w.counted + CASE WHEN v.is_subtotal THEN 0 ELSE 1 END
    FROM walk w
    JOIN ordered o ON o.document_id = w.document_id AND o.rn = w.rn + 1
    CROSS JOIN LATERAL (
        SELECT (w.counted > 0 AND o.shape
                AND o.net_amount IN (w.since_start, w.since_previous)) AS is_subtotal
    ) v
),
verdict AS (
    SELECT id, document_id, is_subtotal, FALSE AS is_duplicate FROM walk
    UNION ALL
    SELECT s.id, s.document_id, FALSE, TRUE FROM scoped s WHERE s.id IN (SELECT id FROM dup)
)
"""

BACKFILL = (
    "UPDATE finance.billing_document_lines t "
    "SET is_subtotal = v.is_subtotal, is_duplicate = v.is_duplicate FROM ("
    + VERDICT_SQL.format(scope=CANDIDATE_SCOPE)
    + "SELECT id, is_subtotal, is_duplicate FROM verdict"
    + ") v WHERE t.id = v.id AND (t.is_subtotal IS DISTINCT FROM v.is_subtotal "
    "OR t.is_duplicate IS DISTINCT FROM v.is_duplicate)"
)


def upgrade() -> None:
    op.execute(ADD_COLUMNS)
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE finance.billing_document_lines "
        "DROP COLUMN IF EXISTS is_duplicate, DROP COLUMN IF EXISTS is_subtotal"
    )
