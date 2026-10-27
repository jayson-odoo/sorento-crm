"""SALES-UNIFIED S2: the Set-apart customers routes (AC-14 overlap and order, AC-15).

`GET|POST /api/v1/sales/set-apart-customers`, `PATCH|DELETE .../{id}` (contract section 6):
read `sales.reports.view`, write `sales.set_apart.edit`. List bodies use the house shape
`{"data": [...], "pagination": {...}}` (the contract names the row, not the envelope).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import company_scope, set_company_scope
from app.models.sales import SetApartCustomer
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import cust
from tests.test_sales_yearly_routes import SLUG, _client, _user

URL = "/api/v1/sales/set-apart-customers"
EDIT = "sales.set_apart.edit"
BOTH = (SLUG, EDIT)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        seed_mocha(s)
        yield s


def _row(db, customer, start, end=None, company_id=DEFAULT_COMPANY_ID) -> SetApartCustomer:
    row = SetApartCustomer(company_id=company_id, customer_id=customer.id, from_month=start, to_month=end)
    db.add(row)
    db.flush()
    return row


def _body(customer, start="2026-01", end=None):
    return {"customer_id": customer.id, "from_month": start, "to_month": end}


def _principal(db):
    return _user(db, DEFAULT_COMPANY_ID)


# ------------------------------------------------------------------------------ AC-15


def test_ac_15_no_token_is_401(db):
    with TestClient(app) as client:
        assert client.get(URL).status_code == 401
        assert client.post(URL, json=_body(cust(db))).status_code == 401


def test_ac_15_read_without_sales_reports_view_is_403(db):
    customer = cust(db)
    row = _row(db, customer, date(2026, 1, 1))
    with _client(db, _principal(db), allow=()) as client:
        assert client.get(URL).status_code == 403
    assert row.id


def test_ac_15_write_without_the_edit_slug_is_403_and_changes_nothing(db):
    customer = cust(db)
    row = _row(db, customer, date(2026, 1, 1))
    with _client(db, _principal(db), allow=(SLUG,)) as client:
        assert client.get(URL).status_code == 200
        assert client.post(URL, json=_body(cust(db))).status_code == 403
        assert client.patch(f"{URL}/{row.id}", json=_body(customer, "2026-02")).status_code == 403
        assert client.delete(f"{URL}/{row.id}").status_code == 403
    db.expire_all()
    assert db.get(SetApartCustomer, row.id).from_month == date(2026, 1, 1)


def test_ac_15_another_companys_rows_are_never_returned_or_editable(db):
    mine = _row(db, cust(db), date(2026, 1, 1))
    other_customer = cust(db, company_id=MOCHA_ID)
    theirs = _row(db, other_customer, date(2026, 1, 1), company_id=MOCHA_ID)
    with _client(db, _principal(db), allow=BOTH) as client:
        listed = client.get(URL).json()["data"]
        assert [r["id"] for r in listed] == [mine.id]
        assert client.patch(f"{URL}/{theirs.id}", json=_body(other_customer, "2026-03")).status_code == 404
        assert client.delete(f"{URL}/{theirs.id}").status_code == 404
    db.expire_all()
    with company_scope(db, None):
        assert db.get(SetApartCustomer, theirs.id).from_month == date(2026, 1, 1)


# ------------------------------------------------------------------------------ CRUD


def test_the_list_row_carries_the_debtor_code_the_name_and_year_month_strings(db):
    customer = cust(db, code="ZZT-D001", name="Zzt Trading One")
    _row(db, customer, date(2026, 1, 1), date(2026, 3, 1))
    _row(db, cust(db), date(2026, 5, 1), None)
    with _client(db, _principal(db), allow=(SLUG,)) as client:
        body = client.get(URL).json()
    first = next(r for r in body["data"] if r["customer_id"] == customer.id)
    assert {k: first[k] for k in ("debtor_code", "customer_name", "from_month", "to_month")} == {
        "debtor_code": "ZZT-D001", "customer_name": "Zzt Trading One",
        "from_month": "2026-01", "to_month": "2026-03"}
    assert any(r["to_month"] is None for r in body["data"])
    assert body["pagination"]["total"] == 2


def test_create_stores_the_first_of_the_month_and_returns_the_row(db):
    customer = cust(db, code="ZZT-D002")
    with _client(db, _principal(db), allow=BOTH) as client:
        created = client.post(URL, json=_body(customer, "2026-01", "2026-03"))
        assert created.status_code in (200, 201), created.text
        row = created.json()
        assert (row["customer_id"], row["debtor_code"], row["from_month"], row["to_month"]) == (
            customer.id, "ZZT-D002", "2026-01", "2026-03")
    stored = db.get(SetApartCustomer, row["id"])
    assert (stored.from_month, stored.to_month, stored.company_id) == (
        date(2026, 1, 1), date(2026, 3, 1), DEFAULT_COMPANY_ID)


@pytest.mark.parametrize("bad", [{"from_month": "2026-13"}, {"from_month": "January"},
                                 {"from_month": None}, {"customer_id": "not-a-uuid"}])
def test_create_rejects_a_malformed_body_with_422(db, bad):
    body = {**_body(cust(db)), **bad}
    with _client(db, _principal(db), allow=BOTH) as client:
        assert client.post(URL, json=body).status_code == 422


def test_patch_edits_the_months_and_delete_removes_the_row(db):
    customer = cust(db)
    row = _row(db, customer, date(2026, 1, 1))
    with _client(db, _principal(db), allow=BOTH) as client:
        patched = client.patch(f"{URL}/{row.id}", json=_body(customer, "2026-02", "2026-04"))
        assert patched.status_code == 200, patched.text
        assert (patched.json()["from_month"], patched.json()["to_month"]) == ("2026-02", "2026-04")
        assert client.patch(f"{URL}/{row.id}", json=_body(customer, "2026-02", "2026-04")).status_code == 200
        gone = client.delete(f"{URL}/{row.id}")
        assert gone.status_code in (200, 204), gone.text
        assert client.get(URL).json()["data"] == []
        assert client.delete(f"{URL}/{row.id}").status_code == 404


# ------------------------------------------------------------------------------ AC-14


def test_ac_14_to_month_before_from_month_is_422(db):
    customer = cust(db)
    with _client(db, _principal(db), allow=BOTH) as client:
        assert client.post(URL, json=_body(customer, "2026-03", "2026-02")).status_code == 422
        row = _row(db, customer, date(2026, 5, 1))
        assert client.patch(f"{URL}/{row.id}", json=_body(customer, "2026-05", "2026-04")).status_code == 422
        same = client.post(URL, json=_body(cust(db), "2026-03", "2026-03"))
        assert same.status_code in (200, 201), same.text


def test_ac_14_an_overlapping_row_for_the_same_customer_is_422_set_apart_overlap(db):
    customer = cust(db)
    _row(db, customer, date(2026, 2, 1), date(2026, 4, 1))
    with _client(db, _principal(db), allow=BOTH) as client:
        for start, end in (("2026-01", "2026-02"), ("2026-03", "2026-03"), ("2026-04", None),
                           ("2026-01", None), ("2026-02", "2026-04")):
            refused = client.post(URL, json=_body(customer, start, end))
            assert refused.status_code == 422, (start, end, refused.text)
            assert refused.json()["code"] == "set_apart_overlap"


def test_ac_14_neighbouring_months_other_customers_and_other_companies_do_not_overlap(db):
    customer = cust(db)
    _row(db, customer, date(2026, 2, 1), date(2026, 4, 1))
    other = cust(db)
    _row(db, other, date(2026, 2, 1), None)
    with _client(db, _principal(db), allow=BOTH) as client:
        assert client.post(URL, json=_body(customer, "2026-01", "2026-01")).status_code in (200, 201)
        assert client.post(URL, json=_body(customer, "2026-05", None)).status_code in (200, 201)
        assert client.post(URL, json=_body(cust(db), "2026-02", None)).status_code in (200, 201)


def test_ac_14_an_edit_that_runs_into_a_sibling_row_is_422_but_not_into_itself(db):
    customer = cust(db)
    first = _row(db, customer, date(2026, 1, 1), date(2026, 1, 1))
    _row(db, customer, date(2026, 3, 1), None)
    with _client(db, _principal(db), allow=BOTH) as client:
        assert client.patch(f"{URL}/{first.id}", json=_body(customer, "2026-01", "2026-02")).status_code == 200
        clash = client.patch(f"{URL}/{first.id}", json=_body(customer, "2026-01", "2026-03"))
        assert clash.status_code == 422 and clash.json()["code"] == "set_apart_overlap"


# ------------------------------------------------------------------------------ list sort


def _three(db):
    a = cust(db, code="ZZT-D30", name="Bravo Trading")
    b = cust(db, code="ZZT-D10", name="Charlie Trading")
    c = cust(db, code="ZZT-D20", name="Alpha Trading")
    _row(db, a, date(2026, 2, 1), date(2026, 6, 1))
    _row(db, b, date(2026, 1, 1), date(2026, 9, 1))
    _row(db, c, date(2026, 3, 1), date(2026, 4, 1))
    return a, b, c


@pytest.mark.parametrize("key, field, expected", [
    ("debtor_code", "debtor_code", ["ZZT-D10", "ZZT-D20", "ZZT-D30"]),
    ("customer_name", "customer_name", ["Alpha Trading", "Bravo Trading", "Charlie Trading"]),
    ("from_month", "from_month", ["2026-01", "2026-02", "2026-03"]),
    ("to_month", "to_month", ["2026-04", "2026-06", "2026-09"]),
])
def test_the_list_sorts_server_side_on_every_column_both_ways(db, key, field, expected):
    _three(db)
    with _client(db, _principal(db), allow=(SLUG,)) as client:
        asc = client.get(URL, params={"sort": key, "dir": "asc"})
        desc = client.get(URL, params={"sort": key, "dir": "desc"})
    assert [r[field] for r in asc.json()["data"]] == expected
    assert [r[field] for r in desc.json()["data"]] == expected[::-1]


def test_an_unknown_sort_key_is_422(db):
    with _client(db, _principal(db), allow=(SLUG,)) as client:
        assert client.get(URL, params={"sort": "created_at"}).status_code == 422


def test_the_list_pages_and_searches_by_code_or_name(db):
    _three(db)
    with _client(db, _principal(db), allow=(SLUG,)) as client:
        page = client.get(URL, params={"sort": "debtor_code", "dir": "asc", "page": 2, "limit": 2}).json()
        assert [r["debtor_code"] for r in page["data"]] == ["ZZT-D30"]
        assert page["pagination"]["total"] == 3
        by_name = client.get(URL, params={"query": "charlie"}).json()["data"]
        assert [r["customer_name"] for r in by_name] == ["Charlie Trading"]
        by_code = client.get(URL, params={"query": "D20"}).json()["data"]
        assert [r["debtor_code"] for r in by_code] == ["ZZT-D20"]
