"""Billing lines: mark AutoCount subtotal lines so line-based sales sums skip them.

SALES-SUBTOTAL-LINES (plan documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md): some
AutoCount invoices carry a blank-item line whose amount is the running subtotal of the lines above
it, and the line sum counted it as a sale (line sum > header `local_net_total`).

1. `finance.billing_document_lines.is_subtotal boolean NOT NULL DEFAULT false`.
2. Backfill: the exact rule (header guard included) of `app/services/finance/billing_subtotal_lines.py` as a recursive
   walk over each document that has a line of subtotal shape (copied here so the migration stays
   frozen; `tests/test_billing_subtotal_lines.py` runs this copy against the ingest's).

Idempotent (`IF NOT EXISTS`; the backfill sets the same verdict on a rerun). Additive only; the
downgrade drops the column.

Revision ID: sbt_0001_billing_subtotal_lines
Revises: ptag_0016_accessories
"""
from __future__ import annotations

from alembic import op

revision = "sbt_0001_billing_subtotal_lines"
down_revision = "ptag_0016_accessories"
branch_labels = None
depends_on = None

ADD_COLUMN = (
    "ALTER TABLE finance.billing_document_lines "
    "ADD COLUMN IF NOT EXISTS is_subtotal boolean NOT NULL DEFAULT false"
)

#: Only documents holding a line of subtotal shape are walked (the rest stay false).
CANDIDATE_SCOPE = """l.document_id IN (
        SELECT c.document_id FROM finance.billing_document_lines c
        WHERE c.net_amount IS NOT NULL
          AND NULLIF(BTRIM(c.item_code), '') IS NULL AND c.product_id IS NULL
          AND NULLIF(BTRIM(c.uom), '') IS NULL AND c.quantity IS NULL AND c.unit_price IS NULL
    )"""

WALK_SQL = """
WITH RECURSIVE balanced AS (
    -- A document whose lines already add up to its header has nothing to undo (review R1).
    SELECT b.document_id
    FROM finance.billing_document_lines b
    JOIN finance.billing_documents d ON d.id = b.document_id
    GROUP BY b.document_id, d.net_total
    HAVING SUM(COALESCE(b.net_amount, 0)) = d.net_total
),
ordered AS (
    SELECT l.id, l.document_id, l.net_amount,
           (l.net_amount IS NOT NULL
            AND NULLIF(BTRIM(l.item_code), '') IS NULL AND l.product_id IS NULL
            AND NULLIF(BTRIM(l.uom), '') IS NULL AND l.quantity IS NULL AND l.unit_price IS NULL
            AND NULLIF(BTRIM(l.from_doc_type), '') IS NULL
            AND NULLIF(BTRIM(l.from_doc_no), '') IS NULL
            AND NULLIF(BTRIM(l.from_line_ref), '') IS NULL
            AND l.sales_order_line_id IS NULL
            AND l.document_id NOT IN (SELECT document_id FROM balanced)) AS shape,
           ROW_NUMBER() OVER (
               PARTITION BY l.document_id
               ORDER BY l.line_no NULLS LAST, l.source_ref COLLATE "C"
           ) AS rn
    FROM finance.billing_document_lines l
    WHERE {scope}
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
)
SELECT id, document_id, is_subtotal FROM walk
"""

BACKFILL = (
    "UPDATE finance.billing_document_lines t SET is_subtotal = v.is_subtotal "
    "FROM (" + WALK_SQL.format(scope=CANDIDATE_SCOPE) + ") v "
    "WHERE t.id = v.id AND t.is_subtotal IS DISTINCT FROM v.is_subtotal"
)


def upgrade() -> None:
    op.execute(ADD_COLUMN)
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute("ALTER TABLE finance.billing_document_lines DROP COLUMN IF EXISTS is_subtotal")
