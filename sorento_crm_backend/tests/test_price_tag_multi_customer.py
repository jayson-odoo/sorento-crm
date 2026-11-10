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

import pytest

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
    # The pair is set first, so only the mirror can blank it (review finding 4).
    created = _create_draft(
        c, _seed_product(db), debtor_code=_A["code"], debtor_name=_A["name"]
    )
    assert created["debtor_name"] == _A["name"]

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


def test_search_matches_customer_values_not_json_keys(client):
    c, db, _ = client
    created = _create_draft(c, _seed_product(db), customers=[_A, _B])

    rows = c.get(_BASE, params={"q": "name"}).json()["items"]

    assert created["id"] not in [r["id"] for r in rows]


def test_customers_is_a_revisable_header_field():
    from app.services.portal_service import PortalService

    assert "customers" in PortalService._editable_fields(None, "price_tag_request")


# ---------------------------------------------------------------------------
# Revise (review finding 1): the form sends `customers` on Submit revision.
# ---------------------------------------------------------------------------

from tests.test_portal_price_tag_revise import (  # noqa: E402,F401  (fixtures)
    _seed_token,
    _setup,
    db,
    no_queue,
)


def test_revise_stores_the_customers_and_mirrors_the_first(db):
    from app.services.portal_revision_service import PortalRevisionService
    from app.services.price_tag_request_service import PriceTagRequestService

    contact, product_id, row = _setup(db)
    PortalRevisionService(db).revise(
        _seed_token(contact),
        "price_tag_request",
        str(row.id),
        {
            "debtor_code": _A["code"],
            "debtor_name": _A["name"],
            "customers": [_B, _A, dict(_B)],
            "products": [{"product_id": product_id, "quantity": 2}],
        },
        "two customers",
        0,
    )
    db.expire_all()
    fresh = PriceTagRequestService.get_request(db, str(row.id))
    assert fresh.customers == [_B, _A]
    assert (fresh.debtor_code, fresh.debtor_name) == (_B["code"], _B["name"])


def test_revise_refuses_a_customer_without_a_name(db):
    from app.services.error_handler import AppException
    from app.services.portal_revision_service import PortalRevisionService

    contact, product_id, row = _setup(db)
    with pytest.raises(AppException) as refused:
        PortalRevisionService(db).revise(
            _seed_token(contact),
            "price_tag_request",
            str(row.id),
            {
                "customers": [{"code": "ZZT-X", "name": " "}],
                "products": [{"product_id": product_id, "quantity": 1}],
            },
            "blank",
            0,
        )
    # The portal's own validation refusal (`handle_validation_error`), same as every other
    # bad revise field.
    assert refused.value.status_code == 400


def test_revision_history_names_the_customers_once(db):
    """Review finding 2: the diff reads the customers by name, and not the mirrored pair too."""
    from app.services.portal_revision_service import PortalRevisionService, get_adapter

    service = PortalRevisionService(db)
    adapter = get_adapter("price_tag_request")
    previous = {"debtor_code": _A["code"], "debtor_name": _A["name"], "customers": None}
    current = {"debtor_code": _B["code"], "debtor_name": _B["name"], "customers": [_B, _A]}

    changes = [c for c in service._diff(adapter, previous, current) if c["field"] != "products"]

    assert changes == [
        {
            "field": "customers",
            "label": "Customers",
            "from": _A["name"],
            "to": f"{_B['name']}, {_A['name']}",
        }
    ]
    shown = {f["field"]: f["display"] for f in service._snapshot_fields(adapter, current)}
    assert shown["customers"] == f"{_B['name']}, {_A['name']}"
