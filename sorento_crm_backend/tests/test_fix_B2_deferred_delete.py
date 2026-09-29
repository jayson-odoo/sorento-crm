"""Phase 3 fix B2: sales_opportunity.delete is a registered deferred (parked) action,
same shape as sales_team.delete (D7, S6) - Delete asks nothing, parks itself on the
server for the hard-delete window, and the record action runs the same service delete
the immediate DELETE route calls.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.models.base import company_scope

from ._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def test_fix_b2_deferred_delete_is_registered_behind_the_delete_slug():
    import app.services.record_actions  # noqa: F401
    from app.models.sales import SalesOpportunity
    from app.services.form_action_registry import get_action
    from app.services.sales import opportunity_service as svc
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            sales_seed_service.run(db)
            db.flush()

            action = get_action("sales_opportunity.delete")
            assert action is not None
            assert action.permission == "sales.opportunities.delete"
            assert action.entity_types == ("sales_opportunity",)

            opportunity = svc.create_opportunity(
                db,
                company_id=company_id,
                payload={
                    "title": "ZZT Doomed Opp",
                    "expected_amount": Decimal("100.00"),
                    "expected_close_date": date(2026, 11, 1),
                    "prospect_name": "ZZT Doomed Prospect",
                },
                sales_agent_id=None,
                source="crm",
                created_by_user_id=None,
            )
            db.flush()

            action.execute(db, {"entity_id": opportunity.id})
            db.flush()
            assert db.query(SalesOpportunity).filter(SalesOpportunity.id == opportunity.id).count() == 0


def test_fix_b2_deferred_delete_of_an_already_gone_opportunity_is_not_an_error():
    from app.services.form_action_registry import get_action
    import app.services.record_actions  # noqa: F401

    with blank_session() as db:
        action = get_action("sales_opportunity.delete")
        # No row for this id at all - must not raise.
        action.execute(db, {"entity_id": _uid()})
