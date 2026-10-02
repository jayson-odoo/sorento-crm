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
