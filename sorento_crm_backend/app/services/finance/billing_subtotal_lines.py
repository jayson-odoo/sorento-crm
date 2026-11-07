"""AutoCount subtotal lines on a billing document (SALES-SUBTOTAL-LINES,
`documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md`).

Some AutoCount invoices carry a blank-item line whose amount is the running subtotal of the lines
above it. AutoCount marks it in `IVDTL.DtlType`, but the CRM payload does not carry that column,
so the line is recognised by an EXACT rule, never a fuzzy one. A line is a subtotal line when:

1. it has no item and nothing that makes it a sale of something: no item code, product, UOM,
   quantity, unit price, from-doc or sales order line;
2. at least one counted line comes before it in the document; and
3. its net amount equals, to the cent, the sum of the counted lines above it, either since the
   start of the document or since the previous subtotal line.

"Counted" is every line that is not a subtotal line, so a freight charge line above a subtotal is
part of it. Lines are read in `line_no` order (no number last), then by `source_ref` (byte order,
the SQL backfill's `COLLATE "C"`). The migration `sbt_0001_billing_subtotal_lines` backfills with
the same rule as a recursive SQL walk; a test holds the two together.

The line is kept and shown on the document; only line-based sales sums skip it
(`invoiced_sales.counted_line()`).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping, MutableMapping

#: Every field that must be empty for a line to have the shape of a subtotal line.
_EMPTY_FIELDS = (
    "item_code",
    "product_id",
    "uom",
    "quantity",
    "unit_price",
    "from_doc_type",
    "from_doc_no",
    "from_line_ref",
    "sales_order_line_id",
)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def has_subtotal_shape(line: Mapping[str, Any]) -> bool:
    """A line naming no item and carrying an amount (rule 1)."""
    return line.get("net_amount") is not None and all(
        _is_empty(line.get(name)) for name in _EMPTY_FIELDS
    )


def _order_key(line: Mapping[str, Any]) -> tuple:
    line_no = line.get("line_no")
    return (line_no is None, line_no or 0, str(line.get("source_ref") or "").encode())


def mark_subtotal_lines(lines: Iterable[MutableMapping[str, Any]]) -> None:
    """Set `is_subtotal` on each of one document's line value dicts (the ingest's
    `_line_values` shape), deciding the whole document at once."""
    since_start = Decimal("0")
    since_previous = Decimal("0")
    counted = 0
    for line in sorted(lines, key=_order_key):
        net = line.get("net_amount")
        is_subtotal = (
            counted > 0
            and has_subtotal_shape(line)
            and Decimal(net) in (since_start, since_previous)
        )
        line["is_subtotal"] = is_subtotal
        if is_subtotal:
            since_previous = Decimal("0")
            continue
        counted += 1
        amount = Decimal(net) if net is not None else Decimal("0")
        since_start += amount
        since_previous += amount


#: The same rule over stored rows, as SQL: one row per line with its verdict. `{scope}` is a
#: WHERE fragment over `billing_document_lines l` (e.g. `TRUE`, or `l.document_id = :doc`).
#: Read-only; the migration's backfill and the reconciliation query use this walk.
SUBTOTAL_WALK_SQL = """
WITH RECURSIVE ordered AS (
    SELECT l.id, l.document_id, l.net_amount,
           (l.net_amount IS NOT NULL
            AND NULLIF(BTRIM(l.item_code), '') IS NULL AND l.product_id IS NULL
            AND NULLIF(BTRIM(l.uom), '') IS NULL AND l.quantity IS NULL AND l.unit_price IS NULL
            AND NULLIF(BTRIM(l.from_doc_type), '') IS NULL
            AND NULLIF(BTRIM(l.from_doc_no), '') IS NULL
            AND NULLIF(BTRIM(l.from_line_ref), '') IS NULL
            AND l.sales_order_line_id IS NULL) AS shape,
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
