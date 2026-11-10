"""PRICETAG-REQUEST-LAYOUT: one price tag request for several customers.

Owner ruling 10 Nov (mock v3, answer 1): one request holds N customers, one doc number, one
approval, one sheet (the printed tag carries no customer). Stored as
``price_tag_requests.customers`` (JSONB list of ``{code, name}``); the FIRST customer is mirrored
into ``debtor_code`` / ``debtor_name`` so every existing reader (list column, sort, search, SLA,
revision snapshot labels) keeps working unchanged.

Plan: documentation/plans/dealer-kit/PLAN-pricetag-request-layout-10nov.md.
Fixtures reuse ``tests/test_portal_price_tag_edit.py`` (Postgres, own seeded chain).
"""
from __future__ import annotations

from app.main import app  # noqa: F401,E402  (first app import, see test_portal_price_tag_edit)
from tests.test_portal_price_tag_edit import (  # noqa: F401  (fixture)
    _BASE,
    _create_draft,
    _seed_product,
    client,
)

_A = {"code": "ZZT-C1", "name": "ZZT Kitchen Gallery"}
_B = {"code": "ZZT-C2", "name": "ZZT Home Centre Kepong"}
_C = {"code": "ZZT-C3", "name": "ZZT Bath Studio"}


def test_create_with_several_customers_mirrors_the_first_into_debtor(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A, _B])

    assert created["customers"] == [_A, _B]
    assert created["debtor_code"] == _A["code"]
    assert created["debtor_name"] == _A["name"]

    reread = c.get(f"{_BASE}/{created['id']}").json()
    assert reread["customers"] == [_A, _B]


def test_update_replaces_the_customers_and_the_mirror_follows(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A, _B])

    res = c.put(f"{_BASE}/{created['id']}", json={"customers": [_C, _A]})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["customers"] == [_C, _A]
    assert body["debtor_code"] == _C["code"]
    assert body["debtor_name"] == _C["name"]


def test_a_repeated_customer_is_kept_once(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A, _B, dict(_A)])

    assert created["customers"] == [_A, _B]


def test_an_old_single_customer_request_reads_back_as_a_one_item_list(client):
    c, db, _ = client
    created = _create_draft(
        c, _seed_product(db), debtor_code=_A["code"], debtor_name=_A["name"]
    )

    assert created["customers"] == [_A]


def test_clearing_every_customer_blanks_the_mirror_and_submit_refuses(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A])

    res = c.put(f"{_BASE}/{created['id']}", json={"customers": []})
    assert res.status_code == 200, res.text
    assert res.json()["customers"] == []
    assert res.json()["debtor_name"] is None

    submit = c.post(f"{_BASE}/{created['id']}/submit")
    assert submit.status_code == 422, submit.text


def test_a_customer_without_a_name_is_refused(client):
    c, db, _ = client
    res = c.post(
        _BASE,
        json={
            "lines": [{"line_type": "product", "product_id": _seed_product(db)}],
            "customers": [{"code": "ZZT-X", "name": "  "}],
        },
    )
    assert res.status_code == 422, res.text


def test_list_carries_every_customer_and_search_finds_a_later_one(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A, _B])

    rows = c.get(_BASE, params={"q": "Home Centre Kepong"}).json()["items"]

    match = [r for r in rows if r["id"] == created["id"]]
    assert len(match) == 1
    assert match[0]["customers"] == [_A, _B]


def test_customers_is_a_revisable_header_field():
    from app.services.portal_service import PortalService

    assert "customers" in PortalService._editable_fields(None, "price_tag_request")
