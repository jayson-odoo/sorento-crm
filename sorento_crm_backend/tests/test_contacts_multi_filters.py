"""FILTER-MULTISELECT PR2 slice A: the contacts list's Access type, Tier and Customer filters take
several values (OR within a filter, AND across). Red first; Postgres only; every row seeded here.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import ContactAccessType, RespondContact, RespondContactCustomer
from app.models.order import Customer
from tests._multi_filter_client import SORENTO, get, open_client, ok_ids
from tests._pg_fixture import blank_session, unique_code

CONTACTS = "/api/v1/user-management/contacts/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _type(db):
    code = unique_code("zat")
    row = ContactAccessType(code=code, name=f"ZZT type {code}", is_active=True, sort_order=1)
    db.add(row)
    db.flush()
    return row


def _contact(db, tag, label, *, tier=None, types=()):
    profile = {"language": "en"}
    if tier is not None:
        profile["tier"] = tier
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"60{uuid.uuid4().int % 10**8 + 10**8}",
        name=f"ZZT {tag}-{label} {unique_code('c')}",
        chatbot_profile=profile,
    )
    db.add(row)
    db.flush()
    row.access_types = list(types)
    db.flush()
    return row


def _customer(db):
    row = Customer(customer_code=unique_code("ZZT-C"), customer_name="ZZT cust", company_id=SORENTO)
    db.add(row)
    db.flush()
    return row


def _link(db, contact, customer):
    db.add(RespondContactCustomer(contact_id=contact.id, customer_id=customer.id,
                                  company_id=customer.company_id, source="manual"))
    db.flush()


@pytest.fixture
def seeded(db):
    tag = unique_code("M", alpha=True)
    ta, tb, tc = _type(db), _type(db), _type(db)
    k1, k2, k3 = _customer(db), _customer(db), _customer(db)
    a = _contact(db, tag, "a", tier="dealer", types=[ta])
    b = _contact(db, tag, "b", tier="office", types=[tb])
    c = _contact(db, tag, "c", tier="end_user", types=[tc])
    d = _contact(db, tag, "d")  # no tier, no type
    _link(db, a, k1)
    _link(db, b, k2)
    _link(db, c, k3)
    return dict(tag=tag, ta=ta, tb=tb, tc=tc, k1=k1, k2=k2, k3=k3, a=a, b=b, c=c, d=d)


def _ids(client, tag, pairs):
    return ok_ids(get(client, CONTACTS, [("limit", 1000), ("query", tag), *pairs]))


def test_access_type_two_values_are_the_union(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], {"access_type": f"{s['ta'].code},{s['tb'].code}"}.items())
    assert got == {s["a"].id, s["b"].id}


def test_access_type_single_value_still_works(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("access_type", s["ta"].code)]) == {s["a"].id}


def test_access_type_repeated_param(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], [("access_type", s["ta"].code), ("access_type", s["tc"].code)])
    assert got == {s["a"].id, s["c"].id}


def test_tier_two_values_are_the_union(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("tier", "dealer,office")]) == {s["a"].id, s["b"].id}


def test_tier_none_combines_with_a_real_tier(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("tier", "none,end_user")]) == {s["c"].id, s["d"].id}


def test_tier_single_value_and_repeated(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("tier", "dealer")]) == {s["a"].id}
    assert _ids(client, s["tag"], [("tier", "dealer"), ("tier", "end_user")]) == {s["a"].id, s["c"].id}


def test_unknown_tier_is_422_as_before(client, seeded):
    assert get(client, CONTACTS, [("tier", "dealer,platinum")]).status_code == 422


def test_customer_two_values_are_the_union(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], [("customer_id", f"{s['k1'].id},{s['k2'].id}")])
    assert got == {s["a"].id, s["b"].id}


def test_customer_single_value_and_repeated(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("customer_id", s["k3"].id)]) == {s["c"].id}
    got = _ids(client, s["tag"], [("customer_id", s["k1"].id), ("customer_id", s["k3"].id)])
    assert got == {s["a"].id, s["c"].id}


def test_malformed_customer_id_is_422(client):
    assert get(client, CONTACTS, [("customer_id", "not-a-uuid")]).status_code == 422


def test_filters_and_across_each_other(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], [("tier", "dealer,office"), ("customer_id", f"{s['k2'].id},{s['k3'].id}")])
    assert got == {s["b"].id}
