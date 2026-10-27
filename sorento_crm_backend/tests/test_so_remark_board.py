"""FULFIL-SO-REMARK board (AC-7): each line contribution says `is_mockup`, each order
standing says `remark_type`, through the real route (a field the response model does not
declare is dropped silently)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.models.base import company_scope

from ._pg_fixture import blank_session
from .test_fulfilment_board import (
    BASE,
    MARKER,
    TODAY,
    VIEW,
    _client,
    _line,
    _order,
    _pooled_warehouses,
    _product,
    _restore,
    _sorento,
    _stock,
    _uid,
    _user,
)


def _world(db, *, ship_info=None, note=None, line_remarks=(None, None), headings=(None, None)):
    product = _product(db, f"ZZT-{_uid()[:6]}")
    warehouse, pool = _pooled_warehouses(db)
    _stock(db, product, pool, on_hand=100)
    order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
    lines = [
        _line(db, order, product, qty="2", required_date=date(2026, 9, 3), warehouse=warehouse)
        for _ in line_remarks
    ]
    db.execute(
        text("UPDATE sales_orders SET ship_info = :s, internal_note = :n WHERE id = :id"),
        {"s": ship_info, "n": note or f"Order Inquiry project: {MARKER} tower", "id": order.id},
    )
    for line, remark, heading in zip(lines, line_remarks, headings):
        db.execute(
            text("UPDATE sales_order_lines SET line_remark = :r, section_heading = :h "
                 "WHERE id = :id"),
            {"r": remark, "h": heading, "id": line.id},
        )
    return order, lines


def _board(db, order):
    company_id = _sorento(db)
    actor = _user(db, f"{MARKER} Eling")
    db.commit()
    client, originals = _client(db, actor, [VIEW])
    try:
        with company_scope(db, frozenset({company_id})):
            response = client.get(
                f"{BASE}/fulfilment-planning/board",
                params={"orders": order.so_number, "granularity": "week",
                        "as_of": TODAY.isoformat()},
            )
    finally:
        _restore(originals)
    assert response.status_code == 200, response.text
    return response.json()


def _mockup_by_line(body):
    return [c["is_mockup"] for c in body["contributions"]]


@pytest.mark.parametrize(
    "ship_info,expected",
    [
        ("SPONSORSHIP", "Sponsorship"),
        ("PURCHASE REQUEST", "Purchase Request"),
        ("PR26-0375", "Purchase Request"),
        ("PRR26-0120", None),
        (None, None),
    ],
)
def test_ac7_order_standing_carries_remark_type(ship_info, expected):
    with blank_session() as db:
        order, _lines = _world(db, ship_info=ship_info)

        body = _board(db, order)

        assert body["orders"][0]["remark_type"] == expected


def test_ac7_line_remark_marks_only_that_line_as_mockup():
    with blank_session() as db:
        order, _lines = _world(db, line_remarks=("***FOR STH(100)-2 UNITS MOCK UP", None))

        body = _board(db, order)

        assert sorted(_mockup_by_line(body)) == [False, True]


def test_ac7_section_heading_marks_the_lines_under_it():
    with blank_session() as db:
        order, _lines = _world(db, headings=("MOCK UP - BLOCK 1", "BLOCK 1 & 3 - JUL 27"))

        body = _board(db, order)

        assert sorted(_mockup_by_line(body)) == [False, True]


def test_ac7_note_mock_marks_every_line():
    with blank_session() as db:
        order, _lines = _world(db, note="***FOR MOCKUP")

        body = _board(db, order)

        assert _mockup_by_line(body) == [True, True]


def test_ac7_an_ordinary_order_has_no_mockup_line():
    with blank_session() as db:
        order, _lines = _world(db)

        body = _board(db, order)

        assert _mockup_by_line(body) == [False, False]
        for cell in body["cells"]:
            for contribution in cell["contributions"]:
                assert contribution["is_mockup"] is False


def test_ac7_the_cell_contributions_carry_is_mockup_too():
    with blank_session() as db:
        order, _lines = _world(db, line_remarks=("MOCK UP", None))

        body = _board(db, order)

        flags = sorted(c["is_mockup"] for cell in body["cells"] for c in cell["contributions"])
        assert flags == [False, True]
