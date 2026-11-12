"""SEARCH-CHIPS slice 2: the Purchase orders list search takes several values (one repeated `query`
param per chip) and returns an order matching ANY of them, each value matched over the list's
existing search fields (PO number, supplier name). Same behaviour as slice 1, UAC
`documentation/plans/ui/search-chips-acceptance-criteria.md` B1-B6; plan
`documentation/plans/ui/PLAN-search-chips-b-12nov.md`.

Red first. Postgres only: every row is seeded here into a blank schema (`blank_session`) and
asserted through HTTP. Names are fake.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import PurchaseOrder, Supplier
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LIST = "/api/v1/scm/purchase-orders"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _supplier(db, name):
    s = Supplier(id=_u(), supplier_code=unique_code("SUP", alpha=True), supplier_name=name)
    db.add(s)
    db.flush()
    return s


def _po(db, number, supplier=None, status="active"):
    po = PurchaseOrder(id=_u(), po_number=number, status=status,
                       supplier_id=supplier.id if supplier else None)
    db.add(po)
    db.flush()
    return po


@pytest.fixture
def seeded(db):
    tag = unique_code("POC", alpha=True)
    acme_comma = _supplier(db, f"{tag} Acme, Trading")
    acme_only = _supplier(db, f"{tag} Acme Holdings")
    trading_only = _supplier(db, "Trading Bee Fakeco")
    fakeco = _supplier(db, f"{tag} Fakeco Widgets")
    s = dict(tag=tag)
    s["alpha"] = _po(db, f"{tag}-ALPHA")
    s["bravo"] = _po(db, f"{tag}-BRAVO", status="closed")
    s["comma"] = _po(db, f"{tag}-CHARLIE", acme_comma)
    s["acme_only"] = _po(db, f"{tag}-DELTA", acme_only)
    s["trading_only"] = _po(db, f"{tag}-ECHO", trading_only)
    s["by_supplier"] = _po(db, f"{tag}-FOXTROT", fakeco)
    return s


def _q(*values):
    return [("query", v) for v in values]


def _list(client, pairs):
    resp = get(client, LIST, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _numbers(body):
    return {r["po_number"] for r in body["data"]}


def _n(s, *keys):
    return {s[k].po_number for k in keys}


def test_repeated_query_returns_the_union(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].po_number, s["bravo"].po_number))
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_each_value_matched_over_po_number_and_supplier_name(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].po_number, f"{s['tag']} Fakeco Widgets"))
    assert _numbers(body) == _n(s, "alpha", "by_supplier")


def test_single_query_behaves_as_today(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].po_number))
    assert _numbers(body) == _n(s, "alpha")
    assert body["pagination"]["total"] == 1


def test_single_query_on_supplier_name_behaves_as_today(client, seeded):
    s = seeded
    assert _numbers(_list(client, _q(f"{s['tag']} Fakeco Widgets"))) == _n(s, "by_supplier")


def test_a_value_matching_nothing_adds_no_rows(client, seeded):
    s = seeded
    assert _numbers(_list(client, _q(s["alpha"].po_number, "ZZNOTHINGMATCHESTHIS"))) == _n(s, "alpha")


def test_comma_inside_a_value_is_one_value(client, seeded):
    s = seeded
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _list(client, _q("Acme, Trading", s["alpha"].po_number))
    assert _numbers(body) == _n(s, "comma", "alpha")


def test_blank_and_case_duplicate_values_are_ignored(client, seeded):
    s = seeded
    a = s["alpha"].po_number
    body = _list(client, _q(a, "", "  ", a.lower(), s["bravo"].po_number))
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_values_and_with_a_status_filter(client, seeded):
    s = seeded
    body = _list(client, [*_q(s["alpha"].po_number, s["bravo"].po_number), ("status", "closed")])
    assert _numbers(body) == _n(s, "bravo")


def test_more_than_200_values_is_422(client, seeded):
    resp = get(client, LIST, _q(*[f"ZZV{i:03d}" for i in range(201)]))
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_exactly_200_values_is_accepted(client, seeded):
    s = seeded
    values = [s["bravo"].po_number] + [f"ZZV{i:03d}" for i in range(199)]
    assert _numbers(_list(client, _q(*values))) == _n(s, "bravo")


def test_a_value_over_100_characters_is_422(client, seeded):
    resp = get(client, LIST, _q("PO1", "X" * 101))
    assert resp.status_code == 422, resp.text
    assert "100" in resp.text, resp.text


def test_a_value_of_exactly_100_characters_is_accepted(client, seeded):
    s = seeded
    resp = get(client, LIST, [("limit", 200), *_q(s["alpha"].po_number, "Z" * 100)])
    assert resp.status_code == 200, resp.text
    assert _numbers(resp.json()) == _n(s, "alpha")
