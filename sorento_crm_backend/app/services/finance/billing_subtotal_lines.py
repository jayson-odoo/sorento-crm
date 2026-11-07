"""AutoCount billing lines that restate money already on the document (SALES-SUBTOTAL-LINES,
`documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md`).

Two kinds of line carry an amount that another line already carries, so a line sum counting
them overstates the document's header. AutoCount marks them in `IVDTL.DtlType` / `ParentDtlKey`,
but the CRM payload does not carry those columns, so each is recognised by an EXACT rule, never a
fuzzy one, and only on a document whose lines do NOT already add up to its header `net_total`
(the guard: a document that balances double counts nothing, so a charge line that happens to
equal the lines above it, e.g. item 50.00 + freight 50.00, stays a sale).

**Package copy** (`is_duplicate`; crew round 2, MCH Jan-Aug 2026): an AutoCount item-package
parent row ("... SET PACKAGE ...": no item code, no product, no UOM, but a quantity and a unit
price) whose package child, a line that names an item, repeats its quantity, unit price,
discount and net amount exactly. On `AED_V2_MOCHA` the first child carries the package's money as
well, so both rows count it. The copies are taken only when the document's lines less the copies
equal its header `net_total` exactly; otherwise none is. The parent's `line_no` need not be the
child's (M2601-1517: 48 and 16), so it is not compared. One real line excuses one copy (copies paired in `source_ref` byte order).

**Package parent, explicit** (`is_duplicate`; contract v2.13): once the shared service sends
`parent_line_ref` on a document's child lines, the parent is any line a child names, and it is
not summed when its children's net adds up to its own net exactly (MCH: the first child repeats
the money). Where children carry no money (SRT: "package children carry no money") the parent
keeps it. A document carrying `parent_line_ref` is decided by it alone, never by the inference.

**Subtotal** (`is_subtotal`): a line naming no item and nothing sold (no item code, product, UOM,
quantity or unit price; a from-doc reference is allowed, crew round 2, SRT Jan 2026), after at
least one counted line, whose net amount equals to the cent the counted lines above it, either
since the start of the document or since the previous subtotal line.

"Counted" is every line that is neither, so a freight charge line above a subtotal is part of it.
Duplicates are decided first; the subtotal walk reads the rest in `line_no` order (no number
last), then by `source_ref` (byte order, the SQL's `COLLATE "C"`).

The migration `sbt_0001_billing_subtotal_lines` backfills with the same rules in SQL, copied there
and into `documentation/plans/sales/SQL-sales-subtotal-reconcile.sql`;
`tests/test_billing_subtotal_lines.py` R4 holds the migration's copy to this one.

The lines are kept and shown on the document; only line-based sales sums skip them
(`invoiced_sales.counted_line()`).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping, MutableMapping, Optional

#: The fields that name an item: empty on a duplicate copy and on a subtotal line.
_ITEM_FIELDS = ("item_code", "product_id")
#: The fields that state something sold: also empty on a subtotal line.
_SOLD_FIELDS = ("uom", "quantity", "unit_price")


def _is_empty(value: Any) -> bool:
    # Spaces only, as the SQL's BTRIM: a tab is not blank to either.
    return value is None or (isinstance(value, str) and not value.strip(" "))


def _names_item(line: Mapping[str, Any]) -> bool:
    return not all(_is_empty(line.get(name)) for name in _ITEM_FIELDS)


def has_subtotal_shape(line: Mapping[str, Any]) -> bool:
    """A line naming no item, nothing sold, and carrying an amount."""
    return line.get("net_amount") is not None and all(
        _is_empty(line.get(name)) for name in _ITEM_FIELDS + _SOLD_FIELDS
    )


def _ref_key(line: Mapping[str, Any]) -> bytes:
    return str(line.get("source_ref") or "").encode()


def _order_key(line: Mapping[str, Any]) -> tuple:
    line_no = line.get("line_no")
    return (line_no is None, line_no or 0, _ref_key(line))


def _money_key(line: Mapping[str, Any]) -> Optional[tuple]:
    """(quantity, unit price, discount, net) when the line states quantity, price and net."""
    values = [line.get(name) for name in ("quantity", "unit_price", "discount_amount", "net_amount")]
    if values[0] is None or values[1] is None or values[3] is None:
        return None
    return tuple(None if v is None else Decimal(v) for v in values)


def _is_package_copy_shape(line: Mapping[str, Any]) -> bool:
    return not _names_item(line) and _is_empty(line.get("uom")) and _money_key(line) is not None


def _mark_duplicates(lines: list, net_total: Optional[Decimal]) -> None:
    """Mark the package copies, or none: the copies are taken only when the document's lines
    less the copies equal its header `net_total` exactly (review round 2: on a document off for
    another reason, a subtotal line or header-only money, a charge equal to an item line stays a
    sale, and the subtotal walk still sees it)."""
    real: dict[tuple, int] = {}
    for line in lines:
        key = _money_key(line)
        if _names_item(line) and key is not None:
            real[key] = real.get(key, 0) + 1
    copies = []
    for line in sorted(lines, key=_ref_key):
        key = _money_key(line)
        if _is_package_copy_shape(line) and real.get(key, 0) > 0:
            real[key] -= 1
            copies.append(line)
    total = sum((Decimal(x["net_amount"]) for x in lines if x.get("net_amount") is not None), Decimal("0"))
    exact = (
        net_total is not None
        and total - sum((Decimal(x["net_amount"]) for x in copies), Decimal("0")) == Decimal(net_total)
    )
    chosen = {id(x) for x in copies} if exact else set()
    for line in lines:
        line["is_duplicate"] = id(line) in chosen


def _mark_explicit_parents(lines: list) -> None:
    children: dict[str, Decimal] = {}
    for line in lines:
        ref = line.get("parent_line_ref")
        # A line naming itself is no package (review round 3): never its own child.
        if not _is_empty(ref) and ref != line.get("source_ref"):
            net = line.get("net_amount")
            children[ref] = children.get(ref, Decimal("0")) + (Decimal(net) if net is not None else Decimal("0"))
    for line in lines:
        net = line.get("net_amount")
        ref = line.get("source_ref")
        line["is_duplicate"] = (
            ref in children and net is not None and Decimal(net) != 0 and children[ref] == Decimal(net)
        )


def mark_uncounted_lines(
    lines: Iterable[MutableMapping[str, Any]], net_total: Optional[Decimal]
) -> None:
    """Set `is_duplicate` and `is_subtotal` on each of one document's line value dicts (the
    ingest's `_line_values` shape), deciding the whole document at once against its header
    `net_total` (None: no header to check, the guard is off)."""
    lines = list(lines)
    balanced = net_total is not None and sum(
        (Decimal(x["net_amount"]) for x in lines if x.get("net_amount") is not None), Decimal("0")
    ) == Decimal(net_total)
    if balanced:
        for line in lines:
            line["is_duplicate"] = False
            line["is_subtotal"] = False
        return

    if any(not _is_empty(line.get("parent_line_ref")) for line in lines):
        _mark_explicit_parents(lines)
    else:
        _mark_duplicates(lines, net_total)
    since_start = Decimal("0")
    since_previous = Decimal("0")
    counted = 0
    for line in sorted(lines, key=_order_key):
        if line["is_duplicate"]:
            line["is_subtotal"] = False
            continue
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
