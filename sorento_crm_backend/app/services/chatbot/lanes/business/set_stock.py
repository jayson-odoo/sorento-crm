"""Set-level stock answers (COMBO-STOCK; owner hand test + answers, 3 Oct 2026).

Plan: `documentation/plans/chatbot/PLAN-combo-stock-2oct.md`. A set is never stocked:
"chck stock SRTWC8608-RL" is fetched over its members (`gate._expand_product_set`) and
answered as ONE set-level reply - no component rows, no zero rows:

* staff (detailed / compact): "SET: N sets available (limited by M)" plus one line of
  the NON-ZERO locations, sorted by sets (`staff_set_answer`);
* staff, base code ("SRTWC8608"): the sets those products belong to, one line each with
  its sets available, armed as a pick (`staff_set_list`);
* dealer (availability): ONE quantity per set - "SET: how many sets do you need?", then
  "SET x N: <the existing dealer sentence>", the weakest part deciding and the ETA the
  latest part's (`dealer_set_reply`); a base code is a pick of the sets.

Numbers are read off the SAME stock tool envelope (`_stock_by_code`), so the visibility
policy that shaped it shaped the set count too. Membership is `product_set_members`
only (`sets_containing`, `expand_task_sets`: the ORM reads here), never the code's shape.
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
    discontinued: set[str] = set()
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
        if (item.get("flags") or {}).get("discontinued") is True:
            # The resolver's and the set screen's own rule (`entity_resolver.
            # _probe_product_set`): a discontinued member supplies nothing.
            total, locations = Decimal(0), {loc: Decimal(0) for loc in locations}
            discontinued.add(code)
        elif code in discontinued:
            total, locations = Decimal(0), {loc: Decimal(0) for loc in locations}
        out[code] = (total, locations)
    return out


def _qty_text(quantity: Decimal) -> str:
    return format(quantity.normalize(), "f") if quantity != quantity.to_integral() else str(int(quantity))


def _sets(have: Decimal, per_set: Decimal) -> int:
    if per_set <= 0 or have <= 0:
        return 0
    return int(have // per_set)


def _members(product_set: dict[str, Any]) -> list[tuple[str, Decimal]]:
    out: list[tuple[str, Decimal]] = []
    for member in product_set.get("members") or []:
        if isinstance(member, dict) and member.get("product_code"):
            out.append((str(member["product_code"]).strip(), _number(member.get("quantity")) or Decimal(1)))
    return out


def set_counts(product_set: dict[str, Any], envelope: Any) -> tuple[int, str, list[tuple[str, int]]] | None:
    """`(complete sets, limiting member, [(location, sets)])` for one set, the locations
    NON-ZERO only and sorted by sets (most first, then name), or None when the envelope
    carries no numbers (a dealer's, an error) or the set has no members. A member with no
    row counts 0 and limits the set; a tie names the first member in set order."""
    if not isinstance(envelope, dict) or not isinstance(product_set, dict):
        return None
    stock = _stock_by_code(envelope)
    members = _members(product_set)
    if stock is None or not members:
        return None
    empty: tuple[Decimal, dict[str, Decimal]] = (Decimal(0), {})
    complete: int | None = None
    limiting = ""
    for code, quantity in members:
        supplies = _sets(stock.get(code.upper(), empty)[0], quantity)
        if complete is None or supplies < complete:
            complete, limiting = supplies, code
    locations: list[str] = []
    for code, _quantity in members:
        for loc in stock.get(code.upper(), empty)[1]:
            if loc not in locations:
                locations.append(loc)
    by_location = [
        (loc, min(_sets(stock.get(code.upper(), empty)[1].get(loc, Decimal(0)), q) for code, q in members))
        for loc in locations
    ]
    by_location = sorted(((loc, n) for loc, n in by_location if n > 0), key=lambda r: (-r[1], r[0]))
    return int(complete or 0), limiting, by_location


def staff_set_answer(product_set: dict[str, Any], envelope: Any) -> str | None:
    """Q1 (a): "SET: N sets available (limited by M)" + "By location: L n, ..." (non-zero
    locations only; the line is left out when there are none)."""
    counts = set_counts(product_set, envelope)
    if counts is None:
        return None
    complete, limiting, by_location = counts
    lines = [f"{product_set.get('set_code')}: {complete} sets available (limited by {limiting})"]
    if by_location:
        lines.append("By location: " + ", ".join(f"{loc} {n}" for loc, n in by_location))
    return "\n".join(lines)


def sets_containing(db: Any, product_ids: list[str]) -> list[dict[str, Any]]:
    """Every active set carrying any of `product_ids`, ordered by set code:
    `{set_id, set_code, members: [{uuid, product_code, quantity}]}`.

    ORM only: `ProductSet` carries `CompanyScopedMixin`, so the `do_orm_execute`
    listener scopes this to the caller's company, and its members are read only
    THROUGH a visible set (the same rule `entity_resolver._probe_product_set` keeps)."""
    if db is None or not product_ids:
        return []
    from app.models.product_set import ProductSet, ProductSetMember

    set_rows = (
        db.query(ProductSet.id, ProductSet.set_code)
        .join(ProductSetMember, ProductSetMember.product_set_id == ProductSet.id)
        .filter(
            ProductSetMember.product_id.in_([str(p) for p in product_ids]),
            ProductSet.is_active.is_(True),
        )
        .distinct()
        .all()
    )
    return sorted(
        (_with_members(db, str(set_id), set_code) for set_id, set_code in set_rows),
        key=lambda r: str(r["set_code"]),
    )


def _with_members(db: Any, set_id: str, set_code: str) -> dict[str, Any]:
    from app.models.product import Product
    from app.models.product_set import ProductSetMember

    rows = (
        db.query(ProductSetMember.product_id, ProductSetMember.quantity, Product.product_code)
        .join(Product, Product.id == ProductSetMember.product_id)
        .filter(ProductSetMember.product_set_id == set_id)
        .order_by(ProductSetMember.sort_order)
        .all()
    )
    return {
        "set_id": set_id,
        "set_code": set_code,
        "members": [
            {"uuid": str(pid), "product_code": code, "quantity": float(qty or 1)}
            for pid, qty, code in rows
        ],
    }


def _pick(sets: list[dict[str, Any]]) -> dict[str, Any]:
    """The `lane_ask` arming a pick of sets (`turn/compose.py::_lane_question`, kind
    `set_pick`). An option carries the set's code and its own id; the answering turn's
    runner turns that id into the set's members (`turn_runtime._set_entities`), the same
    set-level answer a typed set code gets."""
    return {
        "kind": "set_pick",
        "last_result_set": [
            {"idx": i, "label": s["set_code"], "value": s["set_code"], "uuid": s["set_id"]}
            for i, s in enumerate(sets, start=1)
        ],
        "filters": {},
    }


def staff_set_list(typed: str, sets: list[dict[str, Any]], envelope: Any) -> tuple[str, dict[str, Any]] | None:
    """Q2 (a): "BASE sets:" then "n. SET: N sets" per set, counted off `envelope` (the
    stock tool over every member of those sets), and the pick a number answers."""
    rows = [s for s in sets if s.get("members")]
    lines = []
    for i, s in enumerate(rows, start=1):
        counts = set_counts(s, envelope)
        if counts is None:
            return None
        lines.append(f"{i}. {s['set_code']}: {counts[0]} sets")
    if not lines:
        return None
    text = "\n".join([f"{typed} sets:", *lines, "Reply a number for one set's locations."])
    return text, _pick(rows)


def dealer_set_pick(typed: str, sets: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """A dealer's base code: the sets as a numbered pick; no number of ours."""
    rows = [s for s in sets if s.get("members")]
    if not rows:
        return None
    labels = [str(s["set_code"]) for s in rows]
    head = (
        f"{typed} is part of {len(labels)} sets. Which one?"
        if len(labels) > 1
        else f"{typed} is part of set {labels[0]}. Check it?"
    )
    return "\n".join([head, *numbered(labels)]), _pick(rows)


#: Weakest first (owner Q3, 3 Oct 2026): the part that answers worst answers for the set.
_BRANCH_ORDER = ("no_incoming", "incoming", "too_big", "in_stock")


def _eta_key(eta: Any) -> tuple[int, int, int]:
    try:
        day, month, year = (int(x) for x in str(eta).split("/"))
        return year, month, day
    except (TypeError, ValueError):
        return 0, 0, 0


def dealer_set_reply(product_set: dict[str, Any], envelope: Any) -> tuple[str, dict[str, Any]] | None:
    """The dealer's ONE line for a set, and the ONE `stock_availability` row standing for
    it (keyed by the set, so the open quantity task holds one slot for the set).

    Every member still owing a quantity: "SET: how many sets do you need?". Otherwise
    the weakest member's own presenter sentence (the item title "<code> x <q>: ...",
    `sorento_crm_mcp.presenters._availability_line`) is re-said for the set, so the four
    fixed sentences stay the only wording and no number of ours appears; among
    `incoming` members the latest ETA answers."""
    if not isinstance(envelope, dict) or envelope.get("result_type") != "stock_availability":
        return None
    codes = {str(m.get("product_code") or "").upper() for m in product_set.get("members") or []}
    rows = [
        r for r in envelope.get("stock_availability") or []
        if isinstance(r, dict) and str(r.get("product_code") or "").upper() in codes
    ]
    set_code = str(product_set.get("set_code") or "")
    row: dict[str, Any] = {
        "product_id": product_set.get("set_id"),
        "product_code": set_code,
        "needs_quantity": True,
        "requested_qty": None,
        "branch": None,
    }
    if not rows or any(r.get("needs_quantity") for r in rows) or not all(r.get("branch") for r in rows):
        return f"How many units of {set_code}?", row
    worst = min(rows, key=lambda r: (_BRANCH_ORDER.index(r["branch"]) if r["branch"] in _BRANCH_ORDER else 0,
                                      tuple(-x for x in _eta_key(r.get("eta")))))
    title = next(
        (
            str(it.get("title") or "")
            for it in envelope.get("items") or []
            if isinstance(it, dict)
            and str(it.get("title") or "").upper().startswith(f"{str(worst.get('product_code')).upper()} X ")
        ),
        "",
    )
    tail = title.split(": ", 1)[1] if ": " in title else ""
    quantity = _set_quantity(product_set, worst)
    if not tail or quantity is None:
        return f"How many units of {set_code}?", row
    row.update(
        {
            "needs_quantity": False,
            "requested_qty": quantity,
            "branch": worst["branch"],
            "eta": worst.get("eta"),
        }
    )
    return f"{set_code} x {quantity}: {tail}", row


def _set_quantity(product_set: dict[str, Any], member_row: dict[str, Any]) -> int | None:
    """How many SETS the member's own asked quantity stands for (asked / qty per set)."""
    asked = member_row.get("requested_qty")
    if not isinstance(asked, int) or isinstance(asked, bool):
        return None
    code = str(member_row.get("product_code") or "").upper()
    per_set = next(
        (_number(m.get("quantity")) or Decimal(1)
         for m in product_set.get("members") or [] if str(m.get("product_code") or "").upper() == code),
        Decimal(1),
    )
    return int(Decimal(asked) / per_set) if per_set > 0 else None


def member_quantities(product_set: dict[str, Any], sets: int) -> dict[str, int]:
    """`{member uuid: sets x qty per set}` (rounded up), the per-product quantities the
    stock tool's availability read takes."""
    out: dict[str, int] = {}
    for m in product_set.get("members") or []:
        if isinstance(m, dict) and m.get("uuid"):
            per_set = _number(m.get("quantity")) or Decimal(1)
            out[str(m["uuid"])] = int((Decimal(sets) * per_set).to_integral_value(rounding="ROUND_CEILING"))
    return out


def expand_task_sets(
    db: Any, entities: list[dict[str, Any]], quantities: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, int] | None, list[dict[str, Any]]]:
    """The dealer's open quantity task holds ONE slot per SET (`dealer_set_reply`'s row,
    keyed by the set id). Its fetch names the set id as a product; here it becomes the
    set's members and the set quantity becomes theirs. Returns (entities, quantities,
    the sets expanded). Anything that is not a visible, active set passes through."""
    if db is None or not entities:
        return entities, quantities, []
    from app.models.product_set import ProductSet

    ids = [str(e.get("uuid")) for e in entities if isinstance(e, dict) and e.get("uuid")]
    if not ids:
        return entities, quantities, []
    found = {
        str(set_id): set_code
        for set_id, set_code in db.query(ProductSet.id, ProductSet.set_code)
        .filter(ProductSet.id.in_(ids), ProductSet.is_active.is_(True))
        .all()
    }
    if not found:
        return entities, quantities, []
    out_entities: list[dict[str, Any]] = []
    out_quantities = dict(quantities or {})
    expanded: list[dict[str, Any]] = []
    for e in entities:
        set_id = str(e.get("uuid")) if isinstance(e, dict) else ""
        if set_id not in found:
            out_entities.append(e)
            continue
        product_set = _with_members(db, set_id, found[set_id])
        expanded.append(product_set)
        for m in product_set["members"]:
            out_entities.append({**e, "uuid": m["uuid"], "canonical_code": m["product_code"], "raw": m["product_code"]})
        sets = out_quantities.pop(set_id, None)
        if isinstance(sets, int) and not isinstance(sets, bool):
            out_quantities.update(member_quantities(product_set, sets))
    return out_entities, (out_quantities or None), expanded
