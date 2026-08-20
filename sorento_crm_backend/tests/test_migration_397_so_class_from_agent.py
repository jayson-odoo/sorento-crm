"""Migration 397 - fill pre-existing `sales_orders.demand_class` NULLs from the agent.

`sales_agent_service.set_demand_class` / `.annotate` now backfill an agent's NULL-class
orders the moment a class is set (PLAN-scm-demo-followups-19aug-b), but that only covers
classifications made going forward. An install where agents were already classified before
that behaviour existed needs the same fill applied once - this migration.

Uses `blank_session` rather than `pg_session`: the migration's SQL names only unqualified
`sales_orders` / `sales_agents`, both public-schema tables the scratch schema's
`search_path` resolves correctly, unlike migration 396's schema-qualified projects join.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.order import SalesOrder
from app.models.sales_agent import SalesAgent
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS, PROJECT
from tests._pg_fixture import blank_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "397_so_class_from_agent.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_397_so_class_from_agent", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_a_null_class_order_is_filled_from_its_classified_agent(db):
    agent = _agent(db, sales_agent=unique_code("SEAN"), demand_class=PROJECT)
    order = _order(db, agent, demand_class=None)
    order_id = order.id

    changed = _module().apply(db.connection())

    assert changed >= 1
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == PROJECT


def test_an_already_classified_order_is_left_alone(db):
    agent = _agent(db, sales_agent=unique_code("JEREMY"), demand_class=PROJECT)
    order = _order(db, agent, demand_class=DEFAULT_DEMAND_CLASS)
    order_id = order.id

    _module().apply(db.connection())

    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == DEFAULT_DEMAND_CLASS


def test_an_order_whose_agent_is_still_unclassified_stays_null(db):
    agent = _agent(db, sales_agent=unique_code("LCL"))  # no demand_class
    order = _order(db, agent, demand_class=None)
    order_id = order.id

    _module().apply(db.connection())

    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class is None


def test_apply_is_idempotent(db):
    agent = _agent(db, sales_agent=unique_code("TERA"), demand_class=PROJECT)
    order = _order(db, agent, demand_class=None)
    order_id = order.id

    first = _module().apply(db.connection())
    assert first >= 1
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == PROJECT

    # A second run must not touch this row again - it no longer matches the
    # `demand_class IS NULL` predicate. Runs against the real shared database (per
    # migration 396's own test), so the global rowcount is not asserted `== 0`.
    _module().apply(db.connection())
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == PROJECT


def test_revert_is_a_no_op(db):
    agent = _agent(db, sales_agent=unique_code("CINDY"), demand_class=PROJECT)
    _order(db, agent, demand_class=None)
    _module().apply(db.connection())

    assert _module().revert(db.connection()) == 0
