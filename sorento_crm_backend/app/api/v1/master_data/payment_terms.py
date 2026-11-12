"""Payment Terms list (QUOTE-TERMS-SELECT, owner hand test 10 Nov 2026): a read-only view of the
AutoCount terms master the ESB syncs (`payment_terms`). No write route: AutoCount owns the rows.

Scoped by the session's company filter (`PaymentTerm` is a `CompanyScopedMixin` model), so each
user sees the companies they work in; the company code says which book a row came from.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.company import Company
from app.models.payment_term import PaymentTerm
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()

_SORT = {
    "term_code": PaymentTerm.term_code,
    "term_rule": PaymentTerm.term_rule,
    "company_code": Company.code,
    "is_active": PaymentTerm.is_active,
}


# ai: not-for-assistant a read-only admin view of the AutoCount payment terms master; quotations already carry the printed term
@router.get("/")
def list_payment_terms(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    _user: dict = Depends(require_permission_with_api_key("master_data.payment_terms.view")),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(PaymentTerm, Company.code).join(Company, Company.id == PaymentTerm.company_id)
        if query:
            q = q.filter(
                or_(PaymentTerm.term_code.ilike(f"%{query}%"), PaymentTerm.term_rule.ilike(f"%{query}%"))
            )
        column = _SORT.get(sort or "", PaymentTerm.term_code)
        q = q.order_by(column.desc() if dir == "desc" else column.asc(), PaymentTerm.id)
        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        data = [
            {
                "id": str(term.id),
                "term_code": term.term_code,
                "term_rule": term.term_rule,
                "company_code": company_code,
                "is_active": bool(term.is_active),
                "updated_at": term.updated_at or term.created_at,
            }
            for term, company_code in rows
        ]
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
