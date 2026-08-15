"""The warehouse API must expose the two fields that drive the reorder plan.

`pool_warehouse_id` decides whether a bin's shortage is covered from its site's shared pool
or bought (ADR-0011), and `counts_as_available` decides whether a location's stock counts at
all. Both were added by migration 311 and, until now, could only be changed by an engineer
with a database session - configuration nobody can see is configuration nobody can trust.

The manual-dict trap is the specific risk here: several serializers in this codebase build
their response by hand and silently drop any field not listed, so a new column reaches the
database and never reaches the screen. These tests fail if that happens.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.schemas.inventory import WarehouseUpdate
from app.services.inventory_service import WarehouseService
from tests._pg_fixture import pg_session


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def pool_and_bin(db):
    pool = Warehouse(id=_u(), warehouse_code=f"ZZP-{uuid.uuid4().hex[:6]}",
                     warehouse_name="site pool", is_active=True)
    db.add(pool)
    db.flush()
    bin_ = Warehouse(id=_u(), warehouse_code=f"ZZB-{uuid.uuid4().hex[:6]}",
                     warehouse_name="customer bin", is_active=True,
                     pool_warehouse_id=pool.id)
    db.add(bin_)
    db.flush()
    return pool, bin_


def test_a_new_location_defaults_to_available_and_no_pool(db):
    """The safe default: a location counts, and stands alone until told otherwise."""
    w = Warehouse(id=_u(), warehouse_code=f"ZZN-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(w)
    db.flush()
    db.refresh(w)

    assert w.counts_as_available is True
    assert w.pool_warehouse_id is None


def test_get_warehouse_resolves_the_pool_to_a_readable_code(db, pool_and_bin):
    """No UUID may reach the UI, and a pool is picked by name."""
    pool, bin_ = pool_and_bin

    got = WarehouseService(db).get_warehouse(bin_.id)

    assert got.pool_warehouse_id == pool.id
    assert got.pool_warehouse_code == pool.warehouse_code


def test_a_location_without_a_pool_reports_no_pool_code(db):
    w = Warehouse(id=_u(), warehouse_code=f"ZZS-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(w)
    db.flush()

    got = WarehouseService(db).get_warehouse(w.id)
    assert got.pool_warehouse_code is None


def test_the_listing_carries_both_planning_fields(db, pool_and_bin):
    """The manual-dict trap: a new column that reaches the DB but never the screen."""
    pool, bin_ = pool_and_bin

    page = WarehouseService(db).list_warehouses(page=1, limit=200,
                                                query=bin_.warehouse_code)
    row = next(w for w in page["data"] if w.id == bin_.id)

    assert row.counts_as_available is True
    assert row.pool_warehouse_code == pool.warehouse_code


def test_both_fields_can_be_saved_through_the_update_path(db, pool_and_bin):
    pool, bin_ = pool_and_bin

    updated = WarehouseService(db).update_warehouse(
        bin_.id, WarehouseUpdate(counts_as_available=False, pool_warehouse_id=None)
    )

    assert updated.counts_as_available is False
    assert updated.pool_warehouse_id is None
    persisted = db.execute(text(
        "SELECT counts_as_available, pool_warehouse_id FROM warehouses WHERE id = :i"
    ), {"i": bin_.id}).fetchone()
    assert persisted[0] is False and persisted[1] is None


def test_an_unrelated_update_does_not_clear_the_pool(db, pool_and_bin):
    """`exclude_unset` matters: renaming a warehouse must not silently un-pool it and
    change what the plan buys."""
    pool, bin_ = pool_and_bin

    updated = WarehouseService(db).update_warehouse(
        bin_.id, WarehouseUpdate(warehouse_name="renamed")
    )

    assert updated.warehouse_name == "renamed"
    assert updated.pool_warehouse_id == pool.id
    assert updated.counts_as_available is True
