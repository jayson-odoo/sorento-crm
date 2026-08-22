"""SCM configuration endpoints — small, discoverable quick settings.

At M1 this exposes the single ``dead_stock_days`` knob on the GLOBAL
``scm.reorder_policy`` (scope_type='global', scope_ref NULL). That value drives the
dashboard's "dead" status: on-hand SKUs whose last outbound movement is older than
this window are flagged Dead. Read is gated on the dashboard view slug (so the
setting is visible alongside the numbers it explains); write requires
``scm.config.manage``.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_dashboard import (
    CoverScope,
    CoverScopeUpdate,
    DeadStockDays,
    DeadStockDaysUpdate,
    PlanningMode,
    PlanningModeUpdate,
)
from app.services.error_handler import AppException
from app.services.scm import cash_budget_service, currency_rate_service
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    global_policy_row,
    mode_to_policy_type,
    resolve_global_cover_scope,
    resolve_global_planning_mode,
    upsert_global_policy,
)

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_MANAGE = require_permission_with_api_key("scm.config.manage")

# Engine default fallback (shared with ScmDashboardService._dead_days_for).
_DEFAULT_DEAD_DAYS = DEFAULT_DEAD_STOCK_DAYS


def _global_policy_row(db: Session):
    # Delegates to the one canonical resolver so the dashboard and this endpoint
    # always agree on which global row wins when duplicates exist.
    return global_policy_row(db)


@router.get("/config/dead-stock-days", response_model=DeadStockDays)
def get_dead_stock_days(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    row = _global_policy_row(db)
    value = int(row[1]) if row and row[1] is not None else _DEFAULT_DEAD_DAYS
    return {"dead_stock_days": value}


@router.put("/config/dead-stock-days", response_model=DeadStockDays)
def set_dead_stock_days(
    payload: DeadStockDaysUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    days = payload.dead_stock_days
    if days < 1 or days > 3650:
        raise AppException(
            status_code=422,
            message="Dead-stock threshold must be between 1 and 3650 days.",
        )
    upsert_global_policy(db, dead_stock_days=days)
    db.commit()
    return {"dead_stock_days": days}


# --------------------------------------------------------------------------- #
# planning mode - the ONE universal auto/manual switch (UAC A)
# --------------------------------------------------------------------------- #


@router.get("/config/planning-mode", response_model=PlanningMode)
def get_planning_mode(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return {"mode": resolve_global_planning_mode(db)}


@router.put("/config/planning-mode", response_model=PlanningMode)
def set_planning_mode(
    payload: PlanningModeUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Flip the GLOBAL policy's basis. Touches ONLY ``policy_type`` (AC-A1) - every
    other column (dead_stock_days, safety_days, ...) is left exactly as it was, and
    per-scope override rows (sku/class/abc_xyz_cell) are untouched (AC-A3). Takes
    effect on the NEXT run only; a run already recorded keeps the basis it ran with,
    frozen in its own `inputs.policy_type` (AC-A2)."""
    upsert_global_policy(db, policy_type=mode_to_policy_type(payload.mode))
    db.commit()
    return {"mode": payload.mode}


# --------------------------------------------------------------------------- #
# cover scope - where "use stock" may draw from before buying (AC-3.2)
# --------------------------------------------------------------------------- #


@router.get("/config/cover-scope", response_model=CoverScope)
def get_cover_scope(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Where a plan row may cover a shortage from before it buys.

    Read on the dashboard slug like its sibling settings: the plan screen is where the
    consequence shows up, and the buyer reading "Stock 6 + Buy 182" is entitled to know which
    locations were even eligible to supply that 6.
    """
    return {"cover_scope": resolve_global_cover_scope(db)}


@router.put("/config/cover-scope", response_model=CoverScope)
def set_cover_scope(
    payload: CoverScopeUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Move the GLOBAL policy's `cover_scope`. Touches ONLY that column, exactly as the
    planning-mode flip touches only `policy_type`.

    Takes effect on the NEXT read of the plan, not the next run: the scope filters what the
    screen OFFERS as cover, and never changes a quantity the engine froze."""
    upsert_global_policy(db, cover_scope=payload.cover_scope)
    db.commit()
    return {"cover_scope": payload.cover_scope}


# --------------------------------------------------------------------------- #
# the company's own cash budget
# --------------------------------------------------------------------------- #


class CashBudgetWrite(BaseModel):
    #: Null CLEARS the budget, which puts the plan back to showing itself whole.
    budget_amount: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    note: Optional[str] = None


@router.get("/config/cash-budget")
def get_cash_budget(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """What the company says it can spend, from `scm.purchasing_budget`.

    Read on the dashboard slug because the planning screen shows the figure beside the plan
    it constrains. `configured: false` means nobody has set one, and the plan then shows
    itself whole rather than inventing a limit.
    """
    return cash_budget_service.get_budget(db)


@router.put("/config/cash-budget")
def put_cash_budget(
    body: CashBudgetWrite,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_MANAGE),
):
    """Set or clear the global cash budget. Writing requires `scm.config.manage`."""
    return cash_budget_service.put_budget(
        db,
        budget_amount=body.budget_amount,
        currency=body.currency,
        period_start=body.period_start,
        period_end=body.period_end,
        note=body.note,
        actor=current_user.get("id"),
    )



# ===========================================================================
# exchange rates - what makes two prices comparable
# ===========================================================================

class CurrencyRateWrite(BaseModel):
    #: What one unit of this currency is worth in the base currency. Must be positive:
    #: a zero rate would price every item in that currency at nothing.
    rate_to_base: float = Field(..., gt=0)
    #: When the rate was true. Shown beside every converted figure so a buyer reading a
    #: six-month-old rate can see that is what they are reading.
    as_of: Optional[date] = None
    note: Optional[str] = Field(None, max_length=255)


@router.get("/config/currency-rates")
def get_currency_rates(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The rates on file, plus the currencies the purchase-order book prices in that have
    none.

    Read on the dashboard slug because the plan is where the consequence shows up: a
    supplier priced in a currency with no rate cannot be ranked on cost or funded, and this
    is the list that tells the buyer which rate to add.
    """
    return currency_rate_service.list_rates(db)


@router.put("/config/currency-rates/{currency}")
def put_currency_rate(
    currency: str,
    body: CurrencyRateWrite,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_MANAGE),
):
    """Create or update one currency's rate. Unchanged input is left alone rather than
    rewritten, so `updated_at` keeps meaning "somebody checked this"."""
    return currency_rate_service.upsert_rate(
        db, currency, body.rate_to_base, as_of=body.as_of, note=body.note,
        actor=(current_user or {}).get("id"),
    )


@router.delete("/config/currency-rates/{currency}", status_code=204)
def delete_currency_rate(
    currency: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Remove a rate. Prices in that currency go back to being unrankable, which is the
    honest consequence and shows on the plan as "no rate for X"."""
    currency_rate_service.delete_rate(db, currency)
    return Response(status_code=204)
