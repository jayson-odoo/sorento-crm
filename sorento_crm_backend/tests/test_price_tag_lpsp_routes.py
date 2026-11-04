"""PRICETAG-LPSP S2 over the wire: the portal routes carry the line's price type.

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md, AC-1, AC-2, AC-3, AC-5.

Written test-FIRST (PRINCIPLES.md Phase 2). `response_model` silently drops what it does not
declare, so every field is asserted ON THE WIRE. Same harness as `tests/test_product_tag_templates.py`.
"""
from __future__ import annotations

from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    PORTAL,
    PTAG,
    _draft,
    _product,
    _reference,
    env,
)


def _post(c, lines, price_mode="list"):
    return c.post(
        PTAG,
        json={"debtor_name": "ZZT Dealer", "debtor_code": "ZZT-D", "print_by": "office",
              "price_mode": price_mode, "lines": lines},
    )


def test_create_stores_and_returns_each_lines_type(env):
    db, c, _ = env
    ref = _reference(db)
    a, b = _product(db, ref), _product(db, ref)
    res = _post(
        c,
        [
            {"line_type": "product", "product_id": a, "price_type": "list"},
            {"line_type": "product", "product_id": b, "price_type": "selling",
             "manual_sell_price": "599.00"},
        ],
    )
    assert res.status_code == 201, res.text
    lines = res.json()["lines"]
    assert [l["price_type"] for l in lines] == ["list", "selling"]
    assert [l["show_promo_price"] for l in lines] == [False, True]
    assert lines[1]["manual_sell_price"] == "599.00" or float(lines[1]["manual_sell_price"]) == 599.0

    again = c.get(f"{PTAG}/{res.json()['id']}").json()
    assert [l["price_type"] for l in again["lines"]] == ["list", "selling"]


def test_a_line_with_no_type_is_stored_with_the_requests_mode(env):
    db, c, _ = env
    ref = _reference(db)
    a = _product(db, ref)
    for mode in ("list", "selling"):
        body = _post(c, [{"line_type": "product", "product_id": _product(db, ref)}], mode).json()
        assert body["lines"][0]["price_type"] == mode
    assert a


def test_manual_price_on_an_lp_line_is_422_invalid_line_price(env):
    db, c, _ = env
    ref = _reference(db)
    a = _product(db, ref)
    res = _post(
        c,
        [{"line_type": "product", "product_id": a, "price_type": "list",
          "manual_sell_price": "599.00"}],
        "selling",
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "INVALID_LINE_PRICE"


def test_manual_price_on_an_sp_line_of_a_list_request_is_accepted(env):
    db, c, _ = env
    ref = _reference(db)
    a = _product(db, ref)
    res = _post(
        c,
        [{"line_type": "product", "product_id": a, "price_type": "selling",
          "manual_sell_price": "599.00"}],
        "list",
    )
    assert res.status_code == 201, res.text


def test_an_unknown_price_type_is_422(env):
    db, c, _ = env
    ref = _reference(db)
    a = _product(db, ref)
    res = _post(c, [{"line_type": "product", "product_id": a, "price_type": "bogus"}])
    assert res.status_code == 422


def test_update_replaces_the_types(env):
    db, c, _ = env
    ref = _reference(db)
    a = _product(db, ref)
    body = _draft(c, [{"line_type": "product", "product_id": a, "price_type": "list"}])
    res = c.put(
        f"{PTAG}/{body['id']}",
        json={"lines": [{"line_type": "product", "product_id": a, "price_type": "selling",
                         "manual_sell_price": "480.00"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["lines"][0]["price_type"] == "selling"
    assert res.json()["lines"][0]["show_promo_price"] is True


def test_preview_of_unsaved_lines_honours_each_lines_type(env):
    db, c, _ = env
    ref = _reference(db)
    a, b = _product(db, ref), _product(db, ref)
    res = c.post(
        f"{PORTAL}/lookups/tag-preview",
        json={
            "price_mode": "list",
            "lines": [
                {"key": "k1", "line_type": "product", "product_id": a, "price_type": "list"},
                {"key": "k2", "line_type": "product", "product_id": b, "price_type": "selling",
                 "manual_sell_price": "599.00"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    rows = {row["line_id"]: row for row in res.json()["lines"]}
    assert rows["k1"]["show_promo_price"] is False
    assert rows["k2"]["show_promo_price"] is True
    assert float(rows["k2"]["sell_price"]) == 599.0


def test_preview_of_a_saved_request_honours_each_lines_type(env):
    from app.models.price_tag import PriceTagRequestLine

    db, c, _ = env
    ref = _reference(db)
    a, b = _product(db, ref), _product(db, ref)
    body = _post(
        c,
        [
            {"line_type": "product", "product_id": a, "price_type": "list"},
            {"line_type": "product", "product_id": b, "price_type": "selling",
             "manual_sell_price": "599.00"},
        ],
    ).json()
    ids = {
        l.product_id: l.id
        for l in db.query(PriceTagRequestLine).filter_by(request_id=body["id"]).all()
    }
    res = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": body["id"]})
    assert res.status_code == 200, res.text
    rows = {row["line_id"]: row for row in res.json()["lines"]}
    assert rows[ids[a]]["show_promo_price"] is False
    assert rows[ids[b]]["show_promo_price"] is True
