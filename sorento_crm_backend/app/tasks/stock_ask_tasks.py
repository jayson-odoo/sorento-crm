"""RQ job for the chatbot stock ask v2 salesman notification (S4, `respond_io` queue).

The body lives in `app.services.stock_ask_service.notify_salesman`; this only owns the
session. The job reads owned tables (customers, sales agents) for one specific ask, so it
runs with the all-companies scope, the same as the other worker jobs that act on named rows.
"""
from __future__ import annotations

from typing import Any


def notify_salesman(facts: dict[str, Any]) -> dict[str, Any]:
    from app.database import SessionLocal
    from app.services import stock_ask_service
    from app.services.company_scope import set_company_scope

    db = SessionLocal()
    try:
        set_company_scope(db, None)
        return stock_ask_service.notify_salesman(db, facts)
    finally:
        db.close()
