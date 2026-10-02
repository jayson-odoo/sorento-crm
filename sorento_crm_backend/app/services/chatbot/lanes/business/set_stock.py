"""The full-access header over a product set's stock answer (COMBO-STOCK slice 2).

Plan: `documentation/plans/chatbot/PLAN-combo-stock-2oct.md` (owner answers Q1, Q2, Q4,
2 Oct 2026). A set is never stocked: "chck stock SRTWC8608-RL" is answered over its
members (`gate._expand_product_set`), and this module writes the one thing the member
lines cannot say on their own - how many COMPLETE sets that stock makes, per warehouse
and in total, and which member runs out first.

The numbers come from the SAME stock tool envelope the member lines print, never from
the resolver's own `display.available` (a raw sum over every warehouse with no
visibility filter): the header and the lines under it must never disagree.

Full access only. An `availability` envelope (a dealer) has no numbers by design
(`sorento_crm_mcp.presenters._stock_availability`) and gets no header at all - a set
count is a quantity of ours, which that mode exists never to reveal.

Pure: no I/O.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

#: The envelopes that carry numbers this header may restate: `detailed` (one row per
#: product and location) and `compact` (one item per product, Total + locations).
_DETAILED = "stock"
_COMPACT = "stock_compact"

#: Compact fields that are not a location line.
_COMPACT_NON_LOCATION = frozenset({"product code", "total"})


def _number(value: Any) -> Decimal | None:
    """A rendered quantity as a number. A granted "(O/S: n)" suffix never reaches
    `value` (it rides `granted_value`), but the first token is read anyway so a
    suffixed value still counts its stock and never its outstanding."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip().split(" ")[0].replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _field(fields: list[Any], *, key: str | None = None, label: str | None = None) -> Any:
    for f in fields:
        if not isinstance(f, dict):
            continue
        if key is not None and f.get("key") == key:
            return f.get("value")
        if label is not None and str(f.get("label") or "").strip().lower() == label:
            return f.get("value")
    return None


def _stock_by_code(envelope: dict[str, Any]) -> dict[str, tuple[Decimal, dict[str, Decimal]]] | None:
    """`{product_code: (total, {location: qty})}` read off the rendered items, or
    `None` when the envelope is not a numbered stock answer."""
    result_type = str(envelope.get("result_type") or "")
    if result_type not in (_DETAILED, _COMPACT) or envelope.get("has_result") is not True:
        return None
    out: dict[str, tuple[Decimal, dict[str, Decimal]]] = {}
    for item in envelope.get("items") or []:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), list) else []
        code = _field(fields, key="product_code") or item.get("title")
        if not code:
            continue
        code = str(code).strip().upper()
        total, locations = out.get(code, (Decimal(0), {}))
        if result_type == _COMPACT:
            total = _number(_field(fields, label="total")) or Decimal(0)
            for f in fields:
                if not isinstance(f, dict) or f.get("key") == "product_code":
                    continue
                label = str(f.get("label") or "").strip()
                if not label or label.lower() in _COMPACT_NON_LOCATION:
                    continue
                qty = _number(f.get("value"))
                if qty is not None:
                    locations[label] = qty
        else:
            location = _field(fields, key="system_location")
            qty = _number(_field(fields, key="quantity_on_hand"))
            if qty is not None:
                total += qty
                if location and str(location).strip() != "-":
                    loc = str(location).strip()
                    locations[loc] = locations.get(loc, Decimal(0)) + qty
        out[code] = (total, locations)
    return out


def _qty_text(quantity: Decimal) -> str:
    return format(quantity.normalize(), "f") if quantity != quantity.to_integral() else str(int(quantity))


def _sets(have: Decimal, per_set: Decimal) -> int:
    if per_set <= 0 or have <= 0:
        return 0
    return int(have // per_set)


def set_header(product_set: dict[str, Any], envelope: Any) -> str | None:
    """The header lines for one set, or `None` when this envelope carries no numbers
    (a dealer's availability answer, an error, an empty page) or the set has no
    members. A member with no row in the answer counts 0 and limits the set (Q4)."""
    if not isinstance(envelope, dict) or not isinstance(product_set, dict):
        return None
    stock = _stock_by_code(envelope)
    if stock is None:
        return None
    members: list[tuple[str, Decimal]] = []
    for member in product_set.get("members") or []:
        if not isinstance(member, dict) or not member.get("product_code"):
            continue
        quantity = _number(member.get("quantity")) or Decimal(1)
        members.append((str(member["product_code"]).strip(), quantity))
    if not members:
        return None

    complete: int | None = None
    limiting = ""
    for code, quantity in members:
        total = stock.get(code.upper(), (Decimal(0), {}))[0]
        supplies = _sets(total, quantity)
        if complete is None or supplies < complete:
            complete, limiting = supplies, code

    locations: list[str] = []
    for code, _quantity in members:
        for loc in stock.get(code.upper(), (Decimal(0), {}))[1]:
            if loc not in locations:
                locations.append(loc)
    by_location = [
        f"{loc} {min(_sets(stock.get(code.upper(), (Decimal(0), {}))[1].get(loc, Decimal(0)), quantity) for code, quantity in members)}"
        for loc in locations
    ]

    parts = ", ".join(f"{code} x{_qty_text(quantity)}" for code, quantity in members)
    lines = [
        f"*{product_set.get('set_code')}* is a set of {parts}.",
        f"Complete sets: {complete} (limited by {limiting})",
    ]
    if by_location:
        lines.append(f"By location: {', '.join(by_location)}")
    return "\n".join(lines)
