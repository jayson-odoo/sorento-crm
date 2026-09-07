"""B1 (review of PR #471, `PLAN-scm-reorder-oi-feedback-1sep.md` S1): the SIXTH creation
site - `ProjectSupplyService._place_supply_borrows` - missed in the original grill and the
first implementation pass.

The asker-side ORDER_BACK row this method writes was left at the column's own
`server_default='awaiting'`, so a step-3 supply borrow's own row was born invisible to
purchasing (never in `ACK_LINKABLE`, so never cascaded, never counted by the plan) and
unactionable (the tolerant `acknowledge_rows` guard has nothing to do for a row nobody can
reach through the UI, which no longer offers Confirm at all).

Exercises `_place_supply_borrows` directly rather than through the full ladder v7.1 step-3
HTTP confirm (real supply-key validation needs a real inbound document with a live
balance, which is a different test's job) - this one is about the ROW this method writes,
not the borrow ladder's own correctness.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services.project_supply_service import ProjectSupplyService

from .test_order_inquiry_handshake import _open_po_line, _raise_one_row, api, world
from .test_planning_changes import _core_line, _core_so, _project_line, _project_so, _uid

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


def test_a_supply_borrow_row_is_born_acknowledged(api):
    _client, world = api
    fixture = _raise_one_row(api, qty="10")
    order = fixture["order"]
    line = fixture["line"]
    # A real, resolvable target: `place_supply_borrow` writes a firm link through
    # `place_on_po_allocations`, which refuses a document that does not exist.
    _po, po_line = _open_po_line(world, qty=50)

    supply = ProjectSupplyService(world.db)
    decision = supply.active_decision(str(order.id))
    assert decision is not None
    inquiry = (
        world.db.query(OrderInquiry)
        .filter(OrderInquiry.id == fixture["row"].order_inquiry_id)
        .one()
    )

    item = SimpleNamespace(
        supply_key=f"po:{po_line.id}",
        qty=Decimal("5"),
        donor_core_line_id=None,
        supply_document=None,
        reason="Step 3 supply borrow",
    )
    entry = SimpleNamespace(borrow=[item])
    checked = [(line, entry, None)]

    supply._place_supply_borrows(
        order, decision, checked, inquiry, actor_user_id=world.buyer
    )
    world.db.commit()

    row = (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == IV_ORDER_BACK,
        )
        .order_by(OrderInquiryRow.created_at.desc())
        .first()
    )
    assert row is not None, "the borrow-asker row was not written at all"
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert str(row.acknowledged_by) == str(world.buyer)
    assert row.acknowledged_at is not None


def test_a_supply_borrow_with_no_inquiry_passed_mints_the_header(api):
    """The fallback in `_place_supply_borrows` (project_supply_service.py around line
    5805, fix/oi-empty-header). `refresh_for_decision`'s own gate correctly raises no
    header for a confirmation whose Buy residual and donor holes are both empty, but the
    borrow composition never reaches that gate, so a step-3 supply borrow's own
    asker-side ORDER_BACK row still needs somewhere to live. Passing `inquiry=None` is
    exactly that case, and nothing exercised it before this test: the order has NO
    header at all going in, and the method must mint one rather than crash on
    `None.id`.
    """
    _client, world = api
    core_so = _core_so(world.db, world.company_id)
    core_line = _core_line(
        world.db, core_so, world.product, world.warehouse, qty_ordered="10",
    )
    order = _project_so(
        world.db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(
        world.db, order, line_no=1, product=world.product, core_line=core_line
    )
    world.db.commit()

    # No confirmation has run for this order yet, so it has no header of its own.
    assert (
        world.db.query(OrderInquiry)
        .filter(OrderInquiry.project_sales_order_id == order.id)
        .count()
        == 0
    )

    decision = SOSupplyDecision(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        revision_no=1,
        state="active",
        line_snapshots=[{"line_no": line.line_no}],
        confirmed_by=world.buyer,
        confirmed_at=datetime.utcnow(),
    )
    world.db.add(decision)
    world.db.flush()

    _po, po_line = _open_po_line(world, qty=50)
    item = SimpleNamespace(
        supply_key=f"po:{po_line.id}",
        qty=Decimal("5"),
        donor_core_line_id=None,
        supply_document=None,
        reason="Step 3 supply borrow",
    )
    entry = SimpleNamespace(borrow=[item])
    checked = [(line, entry, None)]

    supply = ProjectSupplyService(world.db)
    supply._place_supply_borrows(
        order, decision, checked, None, actor_user_id=world.buyer
    )
    world.db.commit()

    inquiry = (
        world.db.query(OrderInquiry)
        .filter(OrderInquiry.project_sales_order_id == order.id)
        .filter(OrderInquiry.amendment_id.is_(None))
        .one()
    )
    assert inquiry.inquiry_no, "a minted header must carry a real OI number"

    rows = (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.order_inquiry_id == inquiry.id,
            OrderInquiryRow.verb == IV_ORDER_BACK,
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].so_line_id == line.id
    assert rows[0].qty == Decimal("5")
