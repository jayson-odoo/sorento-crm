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
    basis: str = Query("invoiced"),
    by: str = Query("person"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    company: Optional[list[str]] = Query(None),
    brand: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    channel: Optional[list[str]] = Query(None),
    person: Optional[list[str]] = Query(None),
    customer: Optional[list[str]] = Query(None),
    product: Optional[list[str]] = Query(None),
    previous_from: Optional[date] = Query(None),
    previous_to: Optional[date] = Query(None),
    sort: str = Query("rank"),
    dir: str = Query("asc"),
    user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    if date_from is not None and date_to is not None and date_to < date_from:
        raise _invalid("date_to must not be before date_from")
    if (previous_from is None) != (previous_to is None):
        raise _invalid("previous_from and previous_to go together")
    if previous_from is not None and previous_to < previous_from:
        raise _invalid("previous_to must not be before previous_from")
    return leaderboard_service.build(
        db, user, date_from, date_to, basis=basis, by=by, companies=multi_values(company),
        brands=multi_values(brand), categories=multi_values(category), channels=multi_values(channel),
        persons=[p for p in person or [] if p], customers=multi_values(customer), products=multi_values(product),
        previous_from=previous_from, previous_to=previous_to, sort=sort, direction=dir,
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
        "channels": leaderboard_service.channel_options(),
        "can": leaderboard_service.can_by_basis(db, user),
    }
