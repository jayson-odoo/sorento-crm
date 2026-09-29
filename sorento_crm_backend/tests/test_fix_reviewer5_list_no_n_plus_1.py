"""Phase 3 reviewer should-fix 5: the opportunities list serializes a page without an N+1.

`serialize()` (one row's worth: a detail read, a create/update response) issues a lookup per
row for customer/agent/status/order/lost-reason/created-by, plus a query for the status graph's
`available_transitions` and another for `lines` with a Product join - fine once, an N+1 the
moment it runs per row on a list page. `serialize_list()` batch-loads all of that for the whole
page and carries neither `available_transitions` nor `lines` (a list row has no use for either).

Query count pinned with a `before_cursor_execute` listener (LESSONS 93), never a wall-clock
assertion - the same shape `test_conversations_inbox_list.py` uses.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import event, text

from app.models.base import company_scope

from ._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


class _QueryCounter:
    def __init__(self, bind):
        self.bind = bind
        self.statements: list[str] = []

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self.bind, "before_cursor_execute", self._on)
        return False

    def _on(self, conn, cursor, statement, parameters, context, executemany):
        head = statement.strip().split(None, 1)[0].upper()
        if head in ("SELECT", "WITH"):
            self.statements.append(statement)


def _agent(db, *, code: str):
    from app.models.sales_agent import SalesAgent

    agent = SalesAgent(id=_uid(), sales_agent=code, description="ZZT R5 Agent", is_active=True)
    db.add(agent)
    db.flush()
    return agent


def _customer(db, company_id, *, name: str, agent_id=None):
    from app.models.order import Customer

    customer = Customer(
        id=_uid(), company_id=company_id, customer_code=f"ZZT-{_uid()[:6]}",
        customer_name=name, sales_agent_id=agent_id,
    )
    db.add(customer)
    db.flush()
    return customer


def test_fix_reviewer5_a_ten_row_page_serializes_in_a_bounded_number_of_queries():
    from app.services.sales import opportunity_service as svc
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            sales_seed_service.run(db)
            db.flush()

            opportunities = []
            for i in range(10):
                agent = _agent(db, code=f"ZZO-R5-{i}")
                customer = _customer(db, company_id, name=f"ZZT R5 Customer {i}", agent_id=agent.id)
                opportunities.append(
                    svc.create_opportunity(
                        db,
                        company_id=company_id,
                        payload={
                            "title": f"ZZT R5 Opp {i}",
                            "expected_amount": Decimal("100.00"),
                            "expected_close_date": date(2026, 11, 1),
                            "customer_id": customer.id,
                        },
                        sales_agent_id=agent.id,
                        source="crm",
                        created_by_user_id=None,
                    )
                )
            db.flush()

            bind = db.get_bind()
            with _QueryCounter(bind) as counter:
                rows = svc.serialize_list(db, opportunities)

            assert len(rows) == 10
            for row in rows:
                assert row["lines"] == []
                assert row["available_transitions"] == []

            # A handful of batch queries regardless of page size - NOT one bundle per row.
            # Without the fix this was 60+ for 10 rows (customer + agent + status + order +
            # lost-reason + created-by + transitions + lines, each once per row).
            assert len(counter.statements) <= 10, (
                f"{len(counter.statements)} SELECT/WITH statements for a 10-row page:\n"
                + "\n---\n".join(counter.statements)
            )
