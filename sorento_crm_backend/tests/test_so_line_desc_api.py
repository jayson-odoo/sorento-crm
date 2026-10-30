"""SO-LINE-DESC API surface: the SO detail line (AC-4), the fulfilment board row (AC-5) and the
product tick (AC-7). A field the response model does not declare is dropped silently, so each is
asserted through the real route."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._multi_filter_client import open_client
from tests._pg_fixture import blank_session, unique_code
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401

from .test_so_remark_board import _board, _world
from .test_so_remark_so_page import _detail, _seed

PUSH = "SORENTO ACCESSORIES SRTWC8320-S150-UF PUSH BUTTON ONLY"
TAP = "CABANA ACCESSORIES - TAP HEAD ONLY FOR MODEL KT886SS-NL"
PRODUCTS = "/api/v1/master-data/products/"


# ------------------------------------------------------------------ AC-4 SO detail


@requires_pg
def test_ac4_the_so_detail_returns_each_lines_description_and_null_when_none(scm_app):
    app, so, ids = _seed(scm_app, lines=(None, None))
    db = scm_app[1]
    db.execute(
        text("UPDATE sales_order_lines SET description = :d WHERE id = :id"),
        {"d": PUSH, "id": ids[0]},
    )
    db.flush()

    body = _detail(app, so)

    by_id = {line["id"]: line for line in body["lines"]}
    assert by_id[ids[0]]["description"] == PUSH
    assert "description" in by_id[ids[1]] and by_id[ids[1]]["description"] is None


# ------------------------------------------------------------------ AC-5 fulfilment board


def _describe_lines(db, lines, descriptions):
    for line, description in zip(lines, descriptions):
        db.execute(
            text("UPDATE sales_order_lines SET description = :d WHERE id = :id"),
            {"d": description, "id": line.id},
        )


def test_ac5_each_board_row_carries_its_core_lines_description():
    with blank_session() as db:
        order, lines = _world(db)
        _describe_lines(db, lines, (PUSH, TAP))

        body = _board(db, order)

        assert sorted(c["description"] for c in body["contributions"]) == sorted([PUSH, TAP])
        cell_rows = [c for cell in body["cells"] for c in cell["contributions"]]
        assert sorted(c["description"] for c in cell_rows) == sorted([PUSH, TAP])


def test_ac5_a_line_without_a_description_is_null_not_missing():
    with blank_session() as db:
        order, lines = _world(db)
        _describe_lines(db, lines, (PUSH, None))

        body = _board(db, order)

        assert all("description" in c for c in body["contributions"])
        assert sorted(c["description"] or "" for c in body["contributions"]) == sorted([PUSH, ""])


# ------------------------------------------------------------------ AC-7 product tick


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _refs(db):
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="ZZT uom")
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("cat"), category_name="ZZT cat"
    )
    db.add_all([uom, cat])
    db.flush()
    return uom, cat


def _create_payload(db, **extra):
    uom, cat = _refs(db)
    return {
        "product_code": unique_code("RPACC", alpha=True), "product_name": "ZZT accessory",
        "category_id": cat.id, "base_uom_id": uom.id, "list_price": "1.00", **extra,
    }


def test_ac7_a_new_product_is_unticked_by_default(client, db):
    res = client.post(PRODUCTS, json=_create_payload(db))

    assert res.status_code == 201, res.text
    assert res.json()["show_so_line_description"] is False


def test_ac7_create_with_the_tick_persists_it_and_the_get_returns_it(client, db):
    res = client.post(PRODUCTS, json=_create_payload(db, show_so_line_description=True))

    assert res.status_code == 201, res.text
    assert res.json()["show_so_line_description"] is True
    got = client.get(f"{PRODUCTS}{res.json()['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["show_so_line_description"] is True


def test_ac7_update_flips_the_tick_and_an_update_without_it_leaves_it(client, db):
    created = client.post(PRODUCTS, json=_create_payload(db)).json()
    url = f"{PRODUCTS}{created['id']}"

    on = client.put(url, json={"show_so_line_description": True})
    assert on.status_code == 200, on.text
    assert on.json()["show_so_line_description"] is True

    renamed = client.put(url, json={"product_name": "ZZT accessory renamed"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["show_so_line_description"] is True

    off = client.put(url, json={"show_so_line_description": False})
    assert off.json()["show_so_line_description"] is False


def test_ac7_the_product_list_rows_carry_the_tick(client, db):
    created = client.post(
        PRODUCTS, json=_create_payload(db, show_so_line_description=True)
    ).json()

    res = client.get(PRODUCTS, params={"query": created["product_code"], "limit": 10})

    assert res.status_code == 200, res.text
    [row] = [r for r in res.json()["data"] if r["id"] == created["id"]]
    assert row["show_so_line_description"] is True
