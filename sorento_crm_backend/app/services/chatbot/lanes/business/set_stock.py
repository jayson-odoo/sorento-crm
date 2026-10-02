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

Slice 3 (owner Q3): a BASE code ("SRTWC8608") that reached member products by prefix.
Full access keeps today's lines and adds which sets each product is part of; a dealer
is offered those sets as a pick instead. Membership is read off `product_set_members`
(`sets_containing`, the one ORM read here), never guessed from the code.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.chatbot.turn.task import numbered

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


def sets_containing(db: Any, product_ids: list[str]) -> list[dict[str, Any]]:
    """Every active set carrying any of `product_ids`, ordered by set code:
    `{set_code, product_ids (the asked ones it carries), member_ids (all of its)}`.

    ORM only: `ProductSet` carries `CompanyScopedMixin`, so the `do_orm_execute`
    listener scopes this to the caller's company, and its members are read only
    THROUGH a visible set (the same rule `entity_resolver._probe_product_set` keeps)."""
    if db is None or not product_ids:
        return []
    from app.models.product_set import ProductSet, ProductSetMember

    asked = {str(p) for p in product_ids}
    hits = (
        db.query(ProductSet.id, ProductSet.set_code, ProductSetMember.product_id)
        .join(ProductSetMember, ProductSetMember.product_set_id == ProductSet.id)
        .filter(ProductSetMember.product_id.in_(list(asked)), ProductSet.is_active.is_(True))
        .all()
    )
    by_set: dict[str, dict[str, Any]] = {}
    for set_id, set_code, product_id in hits:
        row = by_set.setdefault(
            str(set_id), {"set_id": str(set_id), "set_code": set_code, "product_ids": []}
        )
        row["product_ids"].append(str(product_id))
    for set_id, row in by_set.items():
        row["member_ids"] = [
            str(member_id)
            for (member_id,) in db.query(ProductSetMember.product_id)
            .filter(ProductSetMember.product_set_id == set_id)
            .order_by(ProductSetMember.sort_order)
            .all()
        ]
    return sorted(by_set.values(), key=lambda r: str(r["set_code"]))


def part_of_set_lines(prefix_products: list[dict[str, Any]], sets: list[dict[str, Any]]) -> list[str]:
    """Full access (Q3a): one line per prefix-matched product that is in at least one
    set, in the order the products were matched."""
    lines: list[str] = []
    seen: set[str] = set()
    for product in prefix_products:
        uuid = str(product.get("uuid") or "")
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        codes = [str(s["set_code"]) for s in sets if uuid in s.get("product_ids", [])]
        if codes:
            lines.append(
                f"{product.get('code')} is part of set(s) {', '.join(codes)} - "
                "ask for the set code to see full-set stock."
            )
    return lines


#: `fetch.output_structurer`'s closing line ("_Data last updated: <ts>_"): it stays last.
_FOOTER_PREFIX = "_Data last updated:"


def above_footer(response: str, block: str) -> str:
    """`block` appended to `response`, kept above the data-freshness footer when the
    reply ends with one - the same placement the counted-set lines use."""
    body = response.rstrip()
    head, sep, last = body.rpartition("\n")
    if last.strip().startswith(_FOOTER_PREFIX):
        return f"{head.rstrip()}\n\n{block}\n\n{last.strip()}" if sep else f"{block}\n\n{last.strip()}"
    return f"{body}\n\n{block}"


def set_pick(typed: str, sets: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Dealer (Q3, availability access): the sets as a numbered pick, and the
    `lane_ask` that arms it (`turn/compose.py::_lane_question`, kind `set_pick`). Each
    row carries the set's members, which a pick answers over exactly like a set code."""
    rows = [s for s in sets if s.get("member_ids")]
    if not rows:
        return None
    labels = [str(s["set_code"]) for s in rows]
    head = f"{typed} is part of {len(labels)} sets. Which one?" if len(labels) > 1 else f"{typed} is part of set {labels[0]}. Check it?"
    ask = {
        "kind": "set_pick",
        "last_result_set": [
            {"idx": i, "label": s["set_code"], "value": s["set_code"], "uuids": list(s["member_ids"])}
            for i, s in enumerate(rows, start=1)
        ],
        "filters": {},
    }
    return "\n".join([head, *numbered(labels)]), ask
