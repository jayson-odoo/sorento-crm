"""UAC F6 / F7 - the purchase records behind the PO cell, narrowed to the site pool.

R15: "PO cell and PO dialog count the BRW pool location only (not BRW-BB / BRW-AM), like
On hand and SPO. History lines with no destination or a project destination are left out."

Two readers have to agree about that, or the panel's Last price and the dialog's newest
history row - which the buyer reads side by side (F7) - state two different purchases:

* `purchase_trend_service.purchase_trend_for_run(warehouse=...)`, the History tab;
* `reorder_run_service._last_purchase_cost_map`, which freezes `inputs.last_purchase` at
  run time and is what the panel actually prints.

(`price_history_service.price_history_for_run` is deliberately NOT one of them: it is read
once per RUN and every row has its own pool, so it has no honest destination to narrow to.)

The second of those keeps its fallbacks: on the customer's book 12,928 of 12,940 imported PO
lines name no destination at all, so a pool-only rule with nothing behind it would blank
the price on nearly every row. The pool purchase WINS where one exists, and
`last_purchase_basis` says which basis was used - never silently relabelled.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.scm import purchase_trend_service
from app.services.scm import reorder_run_service as run_svc
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


def _po(db, *, sup, prod, wh, number, qty=10, cost=25.0, issued=None, expected=None,
        status="active"):
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=number, supplier_id=sup.id, status=status,
        issue_date=issued or date(2026, 5, 1),
        expected_date=expected, currency="MYR", created_at=datetime.utcnow(),
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=prod.id,
        warehouse_id=(wh.id if wh is not None else None),
        qty_ordered=qty, qty_received=0, unit_cost=cost, currency="MYR",
        line_status="open",
    )
    db.add(line)
    db.flush()
    return po


def _world(db):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "pool purchase supplier")
    pool = warehouse(db, segment="dealer")
    bin_ = warehouse(db, segment="project", pool_warehouse_id=pool.id)
    plan = run(db)
    recommendation(db, plan, prod, bin_, sup=sup)
    return plan, prod, sup, pool, bin_


# ===========================================================================
# purchase-trend, the History tab (F6)
# ===========================================================================

def test_purchase_trend_narrowed_to_the_pool_drops_the_bin_and_the_undirected_line(db):
    plan, prod, sup, pool, bin_ = _world(db)
    _po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-PO-POOL", issued=date(2026, 5, 20))
    _po(db, sup=sup, prod=prod, wh=bin_, number="ZZTRVMP-PO-BIN", issued=date(2026, 5, 21))
    _po(db, sup=sup, prod=prod, wh=None, number="ZZTRVMP-PO-NOWHERE",
        issued=date(2026, 5, 22))

    out = purchase_trend_service.purchase_trend_for_run(
        db, str(plan.id), warehouse_id=str(pool.id))
    numbers = [ln["po_number"] for ln in out["products"][str(prod.id)]["lines"]]

    assert numbers == ["ZZTRVMP-PO-POOL"]


def test_purchase_trend_unfiltered_is_unchanged(db):
    """The existing whole-product read is byte-identical when no warehouse is named."""
    plan, prod, sup, pool, bin_ = _world(db)
    _po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-PO-POOL2", issued=date(2026, 5, 20))
    _po(db, sup=sup, prod=prod, wh=None, number="ZZTRVMP-PO-NOWHERE2",
        issued=date(2026, 5, 22))

    out = purchase_trend_service.purchase_trend_for_run(db, str(plan.id))
    numbers = {ln["po_number"] for ln in out["products"][str(prod.id)]["lines"]}

    assert numbers == {"ZZTRVMP-PO-POOL2", "ZZTRVMP-PO-NOWHERE2"}


def test_purchase_trend_lines_carry_the_eta_and_status_the_dialog_prints(db):
    plan, prod, sup, pool, _bin = _world(db)
    _po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-PO-COLS", qty=12, cost=31.5,
        issued=date(2026, 5, 20), expected=date(2026, 6, 30))

    line = purchase_trend_service.purchase_trend_for_run(
        db, str(plan.id), warehouse_id=str(pool.id))["products"][str(prod.id)]["lines"][0]

    assert line["po_number"] == "ZZTRVMP-PO-COLS"
    assert line["supplier_name"] == "pool purchase supplier"
    assert line["qty"] == 12
    assert line["unit_cost"] == 31.5
    assert line["order_date"] == "2026-05-20"
    assert line["expected_date"] == "2026-06-30"
    assert line["status"] == "active"


# ===========================================================================
# the frozen last purchase on the row (F7) + the supplier it names
# ===========================================================================

def test_last_purchase_prefers_the_pool_and_names_the_supplier(db):
    _plan, prod, sup, pool, bin_ = _world(db)
    _po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-LP-POOL", cost=20.0,
        issued=date(2026, 5, 20))
    _po(db, sup=sup, prod=prod, wh=bin_, number="ZZTRVMP-LP-BIN", cost=99.0,
        issued=date(2026, 5, 28))

    costs = run_svc._last_purchase_cost_map(db, [str(prod.id)])
    entry, basis = run_svc._last_purchase_for(costs, str(prod.id), "dealer",
                                              pool_warehouse_id=str(pool.id))

    assert entry["ref"] == "ZZTRVMP-LP-POOL"
    assert basis == "pool"
    # The panel says WHO we last paid, beside what we paid (revamp plan 4.4 zone 2).
    assert entry["supplier_id"] == sup.id
    assert entry["supplier_name"] == "pool purchase supplier"


def test_last_purchase_falls_back_when_the_pool_has_never_been_bought_for(db):
    """12,928 of 12,940 imported lines name no destination, so the fallback is the
    ordinary case - and `last_purchase_basis` says so rather than relabelling it."""
    _plan, prod, sup, pool, _bin = _world(db)
    _po(db, sup=sup, prod=prod, wh=None, number="ZZTRVMP-LP-NOWHERE", cost=17.0,
        issued=date(2026, 5, 20))

    costs = run_svc._last_purchase_cost_map(db, [str(prod.id)])
    entry, basis = run_svc._last_purchase_for(costs, str(prod.id), "dealer",
                                              pool_warehouse_id=str(pool.id))

    assert entry["ref"] == "ZZTRVMP-LP-NOWHERE"
    assert basis == "unattributed"
    assert entry["supplier_name"] == "pool purchase supplier"


def test_a_frozen_row_carries_the_last_supplier(db):
    """`response_model` drops what a schema does not declare, so the field is asserted
    where the FE reads it: on the recommendation's own frozen `inputs`."""
    _plan, prod, sup, pool, _bin = _world(db)
    _po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-LP-FROZEN", cost=44.0,
        issued=date(2026, 5, 20))

    costs = run_svc._last_purchase_cost_map(db, [str(prod.id)])
    entry, _basis = run_svc._last_purchase_for(costs, str(prod.id), None,
                                               pool_warehouse_id=str(pool.id))
    assert set(entry) >= {"cost", "currency", "ref", "at", "supplier_id", "supplier_name"}


def test_two_purchases_on_the_same_day_pick_the_one_recorded_last(db):
    """`po.issue_date` is a DATE, so a same-day pair ties on it and the bucket kept
    whichever row the scan reached first. The line's own `created_at` breaks the tie."""
    _plan, prod, sup, _pool, _bin = _world(db)
    # The ids are pinned, because the query's own ordering falls through to the
    # DESTINATION - so with the tie unbroken the winner is whichever warehouse id sorts
    # first, and a random pair would make this test pass half the time on the old
    # behaviour. `low` is scanned first and holds the EARLIER line.
    tail = uuid.uuid4().hex[:12]
    low = warehouse(db, segment="dealer", id=f"00000000-0000-4000-8000-{tail}")
    high = warehouse(db, segment="dealer", id=f"ffffffff-ffff-4fff-bfff-{tail}")
    same_day = date(2026, 5, 20)
    first = _po(db, sup=sup, prod=prod, wh=low, number="ZZTRVMP-LP-EARLIER", cost=11.0,
                issued=same_day)
    second = _po(db, sup=sup, prod=prod, wh=high, number="ZZTRVMP-LP-LATER",
                 cost=22.0, issued=same_day)
    # Two lines written seconds apart, the shape one upload of one day's purchases makes.
    _set_line_created_at(db, first, datetime(2026, 5, 20, 9, 0, 0))
    _set_line_created_at(db, second, datetime(2026, 5, 20, 9, 0, 5))

    costs = run_svc._last_purchase_cost_map(db, [str(prod.id)])
    entry, basis = run_svc._last_purchase_for(costs, str(prod.id), "dealer")

    assert basis == "own_segment"
    assert entry["ref"] == "ZZTRVMP-LP-LATER"


def _set_line_created_at(db, po, when):
    db.execute(text(
        "UPDATE purchase_order_lines SET created_at = :w WHERE purchase_order_id = :p"
    ), {"w": when, "p": po.id})
    db.flush()
