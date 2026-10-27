"""Dated agent classes and the sales order class they decide (SALES-UNIFIED round 3, owner
rulings Q6 to Q8 (a); `documentation/plans/sales/PLAN-sales-unified-27oct.md` 2.9).

The only writer of `sales.agent_classes`. An agent's class runs from a month to a month
(`retail` = Dealer, `project` = Project team, `other` = neither); a sales order's class is
re-derived from them:

    the order type AutoCount stated on the order (`sales_orders.order_type`)
    -> else the agent's class in effect on the order's date
    -> else nothing ("Sales order type not set": never the customer's segment, never a guess).

`rederive` is that rule over a set of orders: a dry run reports, per agent per month, the
orders and RM that would change class and from what to what; `apply=True` writes them. Saving
an agent's class rows re-derives that agent's orders over the months the change covers, so an
order's class follows the agent's history instead of being stamped forever. The first bulk
backfill is the owner's call after the dry run (`scripts/sales_order_class_rederive.py`).

`sales_agents.demand_class` mirrors the agent's OPEN row, for the readers that want "now"
(the Sales Agents grid, the weekly upload's ladder).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.sales import SalesAgentClass
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.scm.demand_class import DEMAND_CLASSES, class_of

#: How a class reads on screen.
CLASS_LABELS = {"retail": "Dealer", "project": "Project team", "other": "Other"}


def today_malaysia() -> date:
    from app.services.reports.registry import today_malaysia as _today

    return _today()


def _invalid(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _previous_month(value: date) -> date:
    return month_start(value - timedelta(days=1))


def _month(value: Optional[date]) -> Optional[str]:
    return value.strftime("%Y-%m") if value else None


def serialize(row: SalesAgentClass) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "sales_agent_id": str(row.sales_agent_id),
        "demand_class": row.demand_class,
        "class_label": CLASS_LABELS.get(row.demand_class, row.demand_class),
        "from_month": _month(row.from_month),
        "to_month": _month(row.to_month),
    }


def rows_of(db: Session, agent_id: str) -> List[SalesAgentClass]:
    return (
        db.query(SalesAgentClass)
        .filter(SalesAgentClass.sales_agent_id == agent_id)
        .order_by(SalesAgentClass.from_month.asc().nullsfirst(), SalesAgentClass.id)
        .all()
    )


def class_on(rows: Iterable[SalesAgentClass], day: Optional[date]) -> Optional[str]:
    """The class in effect on `day` among one agent's rows (None when no row covers it)."""
    if day is None:
        return None
    month = month_start(day)
    for row in rows:
        if (row.from_month is None or row.from_month <= month) and (
            row.to_month is None or row.to_month >= month
        ):
            return row.demand_class
    return None


class ClassCache:
    """Every agent's rows, read once per batch: the ingest asks for many orders of few agents.

    An agent with NO dated row at all has the class it has today
    (`sales_agents.demand_class`) for every date: no history is "it has always been so",
    which is what the seed of `sales_unified_0002` writes as a row."""

    def __init__(self, db: Session):
        self.db = db
        self._rows: Dict[str, List[SalesAgentClass]] = {}
        self._current: Dict[str, Optional[str]] = {}

    def class_on(self, agent_id: Optional[str], day: Optional[date]) -> Optional[str]:
        if not agent_id:
            return None
        if agent_id not in self._rows:
            self._rows[agent_id] = rows_of(self.db, agent_id)
            if not self._rows[agent_id]:
                self._current[agent_id] = (
                    self.db.query(SalesAgent.demand_class).filter(SalesAgent.id == agent_id).scalar()
                )
        if not self._rows[agent_id]:
            return self._current.get(agent_id)
        return class_on(self._rows[agent_id], day)


def _check(db: Session, agent_id: str, cls: str, start: Optional[date], end: Optional[date],
           exclude: Optional[str]) -> None:
    if cls not in DEMAND_CLASSES:
        raise _invalid(f"Class is one of {', '.join(DEMAND_CLASSES)}", "invalid_class")
    if start is not None and end is not None and end < start:
        raise _invalid("To month is before from month", "class_months_inverted")
    if db.query(SalesAgent.id).filter(SalesAgent.id == agent_id).first() is None:
        raise AppException(status_code=404, message="Sales agent not found", code="NOT_FOUND")
    overlap = db.query(SalesAgentClass.id).filter(
        SalesAgentClass.sales_agent_id == agent_id,
        *([] if exclude is None else [SalesAgentClass.id != exclude]),
        or_(SalesAgentClass.to_month.is_(None), *([] if start is None else [SalesAgentClass.to_month >= start])),
        or_(SalesAgentClass.from_month.is_(None), *([] if end is None else [SalesAgentClass.from_month <= end])),
    ).first()
    if overlap is not None:
        raise _invalid("This agent already has a class for some of those months", "class_overlap")


def _mirror(db: Session, agent_id: str) -> None:
    """`sales_agents.demand_class` = the open row's class (NULL when no row is open)."""
    open_row = (
        db.query(SalesAgentClass.demand_class)
        .filter(SalesAgentClass.sales_agent_id == agent_id, SalesAgentClass.to_month.is_(None))
        .scalar()
    )
    agent = db.query(SalesAgent).filter(SalesAgent.id == agent_id).first()
    if agent is not None:
        agent.demand_class = open_row


def add(db: Session, agent_id: str, *, demand_class: str, from_month: Optional[date],
        to_month: Optional[date]) -> Dict[str, Any]:
    """A new class from `from_month`. An open row that starts before it is closed the month
    before (the `team_members` move rule), so "Dealer from July" needs one step."""
    open_row = (
        db.query(SalesAgentClass)
        .filter(SalesAgentClass.sales_agent_id == agent_id, SalesAgentClass.to_month.is_(None))
        .first()
    )
    if (
        open_row is not None
        and from_month is not None
        and (open_row.from_month is None or open_row.from_month < from_month)
    ):
        open_row.to_month = _previous_month(from_month)
        db.flush()
    _check(db, agent_id, demand_class, from_month, to_month, None)
    row = SalesAgentClass(
        sales_agent_id=agent_id, demand_class=demand_class, from_month=from_month, to_month=to_month
    )
    db.add(row)
    db.flush()
    _mirror(db, agent_id)
    rederive(db, agent_ids=[agent_id], from_month=from_month, apply=True)
    db.commit()
    return serialize(row)


def update(db: Session, row_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    row = db.query(SalesAgentClass).filter(SalesAgentClass.id == row_id).first()
    if row is None:
        raise AppException(status_code=404, message="Class row not found", code="NOT_FOUND")
    before = row.from_month
    cls = fields.get("demand_class", row.demand_class)
    start = fields["from_month"] if "from_month" in fields else row.from_month
    end = fields["to_month"] if "to_month" in fields else row.to_month
    _check(db, str(row.sales_agent_id), cls, start, end, str(row.id))
    row.demand_class, row.from_month, row.to_month = cls, start, end
    db.flush()
    _mirror(db, str(row.sales_agent_id))
    first = None if before is None or start is None else min(before, start)
    rederive(db, agent_ids=[str(row.sales_agent_id)], from_month=first, apply=True)
    db.commit()
    return serialize(row)


def delete(db: Session, row_id: str) -> None:
    row = db.query(SalesAgentClass).filter(SalesAgentClass.id == row_id).first()
    if row is None:
        raise AppException(status_code=404, message="Class row not found", code="NOT_FOUND")
    agent_id, start = str(row.sales_agent_id), row.from_month
    db.delete(row)
    db.flush()
    _mirror(db, agent_id)
    rederive(db, agent_ids=[agent_id], from_month=start, apply=True)
    db.commit()


def set_current(db: Session, agent_id: str, demand_class: Optional[str], *, today: date) -> None:
    """The Sales Agents screen's (and the importers') "the class is now X": written as dated
    rows so history stays. No row yet: one open row from the beginning (today's meaning of a
    class). An open row of another class: closed last month, the new one open from this month.
    None: the open row closes last month. Re-derives the agent's orders from the change.
    Flushes, never commits (the caller's transaction)."""
    rows = rows_of(db, agent_id)
    this_month = month_start(today)
    open_row = next((r for r in rows if r.to_month is None), None)
    if open_row is not None and open_row.demand_class == demand_class:
        return
    start: Optional[date] = this_month
    if not rows:
        if demand_class is None:
            return
        start = None
        db.add(SalesAgentClass(sales_agent_id=agent_id, demand_class=demand_class))
    else:
        if open_row is not None:
            if open_row.from_month is not None and open_row.from_month >= this_month:
                db.delete(open_row)
            else:
                open_row.to_month = _previous_month(this_month)
            db.flush()
        if demand_class is not None:
            db.add(SalesAgentClass(sales_agent_id=agent_id, demand_class=demand_class, from_month=this_month))
    db.flush()
    _mirror(db, agent_id)
    rederive(db, agent_ids=[agent_id], from_month=start, apply=True)


# ------------------------------------------------------------------------- re-derivation


@dataclass
class Move:
    agent: Optional[str]
    month: str
    before: Optional[str]
    after: Optional[str]
    orders: int
    amount: Decimal


def derived_class(order_type: Optional[str], agent_class: Optional[str]) -> Optional[str]:
    """Q8 (a): the stated order type, else the agent's class on the order's date, else None."""
    return class_of(order_type) or agent_class


def rederive(
    db: Session,
    *,
    agent_ids: Optional[List[str]] = None,
    company_id: Optional[str] = None,
    from_month: Optional[date] = None,
    to_month: Optional[date] = None,
    apply: bool = False,
) -> List[Move]:
    """Every sales order whose stored class differs from the rule's answer, grouped per agent
    per month (orders and RM, from -> to), and written when `apply`. Cancelled orders are
    re-derived too (the class is a fact about the order, not about whether it counts)."""
    q = db.query(
        SalesOrder.id,
        SalesOrder.sales_agent_id,
        SalesOrder.order_date,
        SalesOrder.order_type,
        SalesOrder.demand_class,
    )
    if agent_ids is not None:
        q = q.filter(SalesOrder.sales_agent_id.in_(agent_ids))
    if company_id is not None:
        q = q.filter(SalesOrder.company_id == company_id)
    if from_month is not None:
        q = q.filter(SalesOrder.order_date >= from_month)
    if to_month is not None:
        q = q.filter(SalesOrder.order_date < _next_month(to_month))
    cache = ClassCache(db)
    changes: Dict[str, Tuple[Optional[str], Optional[str], Any, Optional[date]]] = {}
    for so_id, agent_id, order_date, order_type, stored in q.all():
        day = order_date.date() if hasattr(order_date, "date") else order_date
        after = derived_class(order_type, cache.class_on(str(agent_id) if agent_id else None, day))
        if after != stored:
            changes[str(so_id)] = (stored, after, agent_id, day)
    if not changes:
        return []

    amounts = dict(
        db.query(SalesOrderLine.sales_order_id, func.coalesce(func.sum(SalesOrderLine.line_total), 0))
        .filter(SalesOrderLine.sales_order_id.in_(list(changes)))
        .group_by(SalesOrderLine.sales_order_id)
        .all()
    )
    codes = dict(
        db.query(SalesAgent.id, SalesAgent.sales_agent)
        .filter(SalesAgent.id.in_({str(a) for _b, _a2, a, _d in changes.values() if a}))
        .all()
    )
    grouped: Dict[Tuple[Any, ...], List[Any]] = defaultdict(lambda: [0, Decimal(0)])
    for so_id, (before, after, agent_id, day) in changes.items():
        key = (codes.get(str(agent_id)) if agent_id else None, _month(day) or "", before, after)
        grouped[key][0] += 1
        grouped[key][1] += Decimal(str(amounts.get(so_id) or 0))
    if apply:
        by_class: Dict[Optional[str], List[str]] = defaultdict(list)
        for so_id, (_before, after, _agent, _day) in changes.items():
            by_class[after].append(so_id)
        for after, ids in by_class.items():
            db.query(SalesOrder).filter(SalesOrder.id.in_(ids)).update(
                {SalesOrder.demand_class: after}, synchronize_session=False
            )
        db.flush()
    return sorted(
        (Move(agent, month, before, after, n, amount) for (agent, month, before, after), (n, amount) in grouped.items()),
        key=lambda m: (m.agent or "", m.month, m.before or "", m.after or ""),
    )


def _next_month(value: date) -> date:
    return date(value.year + (value.month // 12), value.month % 12 + 1, 1)
