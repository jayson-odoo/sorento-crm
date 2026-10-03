"""Set-level stock answers (COMBO-STOCK; owner hand test + answers, 3 Oct 2026).

Plan: `documentation/plans/chatbot/PLAN-combo-stock-2oct.md`. A set is never stocked:
"chck stock SRTWC8608-RL" is fetched over its members (`gate._expand_product_set`) and
answered as ONE set-level reply - no component rows, no zero rows:

* staff (detailed / compact): "SET: N sets available (limited by M)" plus one line of
  the NON-ZERO locations, sorted by sets (`staff_set_answer`);
* staff, base code ("SRTWC8608"): the sets those products belong to, one line each with
  its sets available, armed as a pick (`staff_set_list`);
* dealer (availability): ONE quantity per set - "How many units of SET?" (the open
  quantity task's own one-slot wording), then "SET x N: <the existing dealer sentence>",
  the weakest part deciding and the ETA the latest part's (`dealer_set_reply`); a base
  code is a pick of the sets.

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
    if result_type not in (_DETAILED, _COMPACT):
        return None
    if envelope.get("has_result") is not True and envelope.get("items"):
        return None
    # An empty stock answer (`has_result` false, no rows) is "none of these anywhere":
    # every member counts 0 and the set reads "0 sets available" (AC-CS7).
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


def set_label(product_set: dict[str, Any]) -> str:
    """The set code, with its company when the same code was asked in two companies
    (Sorento and Mocha carry the same codes) - `label_company` is set by the caller."""
    code = str(product_set.get("set_code") or "")
    company = product_set.get("company_name")
    return f"{code} ({company})" if product_set.get("label_company") and company else code


def staff_set_answer(product_set: dict[str, Any], envelope: Any) -> str | None:
    """Q1 (a): "SET: N sets available (limited by M)" + "By location: L n, ..." (non-zero
    locations only; the line is left out when there are none)."""
    counts = set_counts(product_set, envelope)
    if counts is None:
        return None
    complete, limiting, by_location = counts
    lines = [f"{set_label(product_set)}: {complete} sets available (limited by {limiting})"]
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

    from app.models.company import Company

    set_rows = (
        db.query(ProductSet.id, ProductSet.set_code, Company.name)
        .join(ProductSetMember, ProductSetMember.product_set_id == ProductSet.id)
        .outerjoin(Company, Company.id == ProductSet.company_id)
        .filter(
            ProductSetMember.product_id.in_([str(p) for p in product_ids]),
            ProductSet.is_active.is_(True),
        )
        .distinct()
        .all()
    )
    return sorted(
        ({**_with_members(db, str(set_id), set_code), "company_name": company} for set_id, set_code, company in set_rows),
        key=lambda r: (str(r["set_code"]), str(r.get("company_name") or "")),
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
    `set_pick`). An option carries the set's code and its MEMBERS' product ids, so the
    focus a pick leaves holds real products (a follow-up "incoming?" names products, never
    a set id); the answering turn's runner recognises the group as the set
    (`sets_named_by_members`) and answers it at set level, as a typed set code."""
    return {
        "kind": "set_pick",
        "last_result_set": [
            {"idx": i, "label": set_label(s), "value": s["set_code"], "uuids": [m["uuid"] for m in s["members"]]}
            for i, s in enumerate(sets, start=1)
        ],
        "filters": {},
    }


def not_in_a_set(matched_codes: list[str], sets: list[dict[str, Any]]) -> list[str]:
    """The matched codes no listed set carries (review S1): named, never silently
    dropped. By CODE, so another company's twin of a set member is not listed."""
    in_sets = {str(m.get("product_code") or "").upper() for s in sets for m in s.get("members") or []}
    out: list[str] = []
    for code in matched_codes:
        if code and code.upper() not in in_sets and code not in out:
            out.append(code)
    return out


def staff_set_list(
    typed: str, sets: list[dict[str, Any]], envelopes: list[Any], matched_codes: list[str]
) -> tuple[str, dict[str, Any]] | None:
    """Q2 (a): "BASE sets:" then "n. SET: N sets" per set, each counted off its OWN stock
    envelope (`envelopes[i]` for `sets[i]`), and the pick a number answers."""
    lines = []
    for i, (s, envelope) in enumerate(zip(sets, envelopes), start=1):
        counts = set_counts(s, envelope)
        if counts is None:
            return None
        lines.append(f"{i}. {set_label(s)}: {counts[0]} sets")
    if not lines:
        return None
    text = [f"{typed} sets:", *lines, "Reply a number for one set's locations."]
    loose = not_in_a_set(matched_codes, sets)
    if loose:
        text.append(f"Not in a set: {', '.join(loose)}")
    return "\n".join(text), _pick(sets)


def dealer_set_pick(
    typed: str, sets: list[dict[str, Any]], matched_codes: list[str]
) -> tuple[str, dict[str, Any]] | None:
    """A dealer's base code: the sets as a numbered pick; no number of ours."""
    rows = [s for s in sets if s.get("members")]
    if not rows:
        return None
    labels = [set_label(s) for s in rows]
    head = (
        f"{typed} is part of {len(labels)} sets. Which one?"
        if len(labels) > 1
        else f"{typed} is part of set {labels[0]}. Check it?"
    )
    loose = not_in_a_set(matched_codes, rows)
    tail = [f"Not in a set: {', '.join(loose)}"] if loose else []
    return "\n".join([head, *numbered(labels), *tail]), _pick(rows)


#: Weakest first (owner Q3, 3 Oct 2026): the part that answers worst answers for the set.
_BRANCH_ORDER = ("no_incoming", "incoming", "too_big", "in_stock")


def _branch_rank(branch: Any) -> int:
    """An unknown branch ranks as `too_big`, the presenter's own fallback sentence."""
    return _BRANCH_ORDER.index(branch) if branch in _BRANCH_ORDER else _BRANCH_ORDER.index("too_big")


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
    set_code = set_label(product_set)
    # A set is not a product: no `product_id` (Customer asks' FK), its one quantity slot
    # keyed by the set itself (`turn/task.py` reads `slot_key` first).
    row: dict[str, Any] = {
        "product_id": None,
        "slot_key": product_set.get("set_id"),
        "product_code": set_code,
        "needs_quantity": True,
        "requested_qty": None,
        "branch": None,
    }
    if not rows or any(r.get("needs_quantity") for r in rows) or not all(r.get("branch") for r in rows):
        return f"How many units of {set_code}?", row
    worst = min(rows, key=lambda r: (_branch_rank(r.get("branch")), tuple(-x for x in _eta_key(r.get("eta")))))
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
    sets = product_set.get("sets")
    quantity = sets if isinstance(sets, int) and not isinstance(sets, bool) else _set_quantity(product_set, worst)
    if not tail or quantity is None:
        return f"How many units of {set_code}?", row
    line = f"{set_code} x {quantity}: {tail}"
    row.update(
        {
            "needs_quantity": False,
            "requested_qty": quantity,
            "branch": worst["branch"],
            "eta": worst.get("eta"),
            # The weakest part's own presenter stamp (`_stamp_refers`): the set line IS
            # that part's sentence, so it referred the dealer exactly when the part did.
            "refers_to_salesman": worst.get("refers_to_salesman") is True,
            "answer_summary": line,
            # The parts this row answers for (`refer_asks.referred_entries` skips them).
            "covers": [m.get("product_code") for m in product_set.get("members") or [] if m.get("product_code")],
        }
    )
    return line, row


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
    # Each set expanded here carries `sets`, the dealer's own set quantity, so the reply
    # echoes what was asked rather than working it back from a member (review S4).
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
            product_set["sets"] = sets
            out_quantities.update(member_quantities(product_set, sets))
    return out_entities, (out_quantities or None), expanded


def sets_named_by_members(db: Any, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A picked set (`_pick`) reaches the runner as its members, each labelled with the
    SET's code. Those groups, recognised: an active set of the caller's company whose
    code the entities carry and whose every member is among their uuids."""
    if db is None or not entities:
        return []
    from sqlalchemy import func

    from app.models.product_set import ProductSet

    by_code: dict[str, set[str]] = {}
    for e in entities:
        if isinstance(e, dict) and e.get("uuid") and e.get("canonical_code"):
            by_code.setdefault(str(e["canonical_code"]).upper(), set()).add(str(e["uuid"]))
    if not by_code:
        return []
    found = []
    for set_id, set_code in (
        db.query(ProductSet.id, ProductSet.set_code)
        .filter(func.upper(ProductSet.set_code).in_(list(by_code)))
        .filter(ProductSet.is_active.is_(True))
        .all()
    ):
        product_set = _with_members(db, str(set_id), set_code)
        uuids = by_code.get(str(set_code).upper(), set())
        members = {m["uuid"] for m in product_set["members"]}
        if members and members <= uuids:
            found.append(product_set)
    return found
