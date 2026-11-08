"""CONSIGN-OWN-BIN-EMAIL: a consignment's own-bin Borrow is told to purchasing as an order back,
exactly as a sales order line's is.

Owner ruling 2 Nov 2026 ("if order own bin also need to send email to purchasing for order
back"), reversing CONSIGN-PLAN Q1 for the own-bin Borrow: the Confirm raises the ORDER_BACK row
and the purchasing email says ORDER BACK, the same as a sales order line. These tests assert on
the row AND on the purchasing email itself (the `order_inquiry_handover` dispatch, captured,
nothing sent).

Plan: `documentation/plans/scm/PLAN-consign-own-bin-email-02nov.md`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

from .._pg_fixture import blank_session
from ..test_fulfilment_board import _uid
from ..test_oi_saved_line_email import TRIGGER, _lines, emails  # noqa: F401 - fixture
from ..test_so_supply_confirmation import _stock, _warehouse
from .test_borrow_own_location import _confirm, _own_borrow, _own_world
from .test_consign_plan import _consign_world
from .test_dealer_segment_planning import _dealer_pool
from .test_project_supply_service_ladder import _seed_line, _world

# FP-EMAIL-ONE-TRIGGER: this suite pins the email's content; its writes stand in for the
# board Confirm, the one trigger of the purchasing email (tests/conftest.py).
pytestmark = pytest.mark.usefixtures("as_board_confirm")

__all__ = ["emails"]


@pytest.fixture
def contexts(monkeypatch):
    """Each purchasing email's whole dispatch context: `sales_order_class` is what picks the
    automation row (DEALER-OI-ROUTE condition), `handover` is the email itself."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()
    sent: list = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        if trigger_type == TRIGGER:
            sent.append(context)
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake_dispatch
    )
    return sent


def _all_lines(sent):
    return [line for email in sent for line in _lines(email)]


def _live_rows(db, world):
    return sorted(
        (row.verb, row.qty, row.stock_location)
        for row in db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == world["line"].id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )


# ------------------------------------------------------------------ UAC-1, UAC-2


def test_uac1_an_own_bin_borrow_on_a_consignment_raises_and_emails_its_order_back(emails):
    with blank_session() as db:
        world = _consign_world(db)
        _confirm(db, world, borrow=[_own_borrow(world, "10", "Goods are the CON stock.")])
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert rows == [("ORDER_BACK", Decimal("10"), own)], rows
    assert _all_lines(emails) == [(code, "10", own, "ORDER BACK")], _all_lines(emails)


def test_uac2_buy_beside_an_own_bin_borrow_raises_both_and_emails_both(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=6)
        _confirm(
            db, world, borrow=[_own_borrow(world, "6", "Goods are the CON stock.")], buy_qty="4",
        )
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert rows == [("ORDER", Decimal("4"), own), ("ORDER_BACK", Decimal("6"), own)], rows
    assert _all_lines(emails) == [(code, "10", own, "ORDER BACK 6 & ORDER 4")], (
        _all_lines(emails)
    )


# ------------------------------------------------------------------ UAC-3, UAC-4 (pins)


def test_uac3_a_consignment_borrow_from_another_bin_still_emails_order_back(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=0)
        other = _warehouse(db, f"ZZB{_uid()[:4]}-BB")
        _stock(db, world["product"], other, on_hand=10)
        db.commit()
        _confirm(db, world, borrow=[{
            "source": "other_location",
            "warehouse_id": str(other.id),
            "qty": "10",
            "reason": "Free stock at another bin.",
        }])
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code
        other_code = other.warehouse_code

    assert rows == [("ORDER_BACK", Decimal("10"), other_code)], rows
    assert _all_lines(emails) == [(code, "10", own, f"ORDER BACK {other_code}")], (
        _all_lines(emails)
    )


def test_uac4_a_planner_keyed_buy_on_a_consignment_still_emails_order(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=0)
        _confirm(db, world, buy_qty="10")
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert rows == [("ORDER", Decimal("10"), own)], rows
    assert _all_lines(emails) == [(code, "10", own, "ORDER")], _all_lines(emails)


# ------------------------------------------------------------------ UAC-5: same as a sales order


def test_uac5_a_sales_order_lines_own_bin_borrow_at_a_planned_bin_emails_as_before(contexts):
    """A project-class sales order line at a bin IN fulfilment planning (flag on)."""
    with blank_session() as db:
        world = _own_world(db, on_hand=10)
        flag = world["own"].fulfilment_planning
        _confirm(db, world, borrow=[_own_borrow(world, "10")])
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert flag is True
    assert rows == [("ORDER_BACK", Decimal("10"), own)], rows
    assert [c["sales_order_class"] for c in contexts] == ["project"], contexts
    assert _all_lines([c["handover"] for c in contexts]) == [(code, "10", own, "ORDER BACK")]


def test_uac5_a_retail_order_lines_own_bin_borrow_at_a_flagged_off_dealer_bin(contexts):
    """A retail-class sales order line at an active dealer bin flagged OUT of fulfilment
    planning (the shape of BRW): its own-bin Borrow is owed back there and goes to the Retail
    automation row."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order, line, core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        core_so.demand_class = "retail"
        order.so_id = core_so.id
        db.commit()
        world = {"eling": actor, "product": product, "own": pool, "order": order, "line": line}
        flags = (pool.is_active, pool.fulfilment_planning, pool.segment)
        _confirm(db, world, borrow=[_own_borrow(world, "10")])
        rows = _live_rows(db, world)
        code = product.product_code
        own = pool.warehouse_code

    assert flags == (True, False, "dealer")
    assert rows == [("ORDER_BACK", Decimal("10"), own)], rows
    assert [c["sales_order_class"] for c in contexts] == ["retail"], contexts
    assert _all_lines([c["handover"] for c in contexts]) == [(code, "10", own, "ORDER BACK")]


def test_uac5_a_consignment_own_bin_borrow_reads_exactly_as_a_sales_order_lines(emails):
    """The ruling itself: whatever a sales order line's own-bin Borrow raises and emails, a
    consignment's raises and emails the same ("Borrow from another order" off, its default)."""

    def run(make_world):
        with blank_session() as db:
            world = make_world(db)
            db.commit()
            emails.clear()
            _confirm(db, world, borrow=[_own_borrow(world, "10", "Goods at our own bin.")])
            rows = [(verb, qty) for verb, qty, _location in _live_rows(db, world)]
        return rows, [remark for *_rest, remark in _all_lines(emails)]

    sales_order = run(lambda db: _own_world(db, on_hand=10))
    consignment = run(lambda db: _consign_world(db))

    assert consignment == sales_order, (consignment, sales_order)


# ------------------------------------------------------------------ UAC-6: re-confirm


def test_uac6_re_confirming_the_same_own_bin_borrow_sends_nothing_new(emails):
    with blank_session() as db:
        world = _consign_world(db)
        borrow = [_own_borrow(world, "10", "Goods are the CON stock.")]
        _confirm(db, world, borrow=borrow)
        first = _live_rows(db, world)
        emails.clear()
        _confirm(db, world, borrow=borrow)
        again = _live_rows(db, world)

    assert first == again and len(first) == 1, (first, again)
    assert _all_lines(emails) == [], _all_lines(emails)


def test_uac6_re_confirming_the_same_buy_and_own_bin_borrow_sends_nothing_new(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=6)
        borrow = [_own_borrow(world, "6", "Goods are the CON stock.")]
        _confirm(db, world, borrow=borrow, buy_qty="4")
        first = _live_rows(db, world)
        emails.clear()
        _confirm(db, world, borrow=borrow, buy_qty="4")
        again = _live_rows(db, world)

    assert first == again and len(first) == 2, (first, again)
    assert _all_lines(emails) == [], _all_lines(emails)
