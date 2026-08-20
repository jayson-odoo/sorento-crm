"""Migration 401 - re-rank `sales_orders.demand_class` where the agent outranked the segment.

`_backfill_null_class_orders` (and the earlier `397_so_class_from_agent` one-off) filled a
NULL-class order straight from its agent without checking the customer's market segment
first, even though the import ladder reads the segment BEFORE the agent. This migration
corrects the rows that landed wrong - see the migration module's own docstring.

Uses `blank_session` rather than `pg_session`: the migration's SQL names only unqualified
`sales_orders` / `customers`, both public-schema tables the scratch schema's `search_path`
resolves correctly (same reasoning as migration 397's own test).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.access import MarketSegment
from app.models.order import Customer, SalesOrder
from app.models.sales_agent import SalesAgent
from tests._pg_fixture import blank_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "401_so_class_segment_rank.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_401_so_class_segment_rank", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _agent(db, *, demand_class=None) -> SalesAgent:
    row = SalesAgent(
        id=str(uuid.uuid4()), sales_agent=unique_code("AGENT"), source="manual",
        demand_class=demand_class,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, *, segment_stem=None) -> Customer:
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


def _order(db, *, agent: SalesAgent = None, customer: Customer = None,
           order_type=None, demand_class=None) -> SalesOrder:
    row = SalesOrder(
        id=str(uuid.uuid4()), so_number=unique_code("SO"),
        sales_agent_id=agent.id if agent is not None else None,
        customer_id=customer.id if customer is not None else None,
        order_type=order_type, demand_class=demand_class,
    )
    db.add(row)
    db.flush()
    return row


def test_a_project_segment_order_wrongly_classed_retail_by_the_agent_is_corrected(db):
    agent = _agent(db, demand_class="retail")
    customer = _customer(db, segment_stem="project")
    order = _order(db, agent=agent, customer=customer, order_type=None, demand_class="retail")
    order_id = order.id

    changed = _module().apply(db.connection())

    assert changed >= 1
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "project"


def test_a_retail_segment_order_wrongly_classed_project_is_corrected_too(db):
    agent = _agent(db, demand_class="project")
    customer = _customer(db, segment_stem="retail")
    order = _order(db, agent=agent, customer=customer, order_type=None, demand_class="project")
    order_id = order.id

    _module().apply(db.connection())

    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "retail"


def test_an_order_stating_an_order_type_is_left_alone(db):
    """Order type is the ladder's FIRST rung - a row that states one has already been
    answered ahead of the segment and must not be touched by this migration."""
    agent = _agent(db, demand_class="retail")
    customer = _customer(db, segment_stem="project")
    order = _order(
        db, agent=agent, customer=customer, order_type="spike", demand_class="retail",
    )
    order_id = order.id

    _module().apply(db.connection())

    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "retail"


def test_an_order_whose_customer_has_no_segment_is_left_alone(db):
    agent = _agent(db, demand_class="retail")
    customer = _customer(db, segment_stem=None)
    order = _order(db, agent=agent, customer=customer, order_type=None, demand_class="retail")
    order_id = order.id

    _module().apply(db.connection())

    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "retail"


def test_an_already_correctly_classed_row_is_left_alone(db):
    customer = _customer(db, segment_stem="project")
    order = _order(db, customer=customer, order_type=None, demand_class="project")
    order_id = order.id

    changed = _module().apply(db.connection())

    assert changed == 0
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "project"


def test_apply_is_idempotent(db):
    customer = _customer(db, segment_stem="project")
    order = _order(db, customer=customer, order_type=None, demand_class="retail")
    order_id = order.id

    first = _module().apply(db.connection())
    assert first >= 1
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "project"

    # A second run must not touch this row again - it no longer disagrees with the
    # segment's class. Runs against the real shared database (per migration 397's own
    # test), so the global rowcount is not asserted `== 0`.
    _module().apply(db.connection())
    db.expire_all()
    assert db.get(SalesOrder, order_id).demand_class == "project"


def test_revert_is_a_no_op(db):
    customer = _customer(db, segment_stem="project")
    _order(db, customer=customer, order_type=None, demand_class="retail")
    _module().apply(db.connection())

    assert _module().revert(db.connection()) == 0
