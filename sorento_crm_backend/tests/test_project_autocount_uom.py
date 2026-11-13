"""AutoCount QT / SO lines send the item's AutoCount UOM, not the project line's default.

Live refusal (db3, 6 Nov): AutoCount rejected a quotation line sent with uom "EA" for an item
whose AutoCount UOM is "UNIT". Rule: a line goes with the product's base UOM code
(`Product.base_uom_id` -> `UnitOfMeasure.uom_code`); a product with no base UOM keeps the
line's uom. No word aliases.

Builder tests are pure (`base_uoms` = product id -> base UOM code, resolved once per payload by
the service); the send tests assert the body the fake Shared Service received.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.product import UnitOfMeasure
from tests._ac_write_support import (
    BASE,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    api_fixture,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
)


def _line(**over):
    base = dict(
        product_id="p-1",
        product_set_id=None,
        set_parts_snapshot=None,
        product_code_snapshot="SRTWB242",
        description_snapshot="Wash basin 242",
        uom="EA",
        quantity=Decimal("10"),
        unit_price=Decimal("180.00"),
        line_total=Decimal("1800.00"),
        is_rate_only=False,
        sort_order=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _build(lines, base_uoms):
    from app.services.project_autocount_write_service import build_quotation_lines

    return build_quotation_lines(lines, location="BRW-BB", base_uoms=base_uoms)


def test_quotation_line_with_ea_for_a_unit_product_is_sent_as_unit():
    out = _build([_line(uom="EA")], {"p-1": "UNIT"})

    assert [l["uom"] for l in out.lines] == ["UNIT"]


def test_line_uom_equal_to_the_base_uom_in_other_case_is_sent_as_the_base_code():
    out = _build([_line(uom="  unit ")], {"p-1": "UNIT"})

    assert [l["uom"] for l in out.lines] == ["UNIT"]


def test_product_with_no_base_uom_keeps_the_line_uom():
    out = _build([_line(uom="EA")], {})

    assert [l["uom"] for l in out.lines] == ["EA"]


def test_exploded_set_parts_each_follow_the_rule_for_their_own_product():
    set_line = _line(
        product_id=None,
        product_set_id="set-1",
        product_code_snapshot="SET-WC01",
        uom="SET",
        quantity=Decimal("2"),
        unit_price=Decimal("950.00"),
        set_parts_snapshot=[
            {"product_id": "p-wc", "product_code": "SRTWC100", "description": "WC",
             "quantity": "1", "is_driver": True, "uom": "EA"},
            {"product_id": "p-av", "product_code": "SRTAV020", "description": "AV",
             "quantity": "2", "is_driver": False, "uom": "pcs"},
            {"product_id": "p-fh", "product_code": "SRTFH030", "description": "FH",
             "quantity": "2", "is_driver": False, "uom": "EA"},
        ],
    )

    out = _build([set_line], {"p-wc": "UNIT", "p-av": "PCS"})

    assert [(l["itemCode"], l["uom"]) for l in out.lines] == [
        ("SRTWC100", "UNIT"),
        ("SRTAV020", "PCS"),
        ("SRTFH030", "EA"),  # no base UOM: the part's own uom stays
    ]


# --------------------------------------------------------------------------- the sends


def _set_base_uoms(db, mapping):
    """Point each product at a UOM row carrying the wanted code (codes avoid seeded ones)."""
    row_of = {}
    for product, code in mapping:
        if code in row_of:
            product.base_uom_id = row_of[code]
            continue
        uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == product.base_uom_id).one()
        uom.uom_code = code
        row_of[code] = uom.id
    db.flush()


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def test_quotation_create_sends_each_items_autocount_uom(qt_api, fake_ss):
    from app.models.projects import ProjectQuotationLine

    client, db, world = qt_api
    _set_base_uoms(db, [(world.p1, "ZUNIT"), (world.p_wc, "ZUNIT"), (world.p_av, "ZPCS")])
    ordinary = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.product_id == world.p1.id).one()
    ordinary.uom = "EA"
    set_line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.product_set_id == world.pset.id).one()
    set_line.set_parts_snapshot = [
        {**part, "uom": "EA"} for part in set_line.set_parts_snapshot
    ]
    db.commit()
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (
        200,
        done_body(doc_no="QT000777", doc_key=5001, details=[
            detail(1, world.p1.product_code, "10", "180.00", "BRW-BB", None, 1),
        ]),
    )

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    lines = fake_ss.body(request)["lines"]
    assert {l["itemCode"]: l["uom"] for l in lines} == {
        world.p1.product_code: "ZUNIT",
        world.p_wc.product_code: "ZUNIT",
        world.p_av.product_code: "ZPCS",
    }


def test_sales_order_create_sends_each_items_autocount_uom(so_api, fake_ss):
    client, db, world = so_api
    _set_base_uoms(db, [(world.product, "ZUNIT"), (world.product2, "ZPCS")])
    world.line1.uom = "EA"
    world.line2.uom = " pcs"
    db.commit()
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        200,
        done_body(doc_no="SO412345", details=[
            detail(12009, world.product.product_code, "100", "392.85", "BRW-BB", "2026-07-01", 1),
            detail(12010, world.product2.product_code, "20", "50.00", "MWH-BB", "2026-08-01", 2),
        ]),
    )

    response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    lines = fake_ss.body(request)["lines"]
    assert [(l["itemCode"], l["uom"]) for l in lines] == [
        (world.product.product_code, "ZUNIT"),
        (world.product2.product_code, "ZPCS"),
    ]
