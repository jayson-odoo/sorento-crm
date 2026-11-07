"""The sales leaderboard (SALES-LEADERBOARD, `documentation/plans/sales/PLAN-sales-leaderboard-07nov.md`; phase 2:
`PLAN-sales-insights-p2-07nov.md`).

Every RM figure is `ask.run_ask` on the chosen basis, grouped by the chosen view: this module checks access, ranks,
joins the previous window by name and shapes the contract. It holds no money SQL of its own; a person's target
reads `achievement_service` through `target_service`'s own path.
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
from app.services.reports import ask, engine
from app.services.sales import invoiced_sales as inv

_RUN = dict(measure="amount", warehouse_codes=[], policy=None, capped_by_policy=False)

BASES = ("invoiced", "delivered", "ordered", "outstanding")
BYS = ("person", "customer", "product", "brand", "category", "channel")
#: The permission that opens every view but the person board, per basis (Q2).
_SLUG = {"invoiced": inv.INVOICED_SLUG, "delivered": "order_management.orders.view",
         "ordered": "order_management.orders.view", "outstanding": "order_management.orders.view"}
#: The engine's dimension behind each view.
_DIMENSION = {"person": "sales_person"}
_OPEN_FROM, _OPEN_TO = date(1900, 1, 1), date(2200, 12, 31)
_CHANNEL_KEYS = {**{label: value for value, label in inv.SALES_TYPES}}
_ORDER_CHANNELS = (("dealer", "Dealer"), ("project", "Project team"), ("other", "Other"))


#: The engine's "(blank)" row, named for the view it sits in; kept so a view's rows add up to its total.
_BLANK_NAMES = {"customer": "(no customer)", "product": "(no product)", "brand": "(no brand)",
                "category": "(no category)", "channel": "(none)"}


def channel_options() -> dict[str, list[dict[str, str]]]:
    order = [{"value": v, "label": label} for v, label in _ORDER_CHANNELS]
    return {"invoiced": [{"value": v, "label": label} for v, label in inv.SALES_TYPES],
            "delivered": order, "ordered": order, "outstanding": order}


def can_by_basis(db: Session, user: dict) -> dict[str, bool]:
    from app.services.user_service import holds_permission

    return {basis: holds_permission(db, user, _SLUG[basis]) for basis in BASES}


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="REPORT_INVALID_PARAMS")


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


def _person_of(label: Optional[str], code: str) -> str:
    """The person a code ranks under: its person_label (btrim, as the SQL), else the code itself."""
    return (label or "").strip(" ") or code


def _codes_by_person(db: Session, run: Any, grants: frozenset[str]) -> dict[str, set[tuple[str, str]]]:
    """Person -> the (company, agent code) pairs that sold in the period. A code is read per company (the same code
    may be a different person in another company), so the engine's `sales_agent` grouping runs once per granted
    company."""
    codes: dict[str, set[tuple[str, str]]] = {}
    for company_id in sorted(grants):
        names = [r["name"] for r in run(company_grants=frozenset({company_id}))["rows"] if r["name"] != inv.NO_AGENT]
        if not names:
            continue
        with company_scope(db, None):
            labels = dict(
                db.query(SalesAgent.sales_agent, SalesAgent.person_label)
                .filter(SalesAgent.sales_agent.in_(names), SalesAgent.company_id == company_id)
                .order_by(SalesAgent.id)
                .all()
            )
        for name in names:
            codes.setdefault(_person_of(labels.get(name), name), set()).add((company_id, name))
    return codes


def _own_persons(db: Session, user_id: str) -> set[str]:
    from app.services import own_scope

    agent_ids = own_scope.me(db, user_id).agent_ids
    if not agent_ids:
        return set()
    with company_scope(db, None):
        mine = db.query(SalesAgent.sales_agent, SalesAgent.person_label).filter(SalesAgent.id.in_(agent_ids)).all()
    return {_person_of(p, c) for c, p in mine}


def _own_agent_ids(db: Session, user_id: str) -> list[str]:
    """The caller's own agents and their same-company label siblings (one person, several codes): the only agents
    an own-person drill may read, whatever another company's agent is called."""
    from app.services import own_scope
    from app.services.sales import achievement_service

    ids = own_scope.me(db, user_id).agent_ids
    if not ids:
        return []
    with company_scope(db, None):
        by_company: dict[Any, set[str]] = {}
        for agent_id, company_id in db.query(SalesAgent.id, SalesAgent.company_id).filter(SalesAgent.id.in_(ids)):
            by_company.setdefault(company_id, set()).add(str(agent_id))
        out = set(str(i) for i in ids)
        for company_id, agents in by_company.items():
            if company_id is not None:
                for siblings in achievement_service.label_siblings(db, company_id, agents).values():
                    out |= {str(i) for i in siblings}
    return sorted(out)


def _check_access(
    db: Session, user: dict, basis: str, by: str, persons: list[str], customers: list[str], products: list[str]
) -> tuple[bool, Optional[list[str]]]:
    """403 unless the caller may see this slice (Q2). Returns whether they hold the basis slug and, when the way in
    was the own-person exception, the agent ids every figure must be narrowed to."""
    from app.services.user_service import holds_permission

    holds = holds_permission(db, user, _SLUG[basis])
    board = by == "person" and not (persons or customers or products)
    if holds or board:
        return holds, None
    if persons and set(persons) <= _own_persons(db, str(user["id"])):
        return holds, _own_agent_ids(db, str(user["id"]))
    raise AppException(status_code=403, message="Not available to you", code="PERMISSION_DENIED")


def _targets(
    db: Session, grants: frozenset[str], people: dict[str, set[str]], basis: str, date_from: Optional[date],
    date_to: Optional[date],
) -> dict[str, dict[str, Any]]:
    """Person -> the lowest-numbered agent target (amount, all products) whose period holds the board's end date.
    `people` maps a row's person to the companies its codes sold in: a target of another company's agent that merely
    shares the label or code is not the row's."""
    from app.models.sales import SalesTarget, SalesTargetPeriod
    from app.services.sales import achievement_service, target_service

    if not people or not grants:
        return {}
    anchor = date_to or target_service._today()
    with company_scope(db, None):
        found = (
            db.query(SalesTarget, SalesTargetPeriod, SalesAgent.person_label, SalesAgent.sales_agent)
            .join(SalesAgent, SalesAgent.id == SalesTarget.sales_agent_id)
            .join(SalesTargetPeriod, SalesTargetPeriod.target_id == SalesTarget.id)
            .filter(
                SalesTarget.company_id.in_(sorted(grants)), SalesTarget.subject_kind == "agent",
                SalesTarget.metric == "amount", SalesTarget.product_scope == "all",
                SalesTargetPeriod.period_start <= anchor, SalesTargetPeriod.period_end >= anchor,
                SalesTargetPeriod.target_value > 0,
            )
            .order_by(SalesTarget.target_no, SalesTargetPeriod.period_start)
            .all()
        )
        chosen: dict[str, tuple[Any, Any]] = {}
        for target, period, label, code in found:
            person = _person_of(label, code)
            if person in people and target.company_id in people[person] and person not in chosen:
                chosen[person] = (target, period)
        achieved: dict[str, Decimal] = {}
        for company_id in {t.company_id for t, _p in chosen.values()}:
            pairs = [(t, p) for t, p in chosen.values() if t.company_id == company_id]
            for pid, by_account in target_service._achieved_by_account(db, company_id, pairs).items():
                achieved[pid] = sum(by_account.values(), Decimal("0"))
    out = {}
    for person, (target, period) in chosen.items():
        got = achieved.get(period.id, Decimal("0"))
        out[person] = {
            "target_no": target.target_no,
            "basis": target.basis,
            "period_from": period.period_start.isoformat(),
            "period_to": period.period_end.isoformat(),
            "target_amount": _money(period.target_value),
            "achieved_amount": _money(got),
            "achieved_pct": achievement_service.achieved_pct(got, period.target_value),
            "like_for_like": target.basis == basis and (period.period_start, period.period_end) == (date_from, date_to),
        }
    return out


def _customer_info(db: Session, keys: set[str]) -> dict[str, tuple[str, str]]:
    from app.models.company import Company
    from app.models.order import Customer

    if not keys:
        return {}
    with company_scope(db, None):
        rows = (
            db.query(Customer.id, Customer.customer_code, Company.code)
            .outerjoin(Company, Company.id == Customer.company_id)
            .filter(Customer.id.in_(sorted(keys)))
            .all()
        )
    return {str(i): (code or "", company or "") for i, code, company in rows}


def _product_info(db: Session, keys: set[str]) -> dict[str, tuple[Optional[str], Optional[str]]]:
    from app.models.product import Brand, Product, ProductCategory

    if not keys:
        return {}
    with company_scope(db, None):
        rows = (
            db.query(Product.id, Brand.brand_name, ProductCategory.category_name)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .filter(Product.id.in_(sorted(keys)))
            .all()
        )
    return {str(i): (brand, category) for i, brand, category in rows}


def build(
    db: Session,
    user: dict,
    date_from: Optional[date],
    date_to: Optional[date],
    basis: str = "invoiced",
    by: str = "person",
    company: Optional[str] = None,
    brands: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    channels: Optional[list[str]] = None,
    persons: Optional[list[str]] = None,
    customers: Optional[list[str]] = None,
    products: Optional[list[str]] = None,
    previous_from: Optional[date] = None,
    previous_to: Optional[date] = None,
) -> dict[str, Any]:
    if basis not in BASES:
        raise _invalid(f"basis is one of {', '.join(BASES)}")
    if by not in BYS:
        raise _invalid(f"by is one of {', '.join(BYS)}")
    open_basis = basis == "outstanding"
    if (date_from is None) != (date_to is None) or (date_from is None and not open_basis):
        raise _invalid("date_from and date_to are required" if not open_basis else "date_from and date_to go together")
    persons, customers, products = list(persons or []), list(customers or []), list(products or [])
    customers, products = inv.uuid_values(customers, "customer"), inv.uuid_values(products, "product")
    user_id = str(user["id"])
    holds, own_agents = _check_access(db, user, basis, by, persons, customers, products)

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
    if channels:
        filters["channel"] = list(channels)
    if persons:
        filters["sales_person"] = persons
    if customers:
        filters["customer"] = customers
    if products:
        filters["product"] = products
    if own_agents is not None:
        # An empty list is zero rows (run_ask answers an empty filter with nothing), never "no agent".
        filters["sales_agent"] = list(own_agents)

    run_from, run_to = (date_from, date_to) if date_from else (_OPEN_FROM, _OPEN_TO)
    if open_basis:
        previous_from = previous_to = None
    elif previous_from is None or previous_to is None:
        previous_from, previous_to = ask.compare_window("previous_period", date_from, date_to)

    def run(frm: date, to: date, group_by: Optional[str], **extra: Any) -> dict[str, Any]:
        return ask.run_ask(
            db, group_by=group_by, date_from=frm, date_to=to, filters=filters, basis=basis,
            **{"company_grants": grants, "top_n": None, **_RUN, **extra},
        )

    now = run(run_from, run_to, _DIMENSION.get(by, by), also=("customers", "products"))
    before = None if open_basis else run(previous_from, previous_to, _DIMENSION.get(by, by))

    prev_by_name = {r["name"]: r["amount"] for r in before["rows"]} if before else {}
    no_agent = 0.0
    ranked = []
    for r in now["rows"]:
        if by == "person" and r["name"] == inv.NO_AGENT:
            no_agent = _money(r["amount"])
            continue
        if by == "person" and _money(r["amount"]) == 0:
            continue  # the engine already drops a row with neither qty nor amount; only a person row needs a figure
        ranked.append(r)
    shown = {r["name"]: _BLANK_NAMES.get(by, r["name"]) if r["name"] == engine.BLANK_VALUE else r["name"] for r in ranked}
    ranked.sort(key=lambda r: (-Decimal(str(r["amount"])), shown[r["name"]]))

    codes = {}
    if by == "person":
        codes = _codes_by_person(db, lambda **extra: run(run_from, run_to, "sales_agent", **extra), grants)
    customer_info = _customer_info(db, {k for r in ranked for k in r["keys"]}) if by == "customer" else {}
    product_info = _product_info(db, {r["keys"][0] for r in ranked if r["keys"]}) if by == "product" else {}

    rows = []
    for rank, r in enumerate(ranked, start=1):
        prev = prev_by_name.get(r["name"], 0)
        row: dict[str, Any] = {
            "rank": rank,
            "name": shown[r["name"]],
            "keys": list(r["keys"]) if by != "person" else [],
            "amount": _money(r["amount"]),
            "qty": int(r.get("qty") or 0),
            "prev_amount": None if open_basis else _money(prev),
            "change_pct": None if open_basis else _change(r["amount"], prev),
            "customers": int(r.get("customers") or 0),
            "products": int(r.get("products") or 0),
        }
        if by == "person":
            row.update(person=r["name"], codes=sorted({c for _co, c in codes.get(r["name"], set())} or {r["name"]}), is_me=False, target=None)
        elif by == "customer":
            info = [customer_info[k] for k in r["keys"] if k in customer_info]
            row["code"] = ", ".join(sorted({c for c, _co in info if c}))
            row["companies"] = sorted({co for _c, co in info if co})
        elif by == "product":
            brand, category = product_info.get(r["keys"][0], (None, None)) if r["keys"] else (None, None)
            row.update(brand=brand, category=category)
        elif by == "channel":
            row["key"] = _CHANNEL_KEYS.get(r["name"])  # the "(blank)" row has no key
        rows.append(row)

    me = None
    if by == "person":
        for person, target in _targets(db, grants, {p: {co for co, _c in codes.get(p, set())} for p in (r["person"] for r in rows)}, basis, date_from, date_to).items():
            next(r for r in rows if r["person"] == person)["target"] = target
        mine = _own_persons(db, user_id)
        found = [row for row in rows if row["person"] in mine]
        if found:
            best = min(found, key=lambda row: row["rank"])
            best["is_me"] = True
            me = {"person": best["person"], "rank": best["rank"]}

    total = now["total"]
    return {
        "basis": basis,
        "by": by,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "previous_from": previous_from.isoformat() if previous_from else None,
        "previous_to": previous_to.isoformat() if previous_to else None,
        "as_of": _as_of(db, all_grants),
        "total": {
            "amount": _money(total["amount"]),
            "qty": int(total.get("qty") or 0),
            "prev_amount": None if before is None else _money(before["total"]["amount"]),
            "change_pct": None if before is None else _change(total["amount"], before["total"]["amount"]),
            "customers": int(total.get("customers") or 0),
            "products": int(total.get("products") or 0),
        },
        "no_agent_amount": no_agent,
        "rows": rows,
        "me": me,
        "can_drill_others": holds,
    }
