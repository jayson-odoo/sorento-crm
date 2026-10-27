"""ACCESS-SHEET-FIXES fix 5 (owner 27 Oct: "all the columns here must be sortable, all our system
columns should be sortable"): every Internal Users column sorts on the server through the list's
existing `sort` / `dir` params (the DataGrid sends the column id, `buildDataGridParams`).

Per column: two contacts whose cell values differ, asc puts one first and desc the other. An empty
cell sorts after every value in both directions, so a sort never opens on a page of blanks.
Postgres only (``blank_session``); the shared fixtures come from test_contacts_access_filters.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import ContactAccessType, ContactFieldReveal, ContactTag, respond_contact_tags
from app.models.order import Customer
from app.models.product import Brand
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests._pg_fixture import unique_code
from tests.test_contacts_access_filters import (  # noqa: F401 - fixtures
    CONTACTS,
    _contact,
    _grant,
    _link,
    client,
    db,
    perms,
    state,
)


def _ordered(client, tag, sort, direction):
    resp = client.get(CONTACTS, params={"limit": 1000, "query": tag, "sort": sort, "dir": direction})
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["data"]]


def _customer(db, code, company_id=DEFAULT_COMPANY_ID):
    row = Customer(customer_code=code, customer_name="ZZT cust", company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _types(db, contact, name):
    row = ContactAccessType(code=unique_code("zst"), name=name, is_active=True, sort_order=1)
    db.add(row)
    db.flush()
    contact.access_types = [row]
    db.flush()


def _tag(db, contact, name, settings=None):
    row = ContactTag(name=name, settings=settings or {})
    db.add(row)
    db.flush()
    db.execute(respond_contact_tags.insert().values(contact_id=contact.id, tag_id=row.id))
    db.flush()
    return row


def _brand(db, name):
    row = Brand(brand_code=unique_code("ZSB"), brand_name=name, is_active=True, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row.id


def _set(db, contact, **values):
    for k, v in values.items():
        setattr(contact, k, v)
    db.flush()


# Each seeder gets (db, lo, hi, state) and makes lo's cell sort before hi's.
def _seed_customers(db, lo, hi, state):
    _link(db, lo, _customer(db, unique_code("ZZT-A")))
    _link(db, hi, _customer(db, unique_code("ZZT-B")))


def _seed_access_types(db, lo, hi, state):
    _types(db, lo, "ZZT A type")
    _types(db, hi, "ZZT B type")


def _seed_tags(db, lo, hi, state):
    _tag(db, lo, "ZZT A tag")
    _tag(db, hi, "ZZT B tag")


def _seed_tag_settings(db, lo, hi, state):
    # "Differs" before "Matches" (the cell text), as the filter names them.
    settings = {"chatbot": {"chatbot_stock_allowed": False}}
    _set(db, lo, chatbot_stock_allowed=True)
    _set(db, hi, chatbot_stock_allowed=False)
    _tag(db, lo, "ZZT stock off", settings)
    _tag(db, hi, "ZZT stock off 2", settings)


def _seed_brands(db, lo, hi, state):
    _set(db, lo, brand_ids=[_brand(db, "ZZT A brand")])
    _set(db, hi, brand_ids=[_brand(db, "ZZT B brand")])


def _seed_tier(db, lo, hi, state):
    _set(db, lo, chatbot_profile={"language": "en", "tier": "dealer"})
    _set(db, hi, chatbot_profile={"language": "en", "tier": "office"})


def _seed_cost(db, lo, hi, state):
    db.add(ContactFieldReveal(respond_contact_id=hi.id, field_key="purchase_orders.cost", granted=True))
    db.flush()


def _flag(column):
    def seed(db, lo, hi, state):
        _set(db, lo, **{column: False})
        _set(db, hi, **{column: True})

    return seed


def _seed_regions(db, lo, hi, state):
    _set(db, lo, regions=["east"])
    _set(db, hi, regions=["west"])


def _seed_linked_user(db, lo, hi, state):
    for contact, name in ((lo, "ZZT A user"), (hi, "ZZT B user")):
        db.add(User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name=name,
                    respond_contact_id=contact.id))
    db.flush()


COLUMNS = {
    "customers": _seed_customers,
    "access_types": _seed_access_types,
    "tags": _seed_tags,
    "tag_settings": _seed_tag_settings,
    "brands": _seed_brands,
    "chatbot_tier": _seed_tier,
    "cost_visible": _seed_cost,
    "chatbot_allowed": _flag("chatbot_allowed"),
    "escalation_allowed": _flag("escalation_allowed"),
    "packing_list_allowed": _flag("packing_list_allowed"),
    "chatbot_stock_allowed": _flag("chatbot_stock_allowed"),
    "regions": _seed_regions,
    "outbound_enabled": _flag("outbound_enabled"),
    "linked_user": _seed_linked_user,
}


@pytest.mark.parametrize("column", sorted(COLUMNS))
def test_every_column_sorts_on_the_server_both_ways(client, db, state, perms, column):
    perms.add("user_management.users.view")  # the User column shows only with it
    tag = unique_code("O", alpha=True)
    # Names run against the expected order, so a fallback sort by name or creation fails the test.
    hi = _contact(db, tag, "a")
    lo = _contact(db, tag, "b")
    COLUMNS[column](db, lo, hi, state)
    assert _ordered(client, tag, column, "asc") == [lo.id, hi.id]
    assert _ordered(client, tag, column, "desc") == [hi.id, lo.id]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_an_empty_customers_cell_sorts_last_both_ways(client, db, direction):
    tag = unique_code("O", alpha=True)
    empty = _contact(db, tag, "a")
    one = _contact(db, tag, "b")
    _link(db, one, _customer(db, unique_code("ZZT-A")))
    assert _ordered(client, tag, "customers", direction) == [one.id, empty.id]


def test_brands_every_brand_sorts_as_its_own_group_first(client, db):
    tag = unique_code("O", alpha=True)
    narrowed = _contact(db, tag, "a")
    every = _contact(db, tag, "b")
    _set(db, narrowed, brand_ids=[_brand(db, "ZZT A brand")])
    assert _ordered(client, tag, "brands", "asc") == [every.id, narrowed.id]


def test_customers_sort_reads_the_granted_other_company_codes(client, db, state):
    tag = unique_code("O", alpha=True)
    mocha = _contact(db, tag, "a")
    sorento = _contact(db, tag, "b")
    _link(db, mocha, _customer(db, unique_code("ZZT-A"), company_id=MOCHA_ID))
    _link(db, sorento, _customer(db, unique_code("ZZT-B")))
    state["scope"] = frozenset({DEFAULT_COMPANY_ID})
    _grant(db, state["actor_id"], DEFAULT_COMPANY_ID, MOCHA_ID)
    assert _ordered(client, tag, "customers", "asc") == [mocha.id, sorento.id]
