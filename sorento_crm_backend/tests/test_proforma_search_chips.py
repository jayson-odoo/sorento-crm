"""SEARCH-CHIPS slice 2: the Proforma invoices list search takes several values (one repeated
`query` param per chip) and returns an invoice matching ANY of them, each value matched over the
list's existing search fields (PI number, supplier ref, container, BL, supplier name or code).
Same behaviour as slice 1, UAC `documentation/plans/ui/search-chips-acceptance-criteria.md`
B1-B6; plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.

Red first. Postgres only: every row is seeded here into a blank schema (`blank_session`) and
asserted through HTTP. Names are fake.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import Supplier
from app.models.scm import ProformaInvoice
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LIST = "/api/v1/scm/proforma-invoices"


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


def _pi(db, number, supplier, **kw):
    pi = ProformaInvoice(id=_u(), pi_number=number, supplier_id=supplier.id, **kw)
    db.add(pi)
    db.flush()
    return pi


@pytest.fixture
def seeded(db):
    tag = unique_code("PIC", alpha=True)
    plain = _supplier(db, f"{tag} Plain Supplier")
    acme_comma = _supplier(db, f"{tag} Acme, Trading")
    acme_only = _supplier(db, f"{tag} Acme Holdings")
    trading_only = _supplier(db, "Trading Bee Fakeco")
    s = dict(tag=tag)
    s["alpha"] = _pi(db, f"{tag}-ALPHA", plain)
    s["bravo"] = _pi(db, f"{tag}-BRAVO", plain)
    s["comma"] = _pi(db, f"{tag}-CHARLIE", acme_comma)
    s["acme_only"] = _pi(db, f"{tag}-DELTA", acme_only)
    s["trading_only"] = _pi(db, f"{tag}-ECHO", trading_only)
    s["by_container"] = _pi(db, f"{tag}-FOXTROT", plain, container_ref=f"{tag}CONTZZ1")
    s["by_bl"] = _pi(db, f"{tag}-GOLF", plain, bl_ref=f"{tag}BLZZ9")
    return s


def _q(*values):
    return [("query", v) for v in values]


def _list(client, pairs):
    resp = get(client, LIST, [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _numbers(body):
    return {r["pi_number"] for r in body["data"]}


def _n(s, *keys):
    return {s[k].pi_number for k in keys}


def test_repeated_query_returns_the_union(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].pi_number, s["bravo"].pi_number))
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["total"] == 2


def test_each_value_matched_over_number_container_bl_and_supplier(client, seeded):
    s, tag = seeded, seeded["tag"]
    body = _list(client, _q(s["alpha"].pi_number, f"{tag}CONTZZ1", f"{tag}BLZZ9", "Acme, Trading"))
    assert _numbers(body) == _n(s, "alpha", "by_container", "by_bl", "comma")


def test_single_query_behaves_as_today(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].pi_number))
    assert _numbers(body) == _n(s, "alpha")
    assert body["total"] == 1


def test_single_query_on_container_behaves_as_today(client, seeded):
    s = seeded
    assert _numbers(_list(client, _q(f"{s['tag']}CONTZZ1"))) == _n(s, "by_container")


def test_a_value_matching_nothing_adds_no_rows(client, seeded):
    s = seeded
    assert _numbers(_list(client, _q(s["alpha"].pi_number, "ZZNOTHINGMATCHESTHIS"))) == _n(s, "alpha")


def test_comma_inside_a_value_is_one_value(client, seeded):
    s = seeded
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _list(client, _q("Acme, Trading", s["alpha"].pi_number))
    assert _numbers(body) == _n(s, "comma", "alpha")


def test_blank_and_case_duplicate_values_are_ignored(client, seeded):
    s = seeded
    a = s["alpha"].pi_number
    body = _list(client, _q(a, "", "  ", a.lower(), s["bravo"].pi_number))
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["total"] == 2


def test_more_than_200_values_is_422(client, seeded):
    resp = get(client, LIST, _q(*[f"ZZV{i:03d}" for i in range(201)]))
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_exactly_200_values_is_accepted(client, seeded):
    s = seeded
    values = [s["bravo"].pi_number] + [f"ZZV{i:03d}" for i in range(199)]
    assert _numbers(_list(client, _q(*values))) == _n(s, "bravo")


def test_a_value_over_100_characters_is_422(client, seeded):
    resp = get(client, LIST, _q("PI1", "X" * 101))
    assert resp.status_code == 422, resp.text
    assert "100" in resp.text, resp.text


def test_a_value_of_exactly_100_characters_is_accepted(client, seeded):
    s = seeded
    resp = get(client, LIST, [("limit", 100), *_q(s["alpha"].pi_number, "Z" * 100)])
    assert resp.status_code == 200, resp.text
    assert _numbers(resp.json()) == _n(s, "alpha")
