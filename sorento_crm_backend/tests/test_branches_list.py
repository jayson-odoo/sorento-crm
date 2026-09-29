"""Customer Branches list (#1356): GET /order-management/branches, read only.

- the list needs `order_management.branches.view`;
- a branch names the CRM customer whose code matches its AccNo (trimmed, any case) in its own
  company; an unmatched AccNo carries no customer;
- search, Book and In CRM filters, sort;
- `customer_id` lists one customer's branches (the Customer detail Branches tab);
- another company's branch is not listed;
- no write route exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.base import company_scope

from ._pg_fixture import blank_session

BASE = "/api/v1/order-management/branches"
VIEW = "order_management.branches.view"


def _uid() -> str:
    return str(uuid.uuid4())


def _client(db, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user_id = _uid()
    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        with company_scope(db, frozenset({company_id})):
            yield db, company_id


def _api(world, permissions):
    db, company_id = world
    client, originals = _client(db, permissions)
    return client, originals


def _customer(db, company_id, code, name):
    from app.models.order import Customer

    row = Customer(id=_uid(), company_id=company_id, customer_code=code, customer_name=name)
    db.add(row)
    db.flush()
    return row


def _branch(db, company_id, acc_no, code, name, *, book="SRT", synced=datetime(2026, 9, 29, 6)):
    from app.models.autocount_branch import Branch

    row = Branch(
        id=_uid(), company_id=company_id, source_book=book, acc_no=acc_no, branch_code=code,
        branch_name=name, source_record={"BranchCode": code}, last_synced_at=synced,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(world):
    db, company_id = world
    kedai = _customer(db, company_id, "ZZT-300-K1", "ZZT Kedai Maju")
    _branch(db, company_id, "zzt-300-k1 ", "KL01", "Kepong Showroom")
    _branch(db, company_id, "ZZT-300-K1", "PJ02", "PJ Warehouse", synced=datetime(2026, 9, 28, 6))
    _branch(db, company_id, "ZZT-300-X9", "HQ", "Head Office", book="ZZB2")
    _branch(db, company_id, "", "PG", "Penang Depot", synced=datetime(2026, 9, 27, 6))
    return db, company_id, kedai


def _rows(res):
    assert res.status_code == 200, res.text
    return [r for r in res.json()["data"] if r["branch_name"] in {
        "Kepong Showroom", "PJ Warehouse", "Head Office", "Penang Depot"}]


def test_list_needs_view_permission(world, seeded):
    client, originals = _api(world, [])
    try:
        assert client.get(BASE).status_code == 403
        assert client.get(f"{BASE}/books").status_code == 403
    finally:
        _restore(originals)


def test_list_matches_customer_by_code_and_sorts_newest_first(world, seeded):
    _, _, kedai = seeded
    client, originals = _api(world, [VIEW])
    try:
        rows = _rows(client.get(BASE, params={"query": "ZZT", "limit": 100}))
        rows += _rows(client.get(BASE, params={"query": "Penang", "limit": 100}))
    finally:
        _restore(originals)
    by_name = {r["branch_name"]: r for r in rows}
    # Trimmed, case-insensitive match on the customer code.
    assert by_name["Kepong Showroom"]["customer_id"] == kedai.id
    assert by_name["Kepong Showroom"]["customer_name"] == "ZZT Kedai Maju"
    assert by_name["PJ Warehouse"]["customer_name"] == "ZZT Kedai Maju"
    # Unmatched and empty AccNo carry no customer.
    assert by_name["Head Office"]["customer_id"] is None
    assert by_name["Penang Depot"]["customer_id"] is None
    assert by_name["Penang Depot"]["acc_no"] == ""
    # Default sort: last synced, newest first.
    zzt = [r["branch_name"] for r in rows[:3]]
    assert zzt.index("Kepong Showroom") < zzt.index("PJ Warehouse")


def test_search_book_and_in_crm_filters(world, seeded):
    client, originals = _api(world, [VIEW])
    try:
        by_code = _rows(client.get(BASE, params={"query": "pj02"}))
        by_book = _rows(client.get(BASE, params={"book": "ZZB2"}))
        matched = _rows(client.get(BASE, params={"in_crm": "true", "query": "ZZT", "limit": 100}))
        unmatched = _rows(client.get(BASE, params={"in_crm": "false", "limit": 100}))
        books = client.get(f"{BASE}/books").json()
        by_code_sorted = _rows(client.get(BASE, params={"query": "ZZT", "sort": "branch_code", "dir": "asc"}))
    finally:
        _restore(originals)
    assert [r["branch_code"] for r in by_code] == ["PJ02"]
    assert [r["branch_code"] for r in by_book] == ["HQ"]
    assert {r["branch_code"] for r in matched} == {"KL01", "PJ02"}
    assert {"HQ", "PG"} <= {r["branch_code"] for r in unmatched}
    assert not {"KL01", "PJ02"} & {r["branch_code"] for r in unmatched}
    assert "ZZB2" in books and "SRT" in books
    assert [r["branch_code"] for r in by_code_sorted] == ["HQ", "KL01", "PJ02"]


def test_customer_id_lists_that_customers_branches(world, seeded):
    _, _, kedai = seeded
    client, originals = _api(world, [VIEW])
    try:
        res = client.get(BASE, params={"customer_id": kedai.id})
        missing = client.get(BASE, params={"customer_id": _uid()})
        bad = client.get(BASE, params={"customer_id": "not-a-uuid"})
    finally:
        _restore(originals)
    assert res.status_code == 200, res.text
    assert sorted(r["branch_code"] for r in res.json()["data"]) == ["KL01", "PJ02"]
    assert res.json()["pagination"]["total"] == 2
    assert missing.status_code == 404
    assert bad.status_code == 404


def test_another_companys_branch_is_not_listed(world, seeded):
    db, _, _ = seeded
    other = _uid()
    db.execute(
        text("insert into companies (id, code, name) values (:id, :code, 'ZZT Other')"),
        {"id": other, "code": f"Z{other[:6]}"},
    )
    with company_scope(db, None):
        _branch(db, other, "ZZT-300-K1", "OT1", "Other Company Branch")
    client, originals = _api(world, [VIEW])
    try:
        res = client.get(BASE, params={"query": "OT1"})
    finally:
        _restore(originals)
    assert res.status_code == 200, res.text
    assert res.json()["data"] == []


def test_no_write_route(world, seeded):
    client, originals = _api(world, ["order_management.branches.edit",
                                     "order_management.branches.delete",
                                     "order_management.branches.add", VIEW])
    try:
        assert client.post(BASE, json={}).status_code == 405
        some_id = client.get(BASE).json()["data"][0]["id"]
        assert client.delete(f"{BASE}/{some_id}").status_code in (404, 405)
        assert client.put(f"{BASE}/{some_id}", json={}).status_code in (404, 405)
    finally:
        _restore(originals)
