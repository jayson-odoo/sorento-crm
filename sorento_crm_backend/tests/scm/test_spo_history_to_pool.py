"""UAC F5 - the shipping orders behind a plan row's SPO cell, pool only.

`GET /api/v1/scm/reorder-runs/{run}/spo-history?product_id=` (plan section 5.2). The SPO
cell is a FACT on the row ("N arriving, already in net", R2), and this is the book behind
it: what is still on the water for the site pool, and what has already landed there.

R15 is the whole reason it is a new read rather than a filter on an existing one: the cell
counts the POOL location alone, never its project bins - a bin's incoming stock is already
spoken for by an Order Inquiry, and counting it here would state the same units twice
against a plan that deliberately excluded them.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import company_scope
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.scm import spo_supply
from tests._pg_fixture import pg_session
from tests.scm._revamp_fixtures import (
    category_and_uom,
    product,
    recommendation,
    run,
    supplier,
    warehouse,
)
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg

pytestmark = requires_pg


@pytest.fixture()
def db():
    with pg_session() as s:
        with company_scope(s, frozenset({SORENTO_COMPANY_ID})):
            yield s


def _spo(db, *, prod, wh, sup, number, qty, received=0, expected=None,
         receipt_status="pending", arrived=None, line_status="open"):
    shipment_id = None
    if arrived is not None:
        shipment = InboundShipment(
            id=str(uuid.uuid4()), shipment_number=f"{number}-SHIP",
            shipment_date=arrived, actual_arrival_date=arrived,
            shipment_status="fully_received",
        )
        db.add(shipment)
        db.flush()
        shipment_id = shipment.id
    row = SPOAllocation(
        id=str(uuid.uuid4()), spo_number=number, spo_line_number=1,
        inbound_shipment_id=shipment_id, warehouse_id=wh.id, product_id=prod.id,
        allocated_quantity=qty, quantity_received=received, receipt_status=receipt_status,
        expected_date=expected, supplier_id=sup.id, line_status=line_status,
    )
    db.add(row)
    db.flush()
    return row


def _world(db):
    """A pool (BRW), its project bin (BRW-BB) and an unrelated site (DC1).

    The run's recommendation sits at the BIN, which is the live shape: a run only writes
    rows for locations carrying demand, and the pool itself often has none.
    """
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "spo history supplier")
    pool = warehouse(db, segment="dealer")
    bin_ = warehouse(db, segment="project", pool_warehouse_id=pool.id)
    elsewhere = warehouse(db, segment="dealer")
    plan = run(db)
    recommendation(db, plan, prod, bin_)
    return plan, prod, sup, pool, bin_, elsewhere


def test_open_first_then_received_and_another_site_is_excluded(db):
    plan, prod, sup, pool, _bin, elsewhere = _world(db)

    _spo(db, prod=prod, wh=pool, sup=sup, number="ZZTRVMP-SPO-OPEN", qty=100,
         expected=date(2026, 9, 30))
    _spo(db, prod=prod, wh=pool, sup=sup, number="ZZTRVMP-SPO-IN", qty=40, received=40,
         receipt_status="fully_received", expected=date(2026, 7, 1),
         arrived=date(2026, 7, 5))
    _spo(db, prod=prod, wh=elsewhere, sup=sup, number="ZZTRVMP-SPO-DC1", qty=999,
         expected=date(2026, 9, 30))

    out = spo_supply.spo_history_for_product(db, str(plan.id), str(prod.id))

    assert [s["spo_number"] for s in out["open"]] == ["ZZTRVMP-SPO-OPEN"]
    assert [s["spo_number"] for s in out["history"]] == ["ZZTRVMP-SPO-IN"]
    numbers = {s["spo_number"] for s in out["open"] + out["history"]}
    assert "ZZTRVMP-SPO-DC1" not in numbers, "a shipment bound elsewhere is not this pool's"


def test_every_field_the_dialog_prints_is_present(db):
    plan, prod, sup, pool, _bin, _elsewhere = _world(db)
    _spo(db, prod=prod, wh=pool, sup=sup, number="ZZTRVMP-SPO-FIELDS", qty=100,
         received=25, receipt_status="partial_received", expected=date(2026, 9, 30))

    row = spo_supply.spo_history_for_product(db, str(plan.id), str(prod.id))["open"][0]

    assert row["spo_number"] == "ZZTRVMP-SPO-FIELDS"
    assert row["supplier_name"] == "spo history supplier"
    assert row["qty"] == 100
    assert row["received_qty"] == 25
    assert row["eta"] == "2026-09-30"
    assert row["arrived_at"] is None
    assert row["status"]


def test_an_arrived_shipment_reads_as_history_with_its_arrival_date(db):
    plan, prod, sup, pool, _bin, _elsewhere = _world(db)
    _spo(db, prod=prod, wh=pool, sup=sup, number="ZZTRVMP-SPO-LANDED", qty=60, received=60,
         receipt_status="fully_received", expected=date(2026, 6, 1),
         arrived=date(2026, 6, 9))

    out = spo_supply.spo_history_for_product(db, str(plan.id), str(prod.id))
    assert out["open"] == []
    assert out["history"][0]["arrived_at"] == "2026-06-09"


def test_a_product_the_run_never_planned_has_no_pool_and_no_rows(db):
    plan, _prod, _sup, _pool, _bin, _elsewhere = _world(db)
    cat, uom = category_and_uom(db)
    stranger = product(db, cat, uom)

    out = spo_supply.spo_history_for_product(db, str(plan.id), str(stranger.id))
    assert out == {"open": [], "history": []}
