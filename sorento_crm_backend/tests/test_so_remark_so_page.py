"""FULFIL-SO-REMARK Sales Order page API (AC-16): the SO detail carries `ship_info`, `remark`
(AC-5 default over ALL lines) and per line `is_mockup` / `mockup_label` (AC-6 over ALL lines)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, scm_app, seed_user  # noqa: F401

pytestmark = requires_pg

MARKER = "ZZTSOREM"
MOCK = "***FOR STH(100)-2 UNITS MOCK UP"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


def _seed(scm_app, *, ship_info=None, note=None, lines=(None,), headings=None, cancelled=()):
    """One SO with one line per entry of `lines` (the line_remark, or None). Returns
    (app, so, [line ids])."""
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))
    uom = UnitOfMeasure(id=_uid(), uom_code=_code("U")[:20], uom_name="Unit")
    category = ProductCategory(id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} cat")
    db.add_all([uom, category])
    db.flush()
    customer = Customer(id=_uid(), customer_code=_code("CUS"),
                        customer_name=f"{MARKER} UNIJOH DEVELOPMENT SDN BHD", is_active=True)
    warehouse = Warehouse(id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name="store",
                          is_active=True)
    db.add_all([customer, warehouse])
    db.flush()
    so = SalesOrder(id=_uid(), so_number=_code("SO"), customer_id=customer.id, status="open",
                    priority="normal", order_date=date(2026, 7, 16), source_system="scm_upload",
                    internal_note=note)
    db.add(so)
    db.flush()
    ids = []
    for n, remark in enumerate(lines):
        product = Product(id=_uid(), product_code=_code(f"P{n}"), product_name=f"{MARKER} p{n}",
                          category_id=category.id, base_uom_id=uom.id, list_price=100)
        db.add(product)
        db.flush()
        line = SalesOrderLine(id=_uid(), sales_order_id=so.id, product_id=product.id,
                              warehouse_id=warehouse.id, qty_ordered=1, qty_delivered=0,
                              line_status="cancelled" if n in cancelled else "open", line_no=n + 1)
        db.add(line)
        db.flush()
        heading = headings[n] if headings else None
        db.execute(text("UPDATE sales_order_lines SET line_remark = :r, section_heading = :h "
                        "WHERE id = :id"), {"r": remark, "h": heading, "id": line.id})
        ids.append(str(line.id))
    if ship_info is not None:
        db.execute(text("UPDATE sales_orders SET ship_info = :s WHERE id = :id"),
                   {"s": ship_info, "id": so.id})
    db.flush()
    return app, so, ids


def _detail(app, so):
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{so.id}")
    assert res.status_code == 200, res.text
    return res.json()


def _flags(body, key):
    return {l["id"]: l[key] for l in body["lines"]}


def test_ac16_purchase_request_words(scm_app):
    app, so, _ids = _seed(scm_app, ship_info="PURCHASE REQUEST", lines=(None,))
    body = _detail(app, so)
    assert body["ship_info"] == "PURCHASE REQUEST"
    assert body["remark"] == "Purchase Request"
    assert [l["mockup_label"] for l in body["lines"]] == [False]


def test_ac16_sponsorship_with_one_mockup_line_of_two_badges_that_line_only(scm_app):
    app, so, ids = _seed(scm_app, ship_info="SPONSORSHIP", lines=(MOCK, None))
    body = _detail(app, so)
    assert body["remark"] == "Sponsorship"
    assert _flags(body, "is_mockup") == {ids[0]: True, ids[1]: False}
    assert _flags(body, "mockup_label") == {ids[0]: True, ids[1]: False}


def test_ac16_note_mock_whole_so_has_no_labels(scm_app):
    app, so, ids = _seed(scm_app, note="***FOR MOCKUP", lines=(None, None))
    body = _detail(app, so)
    assert body["remark"] == "Mockup"
    assert all(_flags(body, "is_mockup").values())
    assert not any(_flags(body, "mockup_label").values())


def test_ac16_three_mockup_lines_among_actual_lines_are_labelled(scm_app):
    app, so, ids = _seed(scm_app, ship_info="U 2603-00010",
                         lines=(MOCK, None, MOCK, None, None, MOCK))
    body = _detail(app, so)
    assert body["remark"] == "Mockup"
    assert [i for i, v in _flags(body, "mockup_label").items() if v] == [ids[0], ids[2], ids[5]]


def test_ac16_section_heading_marks_mockup_lines(scm_app):
    app, so, ids = _seed(scm_app, lines=(None, None, None),
                         headings=("MOCK UP - BLOCK 1", "MOCK UP - BLOCK 1", "BLOCK 1 & 3 - JUL 27"))
    body = _detail(app, so)
    assert _flags(body, "is_mockup") == {ids[0]: True, ids[1]: True, ids[2]: False}
    assert _flags(body, "mockup_label") == {ids[0]: True, ids[1]: True, ids[2]: False}


def test_ac16_a_normal_so_is_blank_with_no_labels(scm_app):
    app, so, _ids = _seed(scm_app, ship_info="OT06/2702", lines=(None, None))
    body = _detail(app, so)
    assert body["remark"] == ""
    assert body["ship_info"] == "OT06/2702"
    assert not any(_flags(body, "is_mockup").values())
    assert not any(_flags(body, "mockup_label").values())


def test_ac16_ship_info_is_null_when_not_stored(scm_app):
    app, so, _ids = _seed(scm_app, lines=(None,))
    body = _detail(app, so)
    assert "ship_info" in body and body["ship_info"] is None
    assert body["remark"] == ""


def test_ac16_a_non_adopted_so_still_returns_the_fields(scm_app):
    """No projects.sales_orders row exists for this SO (the seed creates none)."""
    app, db, _g, _k = scm_app
    app, so, ids = _seed(scm_app, ship_info="SPONSORSHIP", lines=(MOCK, None))
    assert db.execute(text("SELECT count(*) FROM projects.sales_orders WHERE so_id = :i"),
                      {"i": so.id}).scalar() == 0
    body = _detail(app, so)
    assert body["remark"] == "Sponsorship"
    assert _flags(body, "mockup_label") == {ids[0]: True, ids[1]: False}


def test_live_1_a_cancelled_mockup_line_does_not_count(scm_app):
    app, so, ids = _seed(scm_app, lines=(MOCK, None, None), cancelled=(0,))
    body = _detail(app, so)
    assert body["remark"] == ""
    assert not any(_flags(body, "mockup_label").values())


def test_live_2_live_lines_all_mockup_get_remark_but_no_labels(scm_app):
    app, so, ids = _seed(scm_app, lines=(MOCK, MOCK, MOCK, None), cancelled=(3,))
    body = _detail(app, so)
    assert body["remark"] == "Mockup"
    assert not any(_flags(body, "mockup_label").values())


def test_live_3_a_cancelled_line_never_carries_the_label(scm_app):
    app, so, ids = _seed(scm_app, lines=(MOCK, MOCK, None), cancelled=(0,))
    body = _detail(app, so)
    assert _flags(body, "mockup_label")[ids[0]] is False
    assert _flags(body, "mockup_label")[ids[1]] is True
