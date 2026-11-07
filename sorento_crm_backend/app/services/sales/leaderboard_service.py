"""The sales leaderboard (SALES-LEADERBOARD, `documentation/plans/sales/PLAN-sales-leaderboard-07nov.md`).

Every RM figure is `ask.run_ask` on the invoiced basis, grouped by the `sales_person` dimension: this module ranks,
joins the previous window by name and shapes the contract. It holds no money SQL of its own.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.finance import BillingDocument
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.reports import ask
from app.services.sales import invoiced_sales as inv

_RUN = dict(basis="invoiced", measure="amount", warehouse_codes=[], policy=None, capped_by_policy=False)
_TOP = 1000


def _grants(db: Session, user_id: str) -> frozenset[str]:
    from app.services.company_scope_resolver import resolve_user_grant_ids

    return frozenset(str(c) for c in resolve_user_grant_ids(db, str(user_id)))


def _money(value: Any) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _change(now: Any, before: Any) -> Optional[float]:
    """The engine's change rule, blank when the earlier figure is zero or negative."""
    if Decimal(str(before or 0)) <= 0:
        return None
    return ask._change_pct(now, before)


def _as_of(db: Session, grants: frozenset[str]) -> Optional[str]:
    if not grants:
        return None
    with company_scope(db, None):
        latest = (
            db.query(func.max(BillingDocument.last_synced_at))
            .filter(BillingDocument.company_id.in_(sorted(grants)))
            .scalar()
        )
    return latest.isoformat() if latest else None


def _persons_of_codes(db: Session, codes: list[str], grants: frozenset[str]) -> dict[str, str]:
    """Agent code -> the person it ranks under (its person_label, else the code itself)."""
    if not codes or not grants:
        return {}
    with company_scope(db, None):
        rows = (
            db.query(SalesAgent.sales_agent, SalesAgent.person_label)
            .filter(SalesAgent.sales_agent.in_(codes), SalesAgent.company_id.in_(sorted(grants)))
            .order_by(SalesAgent.sales_agent, SalesAgent.id)
            .all()
        )
    out: dict[str, str] = {}
    for code, person in rows:
        label = (person or "").strip()
        if label or code not in out:
            out[code] = label or code
    return out


def build(
    db: Session,
    user_id: str,
    date_from: date,
    date_to: date,
    company: Optional[str] = None,
    brands: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    previous_from: Optional[date] = None,
    previous_to: Optional[date] = None,
) -> dict[str, Any]:

    all_grants = _grants(db, user_id)
    grants = all_grants
    if company:
        if str(company) not in all_grants:
            raise AppException(status_code=403, message="Company not available to you", code="FORBIDDEN")
        grants = frozenset({str(company)})

    filters: dict[str, list[str]] = {}
    if brands:
        filters["brand"] = inv.uuid_values(list(brands), "brand")
    if categories:
        filters["category"] = inv.uuid_values(list(categories), "category")

    if previous_from is None or previous_to is None:
        previous_from, previous_to = ask.compare_window("previous_period", date_from, date_to)

    def run(frm: date, to: date, group_by: str, **extra: Any) -> dict[str, Any]:
        return ask.run_ask(
            db, group_by=group_by, date_from=frm, date_to=to, filters=filters, company_grants=grants,
            top_n=_TOP, **_RUN, **extra,
        )

    now = run(date_from, date_to, "sales_person", also=("customers",))
    before = run(previous_from, previous_to, "sales_person")
    by_code = run(date_from, date_to, "sales_agent")

    prev_by_person = {r["name"]: r["amount"] for r in before["rows"]}
    no_agent = 0.0
    ranked = []
    for r in now["rows"]:
        if r["name"] == inv.NO_AGENT:
            no_agent = _money(r["amount"])
            continue
        ranked.append(r)
    ranked.sort(key=lambda r: (-Decimal(str(r["amount"])), r["name"]))

    persons = _persons_of_codes(db, [r["name"] for r in by_code["rows"] if r["name"] != inv.NO_AGENT], grants)
    codes: dict[str, set[str]] = {}
    for r in by_code["rows"]:
        if r["name"] != inv.NO_AGENT:
            codes.setdefault(persons.get(r["name"], r["name"]), set()).add(r["name"])

    rows = []
    for rank, r in enumerate(ranked, start=1):
        prev = prev_by_person.get(r["name"], 0)
        rows.append({
            "rank": rank,
            "person": r["name"],
            "codes": sorted(codes.get(r["name"], {r["name"]})),
            "amount": _money(r["amount"]),
            "prev_amount": _money(prev),
            "change_pct": _change(r["amount"], prev),
            "customers": int(r.get("customers") or 0),
            "is_me": False,
        })

    me = None
    from app.services import own_scope

    agent_ids = own_scope.me(db, user_id).agent_ids
    if agent_ids:
        by_person = {row["person"]: row for row in rows}
        with company_scope(db, None):
            mine = db.query(SalesAgent.sales_agent, SalesAgent.person_label).filter(SalesAgent.id.in_(agent_ids)).all()
        found = [by_person[(p or "").strip() or c] for c, p in mine if ((p or "").strip() or c) in by_person]
        if found:
            best = min(found, key=lambda row: row["rank"])
            best["is_me"] = True
            me = {"person": best["person"], "rank": best["rank"]}

    total = now["total"]
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "previous_from": previous_from.isoformat(),
        "previous_to": previous_to.isoformat(),
        "as_of": _as_of(db, all_grants),
        "total": {
            "amount": _money(total["amount"]),
            "prev_amount": _money(before["total"]["amount"]),
            "change_pct": _change(total["amount"], before["total"]["amount"]),
        },
        "no_agent_amount": no_agent,
        "rows": rows,
        "me": me,
    }
