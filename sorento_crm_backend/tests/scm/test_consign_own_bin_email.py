"""CONSIGN-OWN-BIN-EMAIL: what the purchasing email lists agrees with the rows a Confirm raised.

Owner ruling CONSIGN-PLAN Q1: a consignment's Borrow at its OWN bin sends nothing to
purchasing. The order inquiry row already obeys it (`test_consign_plan.test_uac06`); these
tests assert on the purchasing email itself (the `order_inquiry_handover` dispatch, captured,
nothing sent).

Plan: `documentation/plans/scm/PLAN-consign-own-bin-email-02nov.md`.
"""
from __future__ import annotations

from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

from .._pg_fixture import blank_session
from ..test_fulfilment_board import _uid
from ..test_oi_saved_line_email import _lines, emails  # noqa: F401 - fixture
from ..test_so_supply_confirmation import _stock, _warehouse
from .test_borrow_own_location import _confirm, _own_borrow, _own_world
from .test_consign_plan import _consign_world

__all__ = ["emails"]


def _all_lines(sent):
    return [line for email in sent for line in _lines(email)]


def _live_rows(db, world):
    return [
        (row.verb, row.qty)
        for row in db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == world["line"].id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    ]


# ------------------------------------------------------------------ UAC-1, UAC-2 (red today)


def test_uac1_an_own_bin_borrow_on_a_consignment_sends_purchasing_nothing(emails):
    with blank_session() as db:
        world = _consign_world(db)
        _confirm(db, world, borrow=[_own_borrow(world, "10", "Goods are the CON stock.")])
        rows = _live_rows(db, world)

    assert rows == [], "the row already obeys the ruling"
    assert _all_lines(emails) == [], _all_lines(emails)


def test_uac2_buy_beside_an_own_bin_borrow_emails_only_the_order(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=6)
        _confirm(
            db, world, borrow=[_own_borrow(world, "6", "Goods are the CON stock.")], buy_qty="4",
        )
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert [verb for verb, _qty in rows] == ["ORDER"], rows
    assert _all_lines(emails) == [(code, "10", own, "ORDER 4")], _all_lines(emails)


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
        code = world["product"].product_code
        own = world["own"].warehouse_code
        other_code = other.warehouse_code

    assert _all_lines(emails) == [(code, "10", own, f"ORDER BACK {other_code}")], (
        _all_lines(emails)
    )


def test_uac4_a_planner_keyed_buy_on_a_consignment_still_emails_order(emails):
    with blank_session() as db:
        world = _consign_world(db, con_stock=0)
        _confirm(db, world, buy_qty="10")
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert _all_lines(emails) == [(code, "10", own, "ORDER")], _all_lines(emails)


# ------------------------------------------------------------------ UAC-5, UAC-6 (pins)


def test_uac5_a_sales_order_lines_own_bin_borrow_emails_as_before(emails):
    """Not a consignment: the exemption is the doc type's, never the bin's alone."""
    with blank_session() as db:
        world = _own_world(db, on_hand=10)
        _confirm(db, world, borrow=[_own_borrow(world, "10")])
        rows = _live_rows(db, world)
        code = world["product"].product_code
        own = world["own"].warehouse_code

    assert [verb for verb, _qty in rows] == ["ORDER_BACK"], rows
    assert _all_lines(emails) == [(code, "10", own, "ORDER BACK")], _all_lines(emails)


def test_uac6_re_confirming_the_same_own_bin_borrow_sends_nothing(emails):
    with blank_session() as db:
        world = _consign_world(db)
        borrow = [_own_borrow(world, "10", "Goods are the CON stock.")]
        _confirm(db, world, borrow=borrow)
        emails.clear()
        _confirm(db, world, borrow=borrow)

    assert _all_lines(emails) == [], _all_lines(emails)
