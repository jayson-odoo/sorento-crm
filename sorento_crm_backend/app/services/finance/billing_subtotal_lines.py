"""AutoCount subtotal lines on a billing document (SALES-SUBTOTAL-LINES,
`documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md`).

Some AutoCount invoices carry a blank-item line whose amount is the running subtotal of the lines
above it. AutoCount marks it in `IVDTL.DtlType`, but the CRM payload does not carry that column,
so the line is recognised by an EXACT rule, never a fuzzy one. A line is a subtotal line when:

1. it has no item and nothing that makes it a sale of something: no item code, product, UOM,
   quantity, unit price, from-doc or sales order line;
2. at least one counted line comes before it in the document; and
3. its net amount equals, to the cent, the sum of the counted lines above it, either since the
   start of the document or since the previous subtotal line; and
4. the document's lines do NOT already add up to its header `net_total` (a document that
   balances double counts nothing, so a charge line that happens to equal the lines above it,
   e.g. item 50.00 + freight 50.00, stays a sale).

"Counted" is every line that is not a subtotal line, so a freight charge line above a subtotal is
part of it. Lines are read in `line_no` order (no number last), then by `source_ref` (byte order,
the SQL backfill's `COLLATE "C"`). The migration `sbt_0001_billing_subtotal_lines` backfills with
the same rule as a recursive SQL walk, copied there and into
`documentation/plans/sales/SQL-sales-subtotal-reconcile.sql`; `tests/test_billing_subtotal_lines.py`
R4 holds the migration's copy to this one.

The line is kept and shown on the document; only line-based sales sums skip it
(`invoiced_sales.counted_line()`).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping, MutableMapping, Optional

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


def mark_subtotal_lines(
    lines: Iterable[MutableMapping[str, Any]], net_total: Optional[Decimal]
) -> None:
    """Set `is_subtotal` on each of one document's line value dicts (the ingest's
    `_line_values` shape), deciding the whole document at once against its header
    `net_total` (rule 4)."""
    lines = list(lines)
    balanced = net_total is not None and sum(
        (Decimal(x["net_amount"]) for x in lines if x.get("net_amount") is not None), Decimal("0")
    ) == Decimal(net_total)
    since_start = Decimal("0")
    since_previous = Decimal("0")
    counted = 0
    for line in sorted(lines, key=_order_key):
        net = line.get("net_amount")
        is_subtotal = (
            not balanced
            and counted > 0
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

