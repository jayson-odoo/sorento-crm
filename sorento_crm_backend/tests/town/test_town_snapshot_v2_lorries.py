"""TOWN-V2 Q6 (owner, 10 Nov ~16:10): lorries drive to the real customers of sales orders due today or
overdue. `deliveries.customers` lists up to 6 of them, earliest due first, as the key of their shop in
the town, or None when the customer has no shop there (that lorry drives out of town). Never a
customer id the town does not already show; the redacted and wallboard variants carry the opaque key.
"""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from app.main import app  # noqa: F401

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust, so
from tests.town._town_seed import DAY, NOW, D, dealer_doc, fake_full


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _build(db):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, DEFAULT_COMPANY_ID, DAY, now=NOW)


def _due(db, customer, required):
    header, (line,) = so(db, customer=customer)
    line.qty_ordered, line.qty_delivered, line.line_status, line.required_date = D(5), D(0), "open", required
    db.flush()
    return header


def test_customers_are_shop_keys_earliest_due_first_none_when_not_in_town(db):
    shop_a, shop_c, far_b = cust(db), cust(db), cust(db)
    dealer_doc(db, shop_a, "100.00", DAY)  # invoiced today: a stall in the town
    dealer_doc(db, shop_c, "100.00", DAY)
    _due(db, shop_a, DAY - timedelta(days=5))
    _due(db, shop_a, DAY)  # a second order: the customer appears once
    _due(db, far_b, DAY - timedelta(days=3))  # no shop in the town
    _due(db, shop_c, DAY - timedelta(days=1))
    _due(db, None, DAY - timedelta(days=9))  # no customer: counted, not listed
    out = _build(db)
    keys = {s["key"] for s in out["shops"]}
    assert str(shop_a.id) in keys and str(shop_c.id) in keys and str(far_b.id) not in keys
    assert out["deliveries"]["to_deliver"] == 5
    assert out["deliveries"]["customers"] == [str(shop_a.id), None, str(shop_c.id)]


def test_customers_cap_at_six(db):
    for k in range(8):
        _due(db, cust(db), DAY - timedelta(days=k))
    out = _build(db)
    assert out["deliveries"]["to_deliver"] == 8
    assert out["deliveries"]["customers"] == [None] * 6


def test_customers_empty_when_nothing_due(db):
    assert _build(db)["deliveries"] == {"to_deliver": 0, "customers": []}


@pytest.mark.parametrize("fn_name", ["redact", "strip_names"])
def test_variants_map_customers_to_the_opaque_shop_key(fn_name):
    from app.services.town import snapshot as mod

    full = fake_full()
    first, third = full["shops"][0]["key"], full["shops"][2]["key"]  # rank-1 shop (3 docs), the stall (1 doc)
    full["deliveries"] = {"to_deliver": 4, "customers": [third, None, first]}
    before = copy.deepcopy(full)
    out = getattr(mod, fn_name)(full)
    shops = {s["key"]: s for s in out["shops"]}
    mapped = out["deliveries"]["customers"]
    assert out["deliveries"]["to_deliver"] == 4
    assert mapped[1] is None
    assert shops[mapped[0]]["kind"] == "stall"  # the same shop, under its opaque key
    assert shops[mapped[2]]["kind"] == "shop" and shops[mapped[2]]["today_docs"] == 3
    assert first not in mapped and third not in mapped  # no customer id leaks
    assert full == before  # input not mutated
