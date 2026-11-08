"""ASKS-UX item 4, owner ruling 30 Sep 2026 (option a): a customer-less ask names the TRADING
NAME behind the customers its contact is linked to, when they are the ledgers of one shop.

"HANLIM TRADING SDN BHD [A/C I]", "[A/C II]" and "(CERAMIC & ELLECI)" are one shop when the office
put them in one customer group (CUSTOMER-GROUP-GATE, owner ruling 3 Nov 2026: explicit links only),
so the card reads the group's name instead of the contact's; ungrouped, they are three customers.
One linked ledger reads its name without the ledger marker. Links to two different shops name nothing (the
card falls back to the contact, as before); an ask written against a customer is untouched.
"""
from __future__ import annotations

import pytest

from app.models.access import RespondContactCustomer
from app.models.base import set_company_scope
from app.services import stock_ask_service

from . import _ask_todo_seed as seed
from ._ask_todo_seed import SORENTO
from ._pg_fixture import blank_session


def _link(db, contact_id, customer):
    db.add(RespondContactCustomer(id=seed.uid(), contact_id=contact_id, customer_id=customer.id, company_id=SORENTO))
    db.flush()


@pytest.fixture
def w():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        world = seed.world(db)
        a = world["a"]
        world["h1"] = seed.customer(db, "HANLIM TRADING SDN BHD [A/C I]", a)
        world["h2"] = seed.customer(db, "HANLIM TRADING SDN BHD - [A/C II]", a)
        world["h3"] = seed.customer(db, "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)", a)
        world["other_shop"] = seed.customer(db, "CHIN CHUN HARDWARE SDN BHD", a)
        world["db"] = db
        db.commit()
        yield world


def _names(db, *asks) -> list[str | None]:
    return [r.customer_name for r in stock_ask_service.serialize(db, list(asks))]


def test_a_customerless_ask_names_the_group_when_every_link_is_one_group(w):
    from sqlalchemy import text

    db = w["db"]
    for c in (w["h1"], w["h2"], w["h3"]):
        _link(db, w["dealer"], c)
    ask = seed.ask(db, None, w["dealer"], "SRT-HANLIM")
    db.commit()
    # Ungrouped: three customers to the chatbot, so the card names none of them.
    assert _names(db, ask) == [None]
    gid = seed.uid()
    db.execute(
        text("INSERT INTO customer_groups (id, company_id, name, created_at, updated_at) VALUES (:i, :c, :n, now(), now())"),
        {"i": gid, "c": SORENTO, "n": "HANLIM TRADING SDN BHD"},
    )
    for c in (w["h1"], w["h2"], w["h3"]):
        db.execute(text("UPDATE customers SET customer_group_id = :g WHERE id = :c"), {"g": gid, "c": c.id})
    db.commit()
    assert _names(db, ask) == ["HANLIM TRADING SDN BHD"]
    # And on the wire: the agent's to-do carries the label on the same row.
    todo = stock_ask_service.todo_for_agent(db, w["a"].id)
    row = next(r for r in todo["open"] if r.id == str(ask.id))
    assert row.customer_name == "HANLIM TRADING SDN BHD" and row.contact_name == "Ah Seng"


def test_links_to_two_shops_name_nothing_and_a_customer_ask_is_untouched(w):
    db = w["db"]
    _link(db, w["dealer"], w["h1"])
    _link(db, w["dealer"], w["other_shop"])
    loose = seed.ask(db, None, w["dealer"], "SRT-TWO-SHOPS")
    against = seed.ask(db, w["h2"], w["dealer"], "SRT-AGAINST")
    unlinked = seed.ask(db, None, seed.contact(db, "Walk-in"), "SRT-NOBODY")
    db.commit()
    assert _names(db, loose, against, unlinked) == [None, "HANLIM TRADING SDN BHD - [A/C II]", None]


def test_a_single_link_names_that_shop(w):
    db = w["db"]
    _link(db, w["dealer"], w["h3"])
    ask = seed.ask(db, None, w["dealer"], "SRT-ONE")
    db.commit()
    assert _names(db, ask) == ["HANLIM TRADING SDN BHD"]
