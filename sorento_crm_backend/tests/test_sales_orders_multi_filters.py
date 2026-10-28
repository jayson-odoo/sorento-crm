"""FILTER-MULTISELECT PR3: the Sales orders list's Status, Priority, Source, Type, Customer and Agent
filters take several values (OR within a filter, AND across). Source keeps its "manual" pseudo-value
(everything neither feed wrote) and it OR-combines with a real source. Red first; Postgres only;
rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.order import Customer, SalesOrder
from app.models.sales_agent import SalesAgent
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LIST = "/api/v1/scm/sales-orders"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _customer(db, label):
    row = Customer(id=str(uuid.uuid4()), customer_code=unique_code(label), customer_name=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


def _agent(db, label):
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=unique_code(label), description=f"ZZT {label}", is_active=True)
    db.add(row)
    db.flush()
    return row


def _so(db, tag, label, **kw):
    row = SalesOrder(id=str(uuid.uuid4()), so_number=f"{tag}-{label}", status=kw.pop("status", "open"),
                     order_date=date(2026, 6, 1), **kw)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(db):
    tag = unique_code("SO", alpha=True)
    c1, c2, c3 = _customer(db, "c1"), _customer(db, "c2"), _customer(db, "c3")
    a1, a2, a3 = _agent(db, "a1"), _agent(db, "a2"), _agent(db, "a3")
    return dict(
        tag=tag, c=(c1, c2, c3), a=(a1, a2, a3),
        r1=_so(db, tag, "1", status="open", priority="high", source_system="autocount", demand_class="project",
               customer_id=c1.id, sales_agent_id=a1.id),
        r2=_so(db, tag, "2", status="closed", priority="low", source_system="scm_order_inquiry", demand_class="retail",
               customer_id=c2.id, sales_agent_id=a2.id),
        r3=_so(db, tag, "3", status="cancelled", priority="normal", source_system=None, demand_class=None,
               customer_id=c3.id, sales_agent_id=a3.id),
        r4=_so(db, tag, "4", status="open", priority="low", source_system="scm_upload", demand_class="retail",
               customer_id=c1.id, sales_agent_id=a2.id),
    )


def _numbers(client, s, pairs):
    resp = get(client, LIST, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["so_number"] for r in resp.json()["data"]}


def _n(s, *keys):
    return {s[k].so_number for k in keys}


@pytest.mark.parametrize("param,union,expect,single,single_expect", [
    ("status", "open,closed", ("r1", "r2", "r4"), "cancelled", ("r3",)),
    ("priority", "high,low", ("r1", "r2", "r4"), "normal", ("r3",)),
    ("source", "autocount,inquiry", ("r1", "r2"), "upload", ("r4",)),
    ("demand_class", "project,retail", ("r1", "r2", "r4"), "project", ("r1",)),
])
def test_simple_filters_union_single_and_repeated(client, seeded, param, union, expect, single, single_expect):
    s = seeded
    assert _numbers(client, s, [(param, union)]) == _n(s, *expect)
    assert _numbers(client, s, [(param, single)]) == _n(s, *single_expect)
    a, b = union.split(",")
    assert _numbers(client, s, [(param, a), (param, b)]) == _n(s, *expect)


def test_source_manual_pseudo_value_or_combines_with_a_real_source(client, seeded):
    s = seeded
    # "manual" = neither feed wrote it: no source_system (r3) or an unknown one
    assert _numbers(client, s, [("source", "manual,autocount")]) == _n(s, "r1", "r3")


def test_type_unclassified_pseudo_value_or_combines_with_a_real_class(client, seeded):
    s = seeded
    assert _numbers(client, s, [("demand_class", "unclassified,project")]) == _n(s, "r1", "r3")


def test_unknown_values_still_match_nothing_beside_a_known_one(client, seeded):
    s = seeded
    assert _numbers(client, s, [("source", "autocount,nonsense")]) == _n(s, "r1")
    assert _numbers(client, s, [("demand_class", "project,nonsense")]) == _n(s, "r1")


def test_customer_union_single_and_repeated(client, seeded):
    s = seeded
    c1, c2, c3 = s["c"]
    assert _numbers(client, s, [("customer_code", f"{c2.customer_code},{c3.customer_code}")]) == _n(s, "r2", "r3")
    assert _numbers(client, s, [("customer_code", c1.customer_code)]) == _n(s, "r1", "r4")
    got = _numbers(client, s, [("customer_code", c2.customer_code), ("customer_code", c3.customer_code)])
    assert got == _n(s, "r2", "r3")


def test_agent_union_single_and_repeated(client, seeded):
    s = seeded
    a1, a2, a3 = s["a"]
    assert _numbers(client, s, [("sales_agent_id", f"{a1.id},{a3.id}")]) == _n(s, "r1", "r3")
    assert _numbers(client, s, [("sales_agent_id", a2.id)]) == _n(s, "r2", "r4")
    assert _numbers(client, s, [("sales_agent_id", a1.id), ("sales_agent_id", a3.id)]) == _n(s, "r1", "r3")


def test_filters_and_across_each_other(client, seeded):
    s = seeded
    got = _numbers(client, s, [("status", "open,closed"), ("priority", "low,high"),
                               ("sales_agent_id", f"{s['a'][1].id},{s['a'][2].id}")])
    assert got == _n(s, "r2", "r4")


def test_single_values_work_today(client, seeded):
    s = seeded
    assert _numbers(client, s, [("status", "cancelled")]) == _n(s, "r3")
    assert _numbers(client, s, [("priority", "normal")]) == _n(s, "r3")
    assert _numbers(client, s, [("source", "upload")]) == _n(s, "r4")
    assert _numbers(client, s, [("demand_class", "project")]) == _n(s, "r1")
    assert _numbers(client, s, [("customer_code", s["c"][2].customer_code)]) == _n(s, "r3")
    assert _numbers(client, s, [("sales_agent_id", s["a"][0].id)]) == _n(s, "r1")
