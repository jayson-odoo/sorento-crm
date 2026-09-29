"""RQ job for the chatbot stock ask v2 salesman notification (S4, `respond_io` queue).

The body lives in `app.services.stock_ask_service.notify_salesman`; this only owns the
session. The job runs in the ask's own company (`facts["company_id"]`, the company the ask
row was written in), so the customer and agent it reads are that company's. A job enqueued
without one (none are, since S5) falls back to the all-companies scope.
"""
from __future__ import annotations

from typing import Any


def notify_salesman(facts: dict[str, Any]) -> dict[str, Any]:
    from app.database import SessionLocal
    from app.services import stock_ask_service
    from app.services.company_scope import set_company_scope

    db = SessionLocal()
    try:
        company_id = facts.get("company_id")
        set_company_scope(db, frozenset({str(company_id)}) if company_id else None)
        return stock_ask_service.notify_salesman(db, facts)
    finally:
        db.close()
