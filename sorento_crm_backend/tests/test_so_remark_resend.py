"""FULFIL-SO-REMARK resend (AC-13): "Send to purchasing" prints the AC-5 default and the
AC-12 labels computed from the resent lines."""
from __future__ import annotations

import sqlalchemy as sa

from app.models.project_so import INQUIRY_RAISED

from .test_oi_handover_resend import PREVIEW, _automation, _ok, rs  # noqa: F401 - fixture
from .test_order_inquiry_worklist import _inquiry_for, _row, _uid
from .test_planning_changes import _core_line, _core_so, _project_line
from .test_so_supply_confirmation import _product, _warehouse


def _world_with_so(world, *, ship_info=None, flags):
    """A core SO (lines flagged MOCK per `flags`), its project mirror, one inquiry with one
    open row per line pointing at the mirror line."""
    db = world.db
    product = _product(db)
    wh = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    core_so = _core_so(db, world.company_id)
    core_lines = [
        _core_line(db, core_so, product, wh, qty_ordered="5") for _ in flags
    ]
    from app.models.project_so import ProjectSalesOrder

    order = ProjectSalesOrder(
        id=_uid(), company_id=world.company_id, provisional_ref=f"ZZT-{_uid()[:8]}",
        so_id=core_so.id, autocount_doc_no=core_so.so_number, status="adopted",
    )
    db.add(order)
    db.flush()
    mirrors = [
        _project_line(db, order, line_no=10 * (i + 1), product=product, core_line=cl)
        for i, cl in enumerate(core_lines)
    ]
    inquiry = _inquiry_for(db, world.company_id, order)
    inquiry.raised_by = world.requester
    rows = [
        _row(db, world.company_id, inquiry, state=INQUIRY_RAISED, qty="5",
             item_code=f"ZZT-RS-{i}", stock_location="BRW-BB", so_line_id=m.id,
             delivery_date=None)
        for i, m in enumerate(mirrors)
    ]
    if ship_info is not None:
        db.execute(sa.text("UPDATE sales_orders SET ship_info = :v WHERE id = :id"),
                   {"v": ship_info, "id": core_so.id})
    for cl, flag in zip(core_lines, flags):
        if flag:
            db.execute(sa.text("UPDATE sales_order_lines SET line_remark = 'MOCK UP' "
                               "WHERE id = :id"), {"id": cl.id})
    db.commit()
    return inquiry, rows


def _preview_html(client, inquiry):
    body = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))
    assert len(body["emails"]) == 1, body
    return body["emails"][0]["body_html"]


def test_ac13_resend_prints_the_remark_type_default(rs):
    client, world = rs
    _automation(world)
    inquiry, _rows = _world_with_so(world, ship_info="SPONSORSHIP", flags=[False])

    html = _preview_html(client, inquiry)

    assert "REMARK" in html
    assert "Sponsorship" in html


def test_ac13_resend_prints_mockup_default_and_labels_mixed_lines(rs):
    client, world = rs
    _automation(world)
    inquiry, rows = _world_with_so(world, flags=[True, False])

    html = _preview_html(client, inquiry)

    assert "Mockup" in html
    assert html.count("Mockup, ") == 1, html


def test_ac13_resend_with_no_mockup_prints_no_mockup_word(rs):
    client, world = rs
    _automation(world)
    inquiry, _rows = _world_with_so(world, flags=[False, False])

    html = _preview_html(client, inquiry)

    assert "Mockup" not in html
