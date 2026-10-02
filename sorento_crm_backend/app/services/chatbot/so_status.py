"""SO-NUMBER-ASK: the chatbot's answer to "status of SO421624".

The resolver places DO numbers only (`entity_resolver._probe_customer_order` reads
`orders.order_number`), so an SO number reaches the order lane as a word nothing placed.
This module answers it from `sales_orders` directly, on the engine's own per-contact scoped
session (company scope applies, so another company's SO is simply not found) - the same
precedent `services.resolve_warehouse_token` set for a lane read that has no MCP tool.

One card per SO, words only (owner rulings on PR #1435, behaviour card v2):

    *SO421624* - HANLIM TRADING SDN BHD [A/C I]
    Ordered 15 Sep 2026 - Open
    Delivery: partly delivered

No DO numbers: the SO->DO link (`orders.sales_order_id`) is empty in the data, so delivery is
read off `sales_order_lines.qty_ordered` / `qty_delivered` instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine

#: AutoCount's SO numbering ("SO422056"). A word of this shape that nothing placed is an SO ask.
SO_NUMBER_RE = re.compile(r"^SO\d{4,}$")
_SEPARATORS = re.compile(r"[\s-]+")

CANCELLED_MARK = "❗ Cancelled"


def so_key(word: str) -> str:
    """"so 421624" and "SO-421624" are SO421624: AutoCount stores the number upper case and
    unbroken, and the resolver's own token key folds the same separators away."""
    return _SEPARATORS.sub("", word).upper()


def is_so_number(word: Any) -> bool:
    return isinstance(word, str) and bool(SO_NUMBER_RE.match(so_key(word)))


@dataclass
class SoLookup:
    """`cards` in the order the numbers were typed; `refused` when any SO exists outside the
    contact's links; `missing` the typed words no SO answered, as typed."""

    cards: list[str] = field(default_factory=list)
    refused: bool = False
    missing: list[str] = field(default_factory=list)


def _status_words(status: str | None) -> str:
    s = (status or "").strip().lower()
    if s == "cancelled":
        return CANCELLED_MARK
    return s.capitalize() if s else "Unknown"


def _delivery_words(lines: list[tuple[Any, Any]]) -> str | None:
    """Over the lines that are not cancelled: none delivered, every line in full, or between."""
    if not lines:
        return None
    if all((delivered or 0) <= 0 for _ordered, delivered in lines):
        return "not delivered yet"
    if all((delivered or 0) >= (ordered or 0) for ordered, delivered in lines):
        return "fully delivered"
    return "partly delivered"


def _card(so: SalesOrder, name: str | None, lines: list[tuple[Any, Any]]) -> str:
    head = f"*{so.so_number}*" + (f" - {name}" if name else "")
    status = _status_words(so.status)
    second = f"Ordered {so.order_date.day} {so.order_date:%b %Y} - {status}" if so.order_date else status
    out = [head, second]
    if status != CANCELLED_MARK:
        delivery = _delivery_words(lines)
        if delivery:
            out.append(f"Delivery: {delivery}")
    return "\n".join(out)


def lookup(
    db: Session,
    words: Iterable[str],
    *,
    linked: Iterable[tuple[str, str, str]] | None,
) -> SoLookup:
    """Answer each typed SO word. `linked` is the contact's enforced customer scope
    (`(id, name, code)` per link), or None when no scope is enforced (staff, unlinked).

    In scope: the SO's customer is a link, or it has no customer and its debtor code is the
    code of a link IN THE SAME COMPANY (both SO importers keep the code when it resolves to
    nobody, and one code can name different debtors in two companies)."""
    typed = [w.strip() for w in words if is_so_number(w)]
    out = SoLookup()
    if not typed:
        return out
    keys = {so_key(w) for w in typed}
    rows = (
        db.query(SalesOrder, Customer.customer_name)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .filter(SalesOrder.so_number.in_(keys))
        .all()
    )
    by_number: dict[str, list[tuple[SalesOrder, str | None]]] = {}
    for so, master_name in rows:
        by_number.setdefault(so.so_number.upper(), []).append((so, master_name))
    lines_by_so: dict[str, list[tuple[Any, Any]]] = {}
    if rows:
        for so_id, ordered, delivered in (
            db.query(SalesOrderLine.sales_order_id, SalesOrderLine.qty_ordered, SalesOrderLine.qty_delivered)
            .filter(
                SalesOrderLine.sales_order_id.in_([so.id for so, _ in rows]),
                func.coalesce(SalesOrderLine.line_status, "") != "cancelled",
            )
            .all()
        ):
            lines_by_so.setdefault(str(so_id), []).append((ordered, delivered))

    links = list(linked) if linked is not None else None
    link_ids = {str(i) for i, _n, _c in links} if links is not None else set()
    link_codes: set[tuple[str, str]] = set()
    if link_ids and any(so.customer_id is None for so, _ in rows):
        link_codes = {
            (str(company_id), code.strip().upper())
            for company_id, code in db.query(Customer.company_id, Customer.customer_code)
            .filter(Customer.id.in_(link_ids))
            .all()
            if code
        }

    def _in_scope(so: SalesOrder) -> bool:
        if links is None:
            return True
        if so.customer_id:
            return str(so.customer_id) in link_ids
        return (str(so.company_id), (so.debtor_code or "").strip().upper()) in link_codes

    seen: set[str] = set()
    for word in typed:
        key = so_key(word)
        if key in seen:
            continue
        seen.add(key)
        found = by_number.get(key) or []
        if not found:
            out.missing.append(word)
            continue
        visible = [(so, name) for so, name in found if _in_scope(so)]
        if not visible:
            out.refused = True
            continue
        for so, master_name in visible:
            out.cards.append(_card(so, so.debtor_name or master_name, lines_by_so.get(str(so.id), [])))
    return out


def reply_text(result: SoLookup, *, refusal: str) -> str:
    """Cards, then the scope refusal, then one miss line - each its own paragraph."""
    parts = list(result.cards)
    if result.refused and refusal:
        parts.append(refusal)
    if result.missing:
        words = result.missing
        joined = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]
        parts.append(f"I could not find {joined}.")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# The SO LIST: "all my sales orders" / "my SOs" (owner option (2), behaviour card rulings)
# --------------------------------------------------------------------------- #


def _day(d: Any) -> str:
    return f"{d.day} {d:%b %Y}"


def period_reply(start: Any, end: Any, subject: str | None) -> str | None:
    """Q1 (a): the DO ask's period rule for an SO list, or None when the period is fine.

    The same rule as `do_ask.range_reply` (its cap, its "today", its month and span words),
    in the words of a sales order list; `do_ask` is the DO list's own and is not bent to
    speak about sales orders."""
    from datetime import timedelta

    from app.services.chatbot import do_ask

    today = do_ask.today_myt()
    if start is None and end is None:
        this_month = today.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        return (f"Which period for {subject}?\n" if subject else "Which period?\n") + (
            f"- This month ({do_ask._month(this_month)})\n"
            f"- Last month ({do_ask._month(last_month)})\n"
            "Or type a month (e.g. August) or dates (e.g. 15 Sep to 10 Oct)."
        )
    end = end or today
    if start is not None and start > end:
        start, end = end, start
    days = (end - start).days + 1 if start is not None else None
    if days is not None and days <= do_ask.MAX_DAYS:
        return None
    last = min(end, today)
    suggestions = [do_ask._month(last)]
    lead = ""
    if start is not None:
        if start <= last and do_ask._month(start) not in suggestions:
            suggestions.append(do_ask._month(start))
        lead = (
            f"That is {do_ask._span(start, end, days)} "
            f"({do_ask._ddmmyyyy(start)} to {do_ask._ddmmyyyy(end)}). "
        )
    return (
        f"{lead}I can show up to {do_ask.MAX_DAYS} days of sales orders at a time:\n"
        + "".join(f"- {s}\n" for s in suggestions)
        + "Or type a month or dates."
    )


def customer_names(db: Session, customer_ids: Iterable[str]) -> dict[str, str]:
    """The customers' names, in the order given (link order), so the header reads as the
    contact's own accounts are listed everywhere else."""
    ids = list(dict.fromkeys(str(i) for i in customer_ids if i))
    if not ids:
        return {}
    found = {
        str(cid): name or ""
        for cid, name in db.query(Customer.id, Customer.customer_name).filter(Customer.id.in_(ids)).all()
    }
    return {cid: found[cid] for cid in ids if cid in found}


def list_text(db: Session, names_by_id: dict[str, str], start: Any, end: Any) -> str:
    """Q2 (a) newest first, every status; Q3 (a) the group named once, or on every row when
    the customers span groups. Only SOs whose customer is one of `names_by_id` (the turn's
    customers in scope), on the engine's company-scoped session."""
    from app.services.ledger_family import family_words, group_names

    header_names = family_words(list(names_by_id.values())) or "your account"
    window = f"{_day(start)} to {_day(end)}"
    rows = (
        db.query(SalesOrder)
        .filter(
            SalesOrder.customer_id.in_(list(names_by_id)),
            SalesOrder.order_date >= start,
            SalesOrder.order_date <= end,
        )
        .order_by(SalesOrder.order_date.desc(), SalesOrder.so_number.desc())
        .all()
    )
    if not rows:
        return f"No sales orders for {header_names} from {_day(start)} to {_day(end)}."
    lines_by_so: dict[str, list[tuple[Any, Any]]] = {}
    for so_id, ordered, delivered in (
        db.query(SalesOrderLine.sales_order_id, SalesOrderLine.qty_ordered, SalesOrderLine.qty_delivered)
        .filter(
            SalesOrderLine.sales_order_id.in_([so.id for so in rows]),
            func.coalesce(SalesOrderLine.line_status, "") != "cancelled",
        )
        .all()
    ):
        lines_by_so.setdefault(str(so_id), []).append((ordered, delivered))
    several_groups = len(group_names(list(names_by_id.values()))) > 1
    out = [f"Sales orders for {header_names}, {window}:"]
    for so in rows:
        parts = [so.so_number, _day(so.order_date)]
        if several_groups:
            group = group_names([so.debtor_name or names_by_id.get(str(so.customer_id)) or ""])
            if group:
                parts.append(group[0])
        status = _status_words(so.status)
        parts.append(status)
        if status != CANCELLED_MARK:
            delivery = _delivery_words(lines_by_so.get(str(so.id), []))
            if delivery:
                parts.append(delivery)
        out.append(" - ".join(parts))
    return "\n".join(out)
