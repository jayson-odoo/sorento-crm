"""RED tests - REPORT-SMART-L UAC AC11: `mine` on the sales report-ask route.

A salesperson (a role-user with role `salesperson` whose `users.respond_contact_id` is the contact)
asks for sales without the `sales_orders.sales_report` grant and gets their own book only: the
customers whose `customers.sales_agent_id` is a `sales_agents` row linked to the contact. With the
grant, `mine=true` narrows to the book and `mine` false is unscoped (today). Staff and unknown
contacts are never narrowed; a dealer keeps its own customer scope whatever `mine` says.
Postgres only; every row is seeded here (generic names).

World (September 2026, one fully delivered SO line per customer):
    in1  (book)    brand B1 cat C1  100.00 qty 1
    in2  (book)    brand B2 cat C2  200.00 qty 2
    out  (outside) brand B3 cat C3 1000.00 qty 10
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests._chat_asker_seed import give_role, link_agent, link_user
from tests._report_ask_so_seed import seed_so_line
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    _link,
    client,
    db,
    money,
    seed_agent,
    seed_customer,
)
from tests.test_report_ask_route import _brand, _category, _prod

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
OUT_NAMES = {"ZZT Outside Customer"}
BOOK_TOTAL = D("300.00")
ALL_TOTAL = D("1300.00")

MINE = [None, False, True]


def _world(db):
    other = seed_agent(db, code="ZZT Other Agent")
    w = SimpleNamespace()
    w.in1 = seed_customer(db, name="ZZT Book Customer One")
    w.in2 = seed_customer(db, name="ZZT Book Customer Two")
    w.out = seed_customer(db, name="ZZT Outside Customer")
    rows = [(w.in1, "1", 1, "100.00"), (w.in2, "2", 2, "200.00"), (w.out, "3", 10, "1000.00")]
    for cust, n, qty, total in rows:
        prod = _prod(db, f"ZZTMS-{n}", brand=_brand(db, f"ZZT Brand {n}"), category=_category(db, f"ZZT Cat {n}"))
        seed_so_line(db, cust=cust, prod=prod, qty=qty, total=total, agent=other)
    db.flush()
    return w


def _salesperson(db, w, *, granted: bool, agent: bool = True):
    contact = _contact(db, granted=granted)
    give_role(db, link_user(db, contact), "salesperson")
    if agent:
        book = link_agent(db, contact, "ZZT Book Agent")
        w.in1.sales_agent_id = book.id
        w.in2.sales_agent_id = book.id
    db.commit()
    return contact


def _ask(client, contact, **params):
    q = {**PERIOD, "basis": "delivered", "measure": "amount", **_as_contact(contact), **params}
    return client.get(ROUTE, params={k: v for k, v in q.items() if v is not None}, headers=KEY)


def _ok(client, contact, **params):
    resp = _ask(client, contact, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _total(body):
    return money(body["total"]["amount"])


def _names(body):
    return {r["name"] for r in body["rows"]}


def _refused(resp, codes=("sales_report_not_enabled", "report_dimension_not_allowed")):
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("code") in codes, body
    assert not body.get("rows"), body



# ------------------------------------------------------------------ 1. salesperson, no grant


@pytest.mark.parametrize("mine", MINE)
@pytest.mark.parametrize("group_by", [None, "customer", "product", "brand", "category", "month"])
def test_a_salesperson_without_the_grant_sees_only_their_book(client, db, mine, group_by):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    body = _ok(client, contact, group_by=group_by, top_n=10 if group_by else None, mine=mine)
    assert _total(body) == BOOK_TOTAL, body
    assert not any("Outside" in n or "Brand 3" in n or "Cat 3" in n or "MS-3" in n for n in _names(body)), body["rows"]
    if group_by:
        assert len(body["rows"]) == (1 if group_by == "month" else 2), body["rows"]


def test_a_salesperson_without_the_grant_ranks_the_book_customers_by_name(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by="customer", top_n=10, mine=True)
    assert _names(body) == {w.in1.customer_name, w.in2.customer_name}, body["rows"]


# ------------------------------------------------------------------ 2. salesperson, no grant, agent axes refused


@pytest.mark.parametrize("mine", MINE)
def test_a_salesperson_without_the_grant_may_not_rank_by_sales_agent(client, db, mine):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    _refused(_ask(client, contact, group_by="sales_agent", top_n=10, mine=mine))


@pytest.mark.parametrize("param", ["sales_agent_ids", "customer_agent_ids"])
@pytest.mark.parametrize("mine", MINE)
def test_a_salesperson_without_the_grant_may_not_filter_by_agent(client, db, param, mine):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    agent = seed_agent(db, code="ZZT Any Agent")
    db.commit()
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine, **{param: [agent.id]}))


# ------------------------------------------------------------------ 3. salesperson with the grant


def test_a_granted_salesperson_with_mine_true_is_narrowed_to_the_book(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by="customer", top_n=10, mine=True)
    assert _total(body) == BOOK_TOTAL and _names(body) == {w.in1.customer_name, w.in2.customer_name}, body


def test_a_granted_salesperson_with_mine_false_is_unscoped(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by="customer", top_n=10, mine=False)
    assert _total(body) == ALL_TOTAL and w.out.customer_name in _names(body), body


def test_a_granted_salesperson_without_the_param_is_unscoped_today(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by="customer", top_n=10)
    assert _total(body) == ALL_TOTAL and w.out.customer_name in _names(body), body


def test_a_granted_salesperson_with_mine_may_still_rank_by_sales_agent(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by="sales_agent", top_n=10, mine=True)
    assert body["status"] == "ok" and _total(body) == BOOK_TOTAL, body


# ------------------------------------------------------------------ 4. staff, granted


@pytest.mark.parametrize("mine", [None, True])
def test_a_granted_staff_contact_is_unscoped_whatever_mine_says(client, db, mine):
    w = _world(db)
    contact = _contact(db, granted=True)
    link_user(db, contact)
    db.commit()
    body = _ok(client, contact, group_by="customer", top_n=10, mine=mine)
    assert _total(body) == ALL_TOTAL and w.out.customer_name in _names(body), body


# ------------------------------------------------------------------ 5. dealer, granted


@pytest.mark.parametrize("mine", [None, False, True])
def test_a_dealer_stays_on_its_own_customers_whatever_mine_says(client, db, mine):
    w = _world(db)
    contact = _contact(db, granted=True)
    _link(db, contact, w.in1)
    db.commit()
    body = _ok(client, contact, group_by="brand", top_n=10, mine=mine)
    assert _total(body) == D("100.00") and len(body["rows"]) == 1, body


@pytest.mark.parametrize("mine", [None, True])
def test_a_dealer_may_not_rank_by_sales_agent(client, db, mine):
    w = _world(db)
    contact = _contact(db, granted=True)
    _link(db, contact, w.in1)
    db.commit()
    resp = _ask(client, contact, group_by="sales_agent", top_n=10, mine=mine)
    _refused(resp, codes=("report_dimension_not_allowed",))


# ------------------------------------------------------------------ 6 and 7. nobody to narrow to


@pytest.mark.parametrize("mine", [None, True])
def test_an_unknown_contact_without_the_grant_is_refused(client, db, mine):
    _world(db)
    contact = _contact(db, granted=False)
    db.commit()
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine), codes=("sales_report_not_enabled",))


@pytest.mark.parametrize("mine", [None, True])
def test_a_salesperson_without_an_agent_link_and_no_grant_is_refused(client, db, mine):
    w = _world(db)
    contact = _salesperson(db, w, granted=False, agent=False)
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine))


# ------------------------------------------------------------------ 8. security: the no-grant book needs a LIVE salesperson user


def _agent_link_only(db, w, *, user_status=None, trashed=False):
    contact = _contact(db, granted=False)
    if user_status is not None:
        give_role(db, link_user(db, contact, status=user_status, trashed=trashed), "salesperson")
    book = link_agent(db, contact, "ZZT Book Agent")
    w.in1.sales_agent_id = book.id
    w.in2.sales_agent_id = book.id
    db.commit()
    return contact


@pytest.mark.parametrize("mine", [None, True])
def test_an_agent_link_without_a_crm_user_and_no_grant_is_refused(client, db, mine):
    w = _world(db)
    contact = _agent_link_only(db, w)
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine), codes=("sales_report_not_enabled",))


@pytest.mark.parametrize("mine", [None, True])
def test_an_inactive_salesperson_user_without_the_grant_is_refused(client, db, mine):
    w = _world(db)
    contact = _agent_link_only(db, w, user_status="INACTIVE")
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine), codes=("sales_report_not_enabled",))


@pytest.mark.parametrize("mine", [None, True])
def test_a_trashed_salesperson_user_without_the_grant_is_refused(client, db, mine):
    w = _world(db)
    contact = _agent_link_only(db, w, user_status="ACTIVE", trashed=True)
    _refused(_ask(client, contact, group_by="customer", top_n=10, mine=mine), codes=("sales_report_not_enabled",))


def test_a_salesperson_also_linked_to_an_outside_customer_gets_only_linked_and_book(client, db):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    _link(db, contact, w.in1)
    _link(db, contact, w.out)
    db.commit()
    body = _ok(client, contact, group_by="brand", top_n=10)
    assert _total(body) == D("100.00") and len(body["rows"]) == 1, body


def test_a_salesperson_linked_only_outside_the_book_gets_zero_rows(client, db):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    _link(db, contact, w.out)
    db.commit()
    resp = _ask(client, contact, group_by="brand", top_n=10)
    assert resp.status_code != 200 or (_total(resp.json()) == 0 and not resp.json()["rows"]), resp.text


def test_a_granted_agent_link_only_contact_keeps_todays_behaviour(client, db):
    w = _world(db)
    contact = _contact(db, granted=True)
    book = link_agent(db, contact, "ZZT Book Agent")
    w.in1.sales_agent_id = book.id
    w.in2.sales_agent_id = book.id
    db.commit()
    body = _ok(client, contact, group_by="customer", top_n=10)
    assert _total(body) == ALL_TOTAL, body
