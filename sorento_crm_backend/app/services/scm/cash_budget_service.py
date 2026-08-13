"""The company's OWN cash budget for buying, read from `scm.purchasing_budget`.

This table has existed since M0 and nothing read it. The planning screen instead seeded its
budget at roughly 60% of what the plan itself happened to cost, which invents a constraint
the company never stated: a plan costing RM 5.9m opened with RM 3.55m "available" and 59
lines sitting under a heading that said Over budget, for no business reason at all. The
buyer's reasonable reaction is "why is everything over budget, I have five million" - and
there was no answer, because the figure was never theirs.

So: a configured budget wins. When none is configured the plan shows itself WHOLE and says
so, rather than pretending to a limit. A limit nobody set is not a safer default; it is a
wrong number that looks authoritative.

Scope is `global` here. Per-supplier and per-category windows are already modelled on the
table and are a later slice; resolving them silently now would mean a screen that shows one
budget while three others exist.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.scm import PurchasingBudget

SCOPE_GLOBAL = "global"


def _today() -> date:
    from datetime import datetime

    from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


def _serialize(row: Optional[PurchasingBudget]) -> dict[str, Any]:
    if row is None:
        return {
            "configured": False,
            "budget_amount": None,
            "currency": None,
            "period_start": None,
            "period_end": None,
            "note": None,
            "set_by": None,
        }
    return {
        "configured": row.budget_amount is not None,
        "budget_amount": float(row.budget_amount) if row.budget_amount is not None else None,
        "currency": row.currency,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "note": row.note,
        "set_by": row.set_by,
    }


def current_row(db: Session, *, on: Optional[date] = None) -> Optional[PurchasingBudget]:
    """The global budget in force on a date, else the most recent global one.

    Falling back to the most recent rather than to nothing, because a budget whose month has
    just ended is still the best statement of what the company spends - and a screen that
    forgets the budget on the first of the month is a screen people stop trusting. The period
    travels with the figure so the user can see which window they are looking at.
    """
    day = on or _today()
    q = db.query(PurchasingBudget).filter(PurchasingBudget.scope_type == SCOPE_GLOBAL)
    in_force = (
        q.filter(
            or_(PurchasingBudget.period_start.is_(None), PurchasingBudget.period_start <= day),
            or_(PurchasingBudget.period_end.is_(None), PurchasingBudget.period_end >= day),
        )
        .order_by(PurchasingBudget.period_start.desc().nullslast())
        .first()
    )
    if in_force is not None:
        return in_force
    return q.order_by(PurchasingBudget.period_start.desc().nullslast()).first()


def get_budget(db: Session, *, on: Optional[date] = None) -> dict[str, Any]:
    return _serialize(current_row(db, on=on))


def put_budget(
    db: Session,
    *,
    budget_amount: Optional[float],
    currency: Optional[str] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    note: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Set (or clear) the global cash budget. Commits.

    A null amount CLEARS it, which is a real choice: it puts the plan back to showing itself
    whole instead of against a stale limit.
    """
    row = current_row(db)
    if row is None:
        row = PurchasingBudget(id=str(uuid.uuid4()), scope_type=SCOPE_GLOBAL, source_system="manual")
        db.add(row)
    row.budget_amount = budget_amount
    row.currency = currency or row.currency or "MYR"
    if period_start is not None:
        row.period_start = period_start
    if period_end is not None:
        row.period_end = period_end
    if note is not None:
        row.note = note
    row.set_by = actor or row.set_by
    db.commit()
    db.refresh(row)
    return _serialize(row)
