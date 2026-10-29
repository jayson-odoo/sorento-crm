"""FILTER-MULTISELECT PR3: Delivery orders Status, Customers Group and Branches Book take several
values (OR within a filter). Customers Status stays a single Active / Inactive / Any control but the
backend now honours it. Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.autocount_branch import Branch
from app.models.order import Customer, CustomerGroup, Order, OrderStatus
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

ORDERS = "/api/v1/order-management/orders/"
CUSTOMERS = "/api/v1/order-management/customers/"
BRANCHES = "/api/v1/order-management/branches/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


# ---- Delivery orders: Status ------------------------------------------------------------------------

def _status(db, label):
    row = OrderStatus(id=str(uuid.uuid4()), status_code=unique_code(label), status_name=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def orders(db):
    s1, s2, s3 = _status(db, "s1"), _status(db, "s2"), _status(db, "s3")
    tag = unique_code("DO", alpha=True)
    rows = {}
    for key, st in (("a", s1), ("b", s2), ("c", s3), ("d", s1)):
        row = Order(id=str(uuid.uuid4()), order_number=f"{tag}-{key}", order_status_id=st.id)
        db.add(row)
        db.flush()
        rows[key] = row
    return dict(tag=tag, st=(s1, s2, s3), **rows)


def _orders(client, s, pairs):
    resp = get(client, ORDERS, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_order_status_union(client, orders):
    s = orders
    got = _orders(client, s, [("order_status_id", f"{s['st'][1].id},{s['st'][2].id}")])
    assert got == {s["b"].id, s["c"].id}


def test_order_status_single_and_repeated(client, orders):
    s = orders
    assert _orders(client, s, [("order_status_id", s["st"][0].id)]) == {s["a"].id, s["d"].id}
    got = _orders(client, s, [("order_status_id", s["st"][1].id), ("order_status_id", s["st"][2].id)])
    assert got == {s["b"].id, s["c"].id}


def test_order_status_accepts_codes_beside_ids(client, orders):
    s = orders
    got = _orders(client, s, [("order_status_id", f"{s['st'][1].status_code},{s['st'][2].id}")])
    assert got == {s["b"].id, s["c"].id}


# ---- Customers: Group (multi) and Status (single, honoured) ------------------------------------------

def _group(db, label):
    row = CustomerGroup(id=str(uuid.uuid4()), name=f"ZZT {label} {unique_code('g')}")
    db.add(row)
    db.flush()
    return row


def _customer(db, tag, label, group=None, active=True):
    row = Customer(id=str(uuid.uuid4()), customer_code=f"{tag}-{label}", customer_name=f"ZZT {tag} {label}",
                   customer_group_id=group.id if group else None, is_active=active)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def customers(db):
    tag = unique_code("CU", alpha=True)
    g1, g2, g3 = _group(db, "g1"), _group(db, "g2"), _group(db, "g3")
    return dict(
        tag=tag, g=(g1, g2, g3),
        a=_customer(db, tag, "a", g1, True), b=_customer(db, tag, "b", g2, False),
        c=_customer(db, tag, "c", g3, True), d=_customer(db, tag, "d", g1, False),
    )


def _custs(client, s, pairs):
    resp = get(client, CUSTOMERS, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_customer_group_union(client, customers):
    s = customers
    got = _custs(client, s, [("customer_group_id", f"{s['g'][1].id},{s['g'][2].id}")])
    assert got == {s["b"].id, s["c"].id}


def test_customer_group_single_and_repeated(client, customers):
    s = customers
    assert _custs(client, s, [("customer_group_id", s["g"][0].id)]) == {s["a"].id, s["d"].id}
    got = _custs(client, s, [("customer_group_id", s["g"][1].id), ("customer_group_id", s["g"][2].id)])
    assert got == {s["b"].id, s["c"].id}


def test_malformed_customer_group_id_is_422(client, customers):
    assert get(client, CUSTOMERS, [("customer_group_id", "not-a-uuid")]).status_code == 422
    s = customers
    assert get(client, CUSTOMERS, [("customer_group_id", f"{s['g'][0].id},not-a-uuid")]).status_code == 422


def test_customer_status_active_only(client, customers):
    s = customers
    assert _custs(client, s, [("status", "active")]) == {s["a"].id, s["c"].id}


def test_customer_status_inactive_only(client, customers):
    s = customers
    assert _custs(client, s, [("status", "inactive")]) == {s["b"].id, s["d"].id}


def test_customer_no_status_is_everyone(client, customers):
    s = customers
    assert _custs(client, s, []) == {s["a"].id, s["b"].id, s["c"].id, s["d"].id}


def test_customer_status_and_group_and_across(client, customers):
    s = customers
    got = _custs(client, s, [("status", "active"), ("customer_group_id", f"{s['g'][0].id},{s['g'][1].id}")])
    assert got == {s["a"].id}


# ---- Branches: Book ---------------------------------------------------------------------------------

def _branch(db, tag, label, book):
    row = Branch(id=str(uuid.uuid4()), source_book=book, branch_code=f"{tag}-{label}", branch_name=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def branches(db):
    tag = unique_code("BR", alpha=True)
    return dict(tag=tag, a=_branch(db, tag, "a", "SORENTO"), b=_branch(db, tag, "b", "MOCHA"),
                c=_branch(db, tag, "c", "OTHER"), d=_branch(db, tag, "d", "MOCHA"))


def _brs(client, s, pairs):
    resp = get(client, BRANCHES, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_branch_book_union(client, branches):
    s = branches
    assert _brs(client, s, [("book", "SORENTO,OTHER")]) == {s["a"].id, s["c"].id}


def test_branch_book_single_and_repeated(client, branches):
    s = branches
    assert _brs(client, s, [("book", "MOCHA")]) == {s["b"].id, s["d"].id}
    assert _brs(client, s, [("book", "SORENTO"), ("book", "OTHER")]) == {s["a"].id, s["c"].id}
