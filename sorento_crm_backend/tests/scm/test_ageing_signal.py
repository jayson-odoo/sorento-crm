"""L5 - stock still held against a purchase years old is evidence of a slow mover.

> "if I order from 5 years ago and now still got stock meaning this is not very hot selling"

That is the requirement, and the reason it is worth having at all is that it is a fact about
THIS stock rather than a statistic about demand. Demand variance says what a class of items
tends to do; a pallet bought in 2020 that has never moved says what this pallet did.

The rule is deliberately narrow, and the tests below are mostly about the LIMITS rather than
the case it fires on:

* it only ever speaks where the movement rule abstained (never moved), because a SKU that
  moved last week is not dead however old its last purchase is;
* it never overrides a movement it can see;
* and the reason quotes the age, because "dead stock" with no figure is an assertion and
  "bought 1,876 days ago and has never moved" is something a buyer can check.

The engine half is pure and covers the truth table. The service half proves the wiring on
real tables: that the date is found through the imported HISTORY (which names no warehouse,
so a per-warehouse lookup would silently read "never bought"), and that it is company-scoped.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import reorder_engine as eng
from app.services.scm.reorder_run_service import _last_purchase_map
from tests._pg_fixture import pg_session

MARKER = "ZZTAGE"
SORENTO = "00000000-0000-0000-0000-000000000001"

WINDOW = 180.0  # dead_stock_days for these tests


def _u() -> str:
    return str(uuid.uuid4())


def _disp(**over):
    kwargs = dict(
        on_hand=10.0,
        last_movement_days=None,
        dead_stock_days=WINDOW,
        days_of_cover_val=None,
        overstock_days=365.0,
        last_purchase_days=None,
    )
    kwargs.update(over)
    return eng.disposition(**kwargs)


# --------------------------------------------------------------------------- #
# the case it exists for
# --------------------------------------------------------------------------- #

def test_stock_that_never_moved_and_was_bought_long_ago_is_dead():
    """The user's sentence, as a rule."""
    out = _disp(last_movement_days=None, last_purchase_days=1876.0)

    assert out is not None
    assert out["type"] == "dead"
    assert out["basis"] == "ageing", "the two kinds of dead are different evidence"


def test_stock_that_never_moved_and_was_bought_recently_is_not_dead():
    """A delivery that landed last month has not had a chance to sell."""
    assert _disp(last_movement_days=None, last_purchase_days=30.0) is None


def test_a_purchase_exactly_on_the_window_is_not_dead():
    """Strictly greater, matching the movement rule it sits beside. A boundary that
    disagreed with its twin would be a coin toss for anything landing on the day."""
    assert _disp(last_movement_days=None, last_purchase_days=WINDOW) is None
    assert _disp(last_movement_days=None, last_purchase_days=WINDOW + 1)["basis"] == "ageing"


# --------------------------------------------------------------------------- #
# the limits, which are the point
# --------------------------------------------------------------------------- #

def test_a_recent_movement_beats_an_ancient_purchase():
    """Slow-but-selling is not dead.

    A SKU bought in 2020 that sold yesterday is a slow seller, and the overstock check is
    what has something to say about it. Calling it dead would have a buyer discontinue a
    line with live demand.
    """
    assert _disp(last_movement_days=2.0, last_purchase_days=3000.0) is None


def test_a_stale_movement_is_still_reported_as_a_movement():
    """The older signal keeps its own basis, so the reason on screen stays truthful."""
    out = _disp(last_movement_days=WINDOW + 5, last_purchase_days=3000.0)

    assert out["type"] == "dead"
    assert out["basis"] == "movement"


def test_no_purchase_date_leaves_the_old_abstention_intact():
    """Where there is still no evidence, the rule still says nothing.

    This is the pre-L5 behaviour and it has to survive: a never-moved SKU with no purchase
    history is unknown, not dead, and auto-flagging it for discontinuation on no evidence
    is the failure this abstention was written to prevent.
    """
    assert _disp(last_movement_days=None, last_purchase_days=None) is None


def test_nothing_on_hand_is_never_a_disposition():
    """There is no stock to dispose of, whatever its history says."""
    assert _disp(on_hand=0.0, last_purchase_days=3000.0) is None


def test_an_ageing_item_with_high_cover_is_reported_as_dead_not_overstock():
    """Dead takes precedence, as it already did for movement. Overstock says "you hold too
    much of something that sells"; dead says "this does not sell". They are different
    actions and the stronger claim wins."""
    out = _disp(last_movement_days=None, last_purchase_days=3000.0,
                days_of_cover_val=9999.0, overstock_days=365.0)

    assert out["type"] == "dead"


def test_overstock_still_fires_when_the_purchase_is_recent():
    """The new branch must not have swallowed the overstock path."""
    out = _disp(last_movement_days=None, last_purchase_days=10.0,
                days_of_cover_val=9999.0, overstock_days=365.0)

    assert out is not None and out["type"] == "overstock"


# --------------------------------------------------------------------------- #
# the wiring, against real tables
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
        category_name=f"{MARKER} cat",
    )
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} u",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=f"{MARKER}-{uuid.uuid4().hex[:8]}",
        product_name=f"{MARKER} item", category_id=cat.id, base_uom_id=uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    supplier = Supplier(
        id=_u(), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:8]}"[:30],
        supplier_name=f"{MARKER} supplier",
    )
    db.add_all([product, supplier])
    db.flush()
    return {"product": product, "supplier": supplier}


def _order(db, world, *, issue_date, po_number=None):
    po = PurchaseOrder(
        id=_u(), po_number=po_number or f"{MARKER}-{uuid.uuid4().hex[:8]}",
        supplier_id=str(world["supplier"].id), status="closed", issue_date=issue_date,
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=str(po.id), product_id=str(world["product"].id),
        qty_ordered=100, qty_received=100, line_status="closed",
    ))
    db.flush()
    return po


def test_the_map_finds_the_most_recent_purchase(db, world):
    pid = str(world["product"].id)
    _order(db, world, issue_date=date(2020, 1, 2))
    _order(db, world, issue_date=date(2021, 6, 30))

    found = _last_purchase_map(db, [pid])

    assert found[pid] == date(2021, 6, 30)


def test_a_history_line_with_no_location_is_still_found(db, world):
    """The reason the map is keyed by product and not by (product, warehouse).

    The purchase-history export names no location at all, so its lines are written with a
    null warehouse. A per-warehouse key would miss every one of them and leave the ageing
    signal reading "never bought" for exactly the stock it exists to judge.
    """
    pid = str(world["product"].id)
    po = _order(db, world, issue_date=date(2020, 3, 4))
    for line in db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.purchase_order_id == str(po.id)
    ):
        assert line.warehouse_id is None, "this test is about the no-location case"

    assert _last_purchase_map(db, [pid])[pid] == date(2020, 3, 4)


def test_a_product_never_bought_is_absent_rather_than_dated(db, world):
    """Absent, not epoch-zero: a fabricated old date would read as dead."""
    assert _last_purchase_map(db, [str(world["product"].id)]) == {}


def test_an_order_with_no_issue_date_does_not_count_as_a_purchase(db, world):
    """A dateless order says nothing about age, so it must not answer the question."""
    pid = str(world["product"].id)
    _order(db, world, issue_date=None)

    assert _last_purchase_map(db, [pid]) == {}


def test_another_company_s_purchase_is_not_visible(db, world):
    """Raw SQL, so the ORM isolation filter never sees it - the predicate is applied by
    hand and this is what proves it was."""
    pid = str(world["product"].id)
    _order(db, world, issue_date=date(2020, 1, 2))

    set_company_scope(db, frozenset({str(uuid.uuid4())}))
    assert _last_purchase_map(db, [pid]) == {}


def test_asking_about_nothing_returns_nothing(db):
    assert _last_purchase_map(db, []) == {}


# `_disposition_label` (the reason-text formatter for a `disposition` rec) was removed
# with the rec type itself (G2, `PLAN-scm-reorder-oi-feedback-1sep.md`) - a dead-stock /
# overstock report is BL-045, not a run recommendation. `eng.disposition()` above is
# still the classification the engine reads to suppress a contradictory buy
# (`reorder_run_service._emit_cell`); only the label text nobody could see any more is gone.
