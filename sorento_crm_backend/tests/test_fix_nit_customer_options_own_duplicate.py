"""Phase 3 nit: customer_options blocks a name only when NO customer of the agent's OWN
names it.

Two customers can share a normalized name (a real prod case elsewhere in this app - see
opportunity_service.py's own SearchableSelect identity comment). `customer_options` used to pick
the exact match with an unordered `.first()`, which could hand back a DIFFERENT agent's row even
when the requesting agent has an exact match of their own, wrongly blocking them from a name
they already own.
"""
from __future__ import annotations

import uuid

from app.models.base import company_scope

from ._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    from sqlalchemy import text

    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _customer(db, company_id, *, name: str, agent_id=None):
    from app.models.order import Customer

    customer = Customer(
        id=_uid(), company_id=company_id, customer_code=f"ZZT-{_uid()[:6]}",
        customer_name=name, sales_agent_id=agent_id,
    )
    db.add(customer)
    db.flush()
    return customer


def _agent(db, *, code: str):
    from app.models.sales_agent import SalesAgent

    agent = SalesAgent(id=_uid(), sales_agent=code, description="ZZT Nit Agent", is_active=True)
    db.add(agent)
    db.flush()
    return agent.id


def test_fix_nit_own_duplicate_name_is_not_blocked():
    from app.services.sales import opportunity_service as svc

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            agent_a = _agent(db, code="ZZO-NIT-A")
            agent_b = _agent(db, code="ZZO-NIT-B")
            name = "ZZT Shared Name Co"
            # Same normalized name, two different owning agents.
            _customer(db, company_id, name=name, agent_id=agent_b)
            _customer(db, company_id, name=name, agent_id=agent_a)

            result = svc.customer_options(db, q=name, sales_agent_id=agent_a)
            assert result["blocked"] is None, result
            assert len(result["items"]) == 1
            assert result["items"][0]["customer_name"] == name


def test_fix_nit_someone_elses_duplicate_name_is_still_blocked():
    from app.services.sales import opportunity_service as svc

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            agent_a = _agent(db, code="ZZO-NIT-C")
            agent_b = _agent(db, code="ZZO-NIT-D")
            name = "ZZT Not Yours Co"
            _customer(db, company_id, name=name, agent_id=agent_b)

            result = svc.customer_options(db, q=name, sales_agent_id=agent_a)
            assert result["blocked"] is not None, result
            assert result["blocked"]["name"] == name
