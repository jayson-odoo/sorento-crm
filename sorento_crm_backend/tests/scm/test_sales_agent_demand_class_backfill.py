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

from app.models.order import SalesOrder
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


def _order(db, agent: SalesAgent, *, demand_class=None) -> SalesOrder:
    row = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=unique_code("SO"),
        sales_agent_id=agent.id,
        demand_class=demand_class,
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
