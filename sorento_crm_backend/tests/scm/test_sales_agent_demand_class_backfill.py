"""`sales_agent_service` backfills its own NULL-class orders when a class is decided.

`outstanding_import_service._classify_demand` reads the agent's `demand_class` LAST, after
order type, the file's own type and the customer's market segment - so an order imported
BEFORE its agent was classified resolved to NULL and stays that way forever, because nothing
re-imports it. `set_demand_class` (the import-time code path) and `annotate` (the PATCH
route's) now fill that gap in the same transaction the class is written in, per
`_backfill_null_class_orders`.

Postgres only, via `blank_session`, `ZZT`-marked rows.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import MarketSegment
from app.models.order import Customer, SalesOrder
from app.models.sales_agent import SalesAgent
from app.services.scm import sales_agent_service as svc
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS, PROJECT
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _agent(db, **kwargs) -> SalesAgent:
    row = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=kwargs.pop("sales_agent", unique_code("AGENT")),
        source=kwargs.pop("source", "manual"),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _order(db, agent: SalesAgent, *, demand_class=None, customer: Customer = None) -> SalesOrder:
    row = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=unique_code("SO"),
        sales_agent_id=agent.id,
        demand_class=demand_class,
        customer_id=customer.id if customer is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, *, segment_stem=None) -> Customer:
    """A customer, with a market segment carrying `segment_stem` as a substring when given.

    `segment_stem` is matched by `demand_class.class_of` the same way `_customer_with_segment`
    in `test_outstanding_import_demand_class.py` does it - a value containing "project" (or
    "retail") classifies as that; `None` leaves the customer with no segment at all.
    """
    code = unique_code("CUST")
    seg = None
    if segment_stem is not None:
        seg = unique_code(segment_stem).lower()
        db.add(MarketSegment(id=str(uuid.uuid4()), code=seg, name=seg, is_active=True))
        db.flush()
    row = Customer(
        id=str(uuid.uuid4()), customer_code=code, customer_name=code,
        market_segment_code=seg, is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_setting_a_class_fills_that_agents_null_class_orders(db):
    agent = _agent(db, sales_agent=unique_code("SEAN"))
    unclassified = _order(db, agent, demand_class=None)
    already_classified = _order(db, agent, demand_class=DEFAULT_DEMAND_CLASS)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)

    db.expire_all()
    assert db.get(SalesOrder, unclassified.id).demand_class == PROJECT
    # A row another rung already answered keeps that answer - never overwritten.
    assert db.get(SalesOrder, already_classified.id).demand_class == DEFAULT_DEMAND_CLASS


def test_annotate_backfills_the_same_way(db):
    agent = _agent(db, sales_agent=unique_code("JEREMY"))
    unclassified = _order(db, agent, demand_class=None)

    svc.annotate(db, agent, demand_class=PROJECT, write_demand_class=True)

    db.expire_all()
    assert db.get(SalesOrder, unclassified.id).demand_class == PROJECT


def test_clearing_the_class_does_not_null_the_orders_back(db):
    agent = _agent(db, sales_agent=unique_code("LCL"))
    order = _order(db, agent, demand_class=None)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)
    db.expire_all()
    assert db.get(SalesOrder, order.id).demand_class == PROJECT

    # Clearing the agent's class is not an undo - the order the earlier save filled
    # keeps its class.
    svc.annotate(db, agent, demand_class=None, write_demand_class=True)
    db.expire_all()
    assert db.get(SalesOrder, order.id).demand_class == PROJECT
    assert db.get(SalesAgent, agent.id).demand_class is None


def test_a_second_agents_orders_are_untouched(db):
    agent = _agent(db, sales_agent=unique_code("TERA"))
    other_agent = _agent(db, sales_agent=unique_code("CINDY"))
    mine = _order(db, agent, demand_class=None)
    theirs = _order(db, other_agent, demand_class=None)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)

    db.expire_all()
    assert db.get(SalesOrder, mine.id).demand_class == PROJECT
    assert db.get(SalesOrder, theirs.id).demand_class is None


def test_backfill_count_is_the_number_of_rows_touched(db):
    agent = _agent(db, sales_agent=unique_code("BB"))
    _order(db, agent, demand_class=None)
    _order(db, agent, demand_class=None)
    _order(db, agent, demand_class=DEFAULT_DEMAND_CLASS)

    changed = svc._backfill_null_class_orders(db, agent, PROJECT)
    assert changed == 2


def test_backfill_of_an_agent_with_no_orders_is_a_silent_zero(db):
    agent = _agent(db, sales_agent=unique_code("NOORDERS"))

    changed = svc._backfill_null_class_orders(db, agent, PROJECT)
    assert changed == 0


def test_a_row_whose_customer_segment_answers_project_wins_over_the_agent(db):
    """The demand-class priority bug: FANNY III (agent retail) rows whose customer's
    segment is a project code must land on `project`, never on the agent's `retail`."""
    agent = _agent(db, sales_agent=unique_code("FANNY"), demand_class=DEFAULT_DEMAND_CLASS)
    customer = _customer(db, segment_stem="project")
    order = _order(db, agent, demand_class=None, customer=customer)

    svc.set_demand_class(db, agent.sales_agent, DEFAULT_DEMAND_CLASS)

    db.expire_all()
    assert db.get(SalesOrder, order.id).demand_class == PROJECT


def test_a_row_whose_customer_segment_answers_retail_still_uses_the_segment(db):
    agent = _agent(db, sales_agent=unique_code("SEGRETAIL"), demand_class=PROJECT)
    customer = _customer(db, segment_stem="retail")
    order = _order(db, agent, demand_class=None, customer=customer)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)

    db.expire_all()
    # The segment says retail even though the agent is a project agent - segment outranks
    # the agent, so the order must not inherit the agent's class here.
    assert db.get(SalesOrder, order.id).demand_class == DEFAULT_DEMAND_CLASS


def test_a_customer_with_no_segment_still_falls_back_to_the_agent(db):
    agent = _agent(db, sales_agent=unique_code("NOSEG"))
    customer = _customer(db, segment_stem=None)
    order = _order(db, agent, demand_class=None, customer=customer)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)

    db.expire_all()
    assert db.get(SalesOrder, order.id).demand_class == PROJECT


def test_an_order_with_no_customer_at_all_falls_back_to_the_agent(db):
    agent = _agent(db, sales_agent=unique_code("NOCUST"))
    order = _order(db, agent, demand_class=None, customer=None)

    svc.set_demand_class(db, agent.sales_agent, PROJECT)

    db.expire_all()
    assert db.get(SalesOrder, order.id).demand_class == PROJECT


def test_backfill_count_covers_both_segment_and_agent_derived_rows(db):
    agent = _agent(db, sales_agent=unique_code("MIXED"), demand_class=DEFAULT_DEMAND_CLASS)
    project_customer = _customer(db, segment_stem="project")
    from_segment = _order(db, agent, demand_class=None, customer=project_customer)
    from_agent = _order(db, agent, demand_class=None, customer=None)

    changed = svc._backfill_null_class_orders(db, agent, DEFAULT_DEMAND_CLASS)

    assert changed == 2
    db.expire_all()
    assert db.get(SalesOrder, from_segment.id).demand_class == PROJECT
    assert db.get(SalesOrder, from_agent.id).demand_class == DEFAULT_DEMAND_CLASS
