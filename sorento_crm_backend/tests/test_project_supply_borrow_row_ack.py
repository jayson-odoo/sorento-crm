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

from decimal import Decimal
from types import SimpleNamespace

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
)
from app.services.project_supply_service import ProjectSupplyService

from .test_order_inquiry_handshake import _open_po_line, _raise_one_row, api, world

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
