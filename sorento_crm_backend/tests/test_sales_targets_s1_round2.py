"""S1 fix lane round 2: the owner's hand test of 27 Sep (PR #1297).

- F1: Applies to gains a fourth choice, Brand (one or more brands); the achievement counts only
  the lines whose product carries one of the brands.
- F5: every scope item a reader gets carries a human label (code and name) and its kind, never
  an id in place of a name, so the record's multi-selects can show names in read and edit mode.
- F6: a target needs both a start and an end date; a half-empty range is refused in plain words.

Seeds and fixtures are the S1 file's (`test_sales_targets_s1.py`).
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal

from .test_sales_targets_s1 import (  # noqa: F401  (fixtures)
    BASE,
    TEAMS_BASE,
    _agent,
    _category,
    _product,
    _so_line,
    _uid,
    api,
    world,
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _brand(db, company_id, name="ZZT Brand"):
    from app.models.product import Brand

    row = Brand(
        id=_uid(), company_id=company_id, brand_code=f"ZB{_uid()[:6]}".upper(), brand_name=name,
    )
    db.add(row)
    db.flush()
    return row


def _branded_product(db, company_id, category_id, brand_id):
    product = _product(db, company_id, category_id)
    product.brand_id = brand_id
    db.flush()
    return product


def _agent_payload(agent_id, **extra):
    return {
        "subject_kind": "agent", "sales_agent_id": agent_id, "name": "ZZT Brand target",
        "metric": "amount", "basis": "ordered", "start_date": "2026-10-01",
        "end_date": "2026-10-31", "target_value": 0, **extra,
    }


# --------------------------------------------------------------------------------------- #
# F1: Brand
# --------------------------------------------------------------------------------------- #


def test_brand_scope_counts_only_the_brands_products(api):
    client, db, company_id = api
    a = _agent(db, "A")
    category = _category(db, company_id)
    mocha = _brand(db, company_id, "ZZT Mocha")
    tp = _brand(db, company_id, "ZZT TP")
    other = _brand(db, company_id, "ZZT Other")
    p_mocha = _branded_product(db, company_id, category.id, mocha.id)
    p_tp = _branded_product(db, company_id, category.id, tp.id)
    p_other = _branded_product(db, company_id, category.id, other.id)
    p_none = _product(db, company_id, category.id)

    _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 5), line_total=Decimal("100"), product_id=p_mocha.id)
    _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 6), line_total=Decimal("40"), product_id=p_tp.id)
    _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 7), line_total=Decimal("999"), product_id=p_other.id)
    _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 8), line_total=Decimal("7"), product_id=p_none.id)

    one = client.post(BASE, json=_agent_payload(a.id, product_scope="brands", brand_ids=[mocha.id]))
    assert one.status_code == 201, one.text
    two = client.post(
        BASE, json=_agent_payload(a.id, product_scope="brands", brand_ids=[mocha.id, tp.id])
    )
    assert two.status_code == 201, two.text

    rows = client.get(BASE, params={"on": "2026-10-15", "subject": "agent"}).json()["rows"]
    by_id = {r["target_id"]: r for r in rows}
    assert by_id[one.json()["id"]]["achieved_value"] == 100  # Mocha only
    assert by_id[two.json()["id"]]["achieved_value"] == 140  # Mocha + TP, not Other, not unbranded
    assert by_id[one.json()["id"]]["product_scope"] == "brands"
    assert by_id[two.json()["id"]]["scope_labels"] == sorted(
        [f"{mocha.brand_code} - ZZT Mocha", f"{tp.brand_code} - ZZT TP"]
    )


def test_brand_scope_validation(api):
    client, db, company_id = api
    a = _agent(db, "A")
    category = _category(db, company_id)
    brand = _brand(db, company_id)
    product = _product(db, company_id, category.id)

    no_brand = client.post(BASE, json=_agent_payload(a.id, product_scope="brands"))
    assert no_brand.status_code == 422
    assert no_brand.json()["code"] == "INVALID_SCOPE"
    assert "brand" in no_brand.json()["message"].lower()

    mixed = client.post(
        BASE,
        json=_agent_payload(a.id, product_scope="brands", brand_ids=[brand.id], product_ids=[product.id]),
    )
    assert mixed.status_code == 422

    brand_on_products = client.post(
        BASE,
        json=_agent_payload(a.id, product_scope="products", product_ids=[product.id], brand_ids=[brand.id]),
    )
    assert brand_on_products.status_code == 422

    brand_on_all = client.post(BASE, json=_agent_payload(a.id, product_scope="all", brand_ids=[brand.id]))
    assert brand_on_all.status_code == 422

    unknown = client.post(
        BASE, json=_agent_payload(a.id, product_scope="brands", brand_ids=[str(uuid.uuid4())])
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "INVALID_SCOPE"

    not_uuid = client.post(BASE, json=_agent_payload(a.id, product_scope="brands", brand_ids=["x"]))
    assert not_uuid.status_code == 422


def test_patch_to_brand_scope_and_back(api):
    client, db, company_id = api
    a = _agent(db, "A")
    brand = _brand(db, company_id, "ZZT Mocha")
    target = client.post(BASE, json=_agent_payload(a.id, product_scope="all")).json()

    res = client.patch(f"{BASE}/{target['id']}", json={"product_scope": "brands", "brand_ids": [brand.id]})
    assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["product_scope"] == "brands"
    assert detail["scope"] == [
        {"id": brand.id, "kind": "brand", "label": f"{brand.brand_code} - ZZT Mocha"}
    ]

    back = client.patch(f"{BASE}/{target['id']}", json={"product_scope": "all"})
    assert back.status_code == 200, back.text
    assert back.json()["scope"] == []


def test_team_target_brand_scope_children_follow(api):
    client, db, company_id = api
    a = _agent(db, "A")
    b = _agent(db, "B")
    brand = _brand(db, company_id, "ZZT Mocha")
    category = _category(db, company_id)
    p_mocha = _branded_product(db, company_id, category.id, brand.id)
    p_plain = _product(db, company_id, category.id)
    team = client.post(TEAMS_BASE, json={"name": "ZZT North", "sales_agent_ids": [a.id, b.id]}).json()
    _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 5), line_total=Decimal("100"), product_id=p_mocha.id)
    _so_line(db, company_id, agent_id=b.id, order_date=date(2026, 10, 5), line_total=Decimal("30"), product_id=p_mocha.id)
    _so_line(db, company_id, agent_id=b.id, order_date=date(2026, 10, 5), line_total=Decimal("500"), product_id=p_plain.id)

    res = client.post(BASE, json={
        "subject_kind": "team", "sales_team_id": team["id"], "name": "ZZT Team Mocha",
        "metric": "amount", "basis": "ordered", "product_scope": "brands", "brand_ids": [brand.id],
        "start_date": "2026-10-01", "end_date": "2026-10-31",
        "agent_figures": [
            {"sales_agent_id": a.id, "target_value": 200},
            {"sales_agent_id": b.id, "target_value": 100},
        ],
    })
    assert res.status_code == 201, res.text
    detail = res.json()
    assert detail["periods"][0]["achieved_value"] == 130  # both agents' Mocha lines, not the plain one
    for child in detail["children"]:
        child_detail = client.get(f"{BASE}/{child['target_id']}").json()
        assert child_detail["product_scope"] == "brands"
        assert [s["id"] for s in child_detail["scope"]] == [brand.id]


def test_options_list_active_brands(api):
    client, db, company_id = api
    active = _brand(db, company_id, "ZZT Active brand")
    inactive = _brand(db, company_id, "ZZT Inactive brand")
    inactive.is_active = False
    db.flush()

    brands = client.get(f"{BASE}/options").json()["brands"]
    by_id = {b["id"]: b for b in brands}
    assert by_id[active.id]["label"] == f"{active.brand_code} - ZZT Active brand"
    assert inactive.id not in by_id


# --------------------------------------------------------------------------------------- #
# F5: scope items carry a human label and their kind, never an id in place of a name
# --------------------------------------------------------------------------------------- #


def test_scope_items_carry_kind_and_code_name_labels(api):
    client, db, company_id = api
    a = _agent(db, "A")
    category = _category(db, company_id, "ZZT Basins")
    product = _product(db, company_id, category.id)

    by_category = client.post(
        BASE, json=_agent_payload(a.id, product_scope="categories", category_ids=[category.id])
    ).json()
    assert by_category["scope"] == [
        {"id": category.id, "kind": "category", "label": f"{category.category_code} - ZZT Basins"}
    ]

    by_product = client.post(
        BASE, json=_agent_payload(a.id, product_scope="products", product_ids=[product.id])
    ).json()
    assert by_product["scope"] == [
        {"id": product.id, "kind": "product", "label": f"{product.product_code} - ZZT Product"}
    ]
    for item in by_category["scope"] + by_product["scope"]:
        assert not UUID_RE.search(item["label"]), item


# --------------------------------------------------------------------------------------- #
# F6: both dates required, in plain words
# --------------------------------------------------------------------------------------- #


def _plain_words(body: dict) -> str:
    """The text a person would read: the AppException message, or every validation msg."""
    if "message" in body:
        return body["message"]
    return " ".join(str(item.get("msg", "")) for item in body.get("detail", []))


def test_create_without_an_end_date_is_refused_in_plain_words(api):
    client, db, _ = api
    a = _agent(db, "A")
    for missing in ("start_date", "end_date"):
        payload = _agent_payload(a.id, product_scope="all")
        payload.pop(missing)
        res = client.post(BASE, json=payload)
        assert res.status_code == 422, res.text
        words = _plain_words(res.json())
        assert "start date and an end date" in words, words
        assert "_" not in words, words  # no snake_case a person reads

    payload = _agent_payload(a.id, product_scope="all", end_date=None)
    res = client.post(BASE, json=payload)
    assert res.status_code == 422, res.text
    assert "start date and an end date" in _plain_words(res.json())


def test_patch_clearing_a_date_is_refused_in_plain_words(api):
    client, db, _ = api
    a = _agent(db, "A")
    target = client.post(BASE, json=_agent_payload(a.id, product_scope="all")).json()
    for field in ("start_date", "end_date"):
        res = client.patch(f"{BASE}/{target['id']}", json={field: None})
        assert res.status_code == 422, res.text
        words = _plain_words(res.json())
        assert "start date and an end date" in words, words
        assert "_" not in words, words


def test_patch_null_messages_have_no_snake_case(api):
    client, db, _ = api
    a = _agent(db, "A")
    target = client.post(BASE, json=_agent_payload(a.id, product_scope="all")).json()
    for field in ("metric", "basis", "product_scope"):
        res = client.patch(f"{BASE}/{target['id']}", json={field: None})
        assert res.status_code == 422, res.text
        words = _plain_words(res.json())
        assert "product_scope" not in words and "_" not in words, words
