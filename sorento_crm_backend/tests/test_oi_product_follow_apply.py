"""OI-PRODUCT-FOLLOW S2 (`documentation/plans/scm/PLAN-oi-product-follow-2oct.md`).

The planning board applies a `product_changed` row: the line's order inquiry row is
restated IN PLACE on the new product, exactly the way a qty / date change already is
(`_settle_row_in_place`), with the old code kept as `previous_item_code` ("was X").

Recommended path of the behaviour card (Q1 (a): on apply; Q2 (a): a link on a document of
the OLD product is given back, never re-pointed). Owner answer pending when written.

Runs on the real database, rolled back (same fixture as the board-apply suite).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    IV_ORDER,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import PRODUCT_CHANGED, Change, Line

from .test_planning_change_apply_on_board import (  # noqa: F401 - fixtures reused
    _build,
    _confirm,
    _link,
    _order_row,
    _po_line,
    _rows_of,
    _supplier,
    api,
    world,
)
from .test_planning_changes import (
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
)

DUE = date(2026, 11, 20)


def _swap_fixture(api, *, linked: bool = False, acknowledged: bool = False):
    """One line of product A confirmed as a Buy of 10 (one ORDER row), then AutoCount
    swaps the line to product B on the same DtlKey and the ESB raises one
    `product_changed` row. The mirror already names B (S1)."""
    client, world = api
    db = world.db
    old_product = world.product
    new_product = _product(db)
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, old_product, world.own_wh, qty_ordered="10",
                      required_date=DUE)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=old_product, core_line=core)
    db.commit()

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="10")])
    assert response.status_code == 200, response.text
    row = _order_row(world, line)
    assert row.item_code == old_product.product_code

    link = None
    if linked:
        _, po_line = _po_line(world, _supplier(world), qty=10, expected_date=DUE)
        link = _link(world, row, po_line, qty=10, document="202609-S0776")
    if acknowledged:
        row.ack_state = ACK_ACKNOWLEDGED
    db.commit()

    core.product_id = new_product.id
    line.product_id = new_product.id
    db.commit()

    change = Change(
        PRODUCT_CHANGED, core_so.so_number, new_product.product_code, "ZZT",
        before=Line(doc_number=core_so.so_number, item_code=old_product.product_code,
                    location="ZZT", qty=10.0, required_date=DUE, row_ref=str(core.id)),
        after=Line(doc_number=core_so.so_number, item_code=new_product.product_code,
                   location="ZZT", qty=10.0, required_date=DUE, row_ref=str(core.id)),
    )
    batch = _build(world, [change], core_so, [str(core.id)])
    assert batch is not None, "a held line's product swap raises a batch"
    return {
        "client": client, "world": world, "order": order, "line": line, "row": row,
        "batch": batch, "old": old_product, "new": new_product, "link": link,
    }


def _apply(fx):
    return _confirm(
        fx["client"], fx["order"].id, [_line_payload(fx["line"].id, buy_qty="10")],
        batch_id=str(fx["batch"].id),
    )


def _live_order_rows(fx):
    return [
        r for r in _rows_of(fx["world"], fx["line"])
        if r.verb == IV_ORDER and r.state != INQUIRY_CANCELLED
    ]


def test_apply_restates_the_oi_row_on_the_new_product_and_keeps_the_old_as_was(api):
    fx = _swap_fixture(api)
    row_id = str(fx["row"].id)

    response = _apply(fx)
    assert response.status_code == 200, response.text
    fx["world"].db.commit()
    fx["world"].db.expire_all()

    live = _live_order_rows(fx)
    assert len(live) == 1, "one OI row per SO line, always"
    row = live[0]
    assert str(row.id) == row_id, "restated in place, never re-raised"
    assert row.item_code == fx["new"].product_code, (
        "S2: the OI line must follow the SO line's new product"
    )
    assert row.previous_item_code == fx["old"].product_code, (
        "S2: the old product stays visible as 'was X'"
    )
    assert Decimal(str(row.qty)) == Decimal("10")
    assert row.delivery_date == DUE
    assert fx["old"].product_code in (row.note or ""), "the note says what it was"


def test_an_acknowledged_row_goes_back_to_to_confirm_on_a_product_swap(api):
    fx = _swap_fixture(api, acknowledged=True)

    response = _apply(fx)
    assert response.status_code == 200, response.text
    fx["world"].db.commit()
    fx["world"].db.expire_all()

    row = _live_order_rows(fx)[0]
    assert row.item_code == fx["new"].product_code
    assert row.ack_state == ACK_CHANGED, "purchasing re-confirms an amended row"
    assert row.changed_at is not None


def test_a_link_on_the_old_products_po_is_given_back_not_re_pointed(api):
    fx = _swap_fixture(api, linked=True)

    response = _apply(fx)
    assert response.status_code == 200, response.text
    fx["world"].db.commit()
    fx["world"].db.expire_all()

    row = _live_order_rows(fx)[0]
    assert row.item_code == fx["new"].product_code
    links = ProjectOrderInquiryService(fx["world"].db)._links_of(row.id)
    assert links == [], (
        "Q2 (a): a PO line for the OLD product is not cover for the new one"
    )
    assert "202609-S0776" in (row.note or ""), "the give-back is stamped on the row"


def test_a_plain_qty_settle_writes_no_previous_item_code(api):
    """Kill guard: `previous_item_code` is written only when the product moved."""
    fx = _swap_fixture(api)
    # Undo the swap on the row's side: the row already names the new product, so the
    # apply is a restatement with no product change.
    fx["row"].item_code = fx["new"].product_code
    fx["world"].db.commit()

    response = _apply(fx)
    assert response.status_code == 200, response.text
    fx["world"].db.commit()
    fx["world"].db.expire_all()

    row = _live_order_rows(fx)[0]
    assert row.previous_item_code is None


def test_worklist_payload_carries_previous_item_code(api):
    fx = _swap_fixture(api)
    assert _apply(fx).status_code == 200
    fx["world"].db.commit()

    client = fx["client"]
    res = client.get(
        "/api/v1/project-sales/order-inquiries",
        params={"query": fx["new"].product_code},
    )
    assert res.status_code == 200, res.text
    items = res.json()["data"]
    assert len(items) == 1, res.text
    assert items[0]["item_code"] == fx["new"].product_code
    assert items[0].get("previous_item_code") == fx["old"].product_code


def test_oi_row_model_has_previous_item_code():
    assert hasattr(OrderInquiryRow, "previous_item_code")
