"""Sales leaderboard API (SALES-LEADERBOARD, plan `documentation/plans/sales/PLAN-sales-leaderboard-07nov.md`).

One permission, `sales.leaderboard.view`, for the board and its filter options. Plain `def` handlers: nothing awaits.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.company import Company
from app.services.error_handler import AppException
from app.services.reports import ask_params as ap
from app.services.sales import leaderboard_service
from app.utils.multi_value import multi_values

router = APIRouter()

VIEW = "sales.leaderboard.view"


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="REPORT_INVALID_PARAMS")


@router.get("/leaderboard")
def get_leaderboard(
    date_from: date = Query(...),
    date_to: date = Query(...),
    company: Optional[str] = Query(None),
    brand: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    previous_from: Optional[date] = Query(None),
    previous_to: Optional[date] = Query(None),
    user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    if date_to < date_from:
        raise _invalid("date_to must not be before date_from")
    if (previous_from is None) != (previous_to is None):
        raise _invalid("previous_from and previous_to go together")
    if previous_from is not None and previous_to < previous_from:
        raise _invalid("previous_to must not be before previous_from")
    return leaderboard_service.build(
        db, str(user["id"]), date_from, date_to, company=company or None,
        brands=multi_values(brand), categories=multi_values(category),
        previous_from=previous_from, previous_to=previous_to,
    )


@router.get("/leaderboard/options")
def get_leaderboard_options(
    user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    from app.models.base import company_scope
    from app.services.company_scope_resolver import resolve_user_grant_ids

    grants = sorted(resolve_user_grant_ids(db, str(user["id"])))
    with company_scope(db, None):
        companies = db.query(Company.id, Company.code).filter(Company.id.in_(grants)).order_by(Company.code).all()
    return {
        "companies": [{"value": str(i), "label": code} for i, code in companies],
        "brands": [{"value": v, "label": label} for v, label in ap.brand_options(db)],
        "categories": [{"value": v, "label": label} for v, label in ap.category_options(db)],
    }
