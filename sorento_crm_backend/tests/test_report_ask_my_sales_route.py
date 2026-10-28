"""RED tests - REPORT-SMART-L UAC AC11: `mine` on the sales report-ask route.

A salesperson (a role-user with role `salesperson` whose `users.respond_contact_id` is the contact)
asks for sales without the `sales_orders.sales_report` grant. Owner 28 Oct 08:40: one rule for totals and
rankings, set by the contact's linked customer: no linked customer sees ALL figures, a linked contact only its
customers. Only a "my ..." ask (`mine=true`) narrows a salesperson to their own book: the customers whose
`customers.sales_agent_id` is a `sales_agents` row linked to the contact. With the grant, `mine=true` narrows
to the book and `mine` false is unscoped. Staff and unknown
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


@pytest.mark.parametrize("group_by", [None, "customer", "brand", "month"])
def test_a_salesperson_without_the_grant_and_no_linked_customer_sees_all_figures(client, db, group_by):
    """Owner 28 Oct 08:40: the total and every ranking run over ALL customers, never narrowed."""
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    for mine in (None, False):
        body = _ok(client, contact, group_by=group_by, top_n=10 if group_by else None, mine=mine)
        assert _total(body) == ALL_TOTAL, body
        if group_by and group_by != "month":
            assert len(body["rows"]) == 3, body["rows"]


@pytest.mark.parametrize("group_by", ["product", "category"])
def test_an_ungranted_salesperson_with_no_link_gets_the_item_and_category_ranking_over_all(client, db, group_by):
    """Owner 28 Oct 10:15: REPORT-SMART R1 retires for a contact with no linked customer."""
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by=group_by, top_n=10)
    assert _total(body) == ALL_TOTAL and len(body["rows"]) == 3, body


@pytest.mark.parametrize("group_by", [None, "customer", "product", "brand", "category", "month"])
def test_a_salesperson_without_the_grant_with_mine_sees_only_their_book(client, db, group_by):
    """The 23 Oct "my ..." own-book ruling stands (owner 28 Oct 08:40 keeps it): `mine` narrows."""
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by=group_by, top_n=10 if group_by else None, mine=True)
    assert _total(body) == BOOK_TOTAL, body
    assert not any("Outside" in n or "Brand 3" in n or "Cat 3" in n or "MS-3" in n for n in _names(body)), body["rows"]
    if group_by:
        assert len(body["rows"]) == (1 if group_by == "month" else 2), body["rows"]


def test_a_salesperson_without_the_grant_ranks_the_book_customers_by_name(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by="customer", top_n=10, mine=True)
    assert _names(body) == {w.in1.customer_name, w.in2.customer_name}, body["rows"]


# ------------------------------------------------------------------ 2. salesperson, no grant, agent axes (owner 28 Oct 08:40: allowed)


@pytest.mark.parametrize("mine", MINE)
def test_a_salesperson_without_the_grant_may_rank_by_sales_agent(client, db, mine):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    body = _ok(client, contact, group_by="sales_agent", top_n=10, mine=mine)
    assert body["status"] == "ok" and _total(body) == (BOOK_TOTAL if mine else ALL_TOTAL), body


@pytest.mark.parametrize("param", ["sales_agent_ids", "customer_agent_ids"])
def test_a_salesperson_without_the_grant_may_filter_by_agent(client, db, param):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    agent = seed_agent(db, code="ZZT Any Agent")
    db.commit()
    resp = _ask(client, contact, group_by="customer", top_n=10, **{param: [agent.id]})
    assert resp.status_code == 200, resp.text


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


@pytest.mark.parametrize("group_by", [None, "brand"])
def test_a_linked_contact_gets_only_its_customer_on_a_total_and_a_ranking(client, db, group_by):
    """Owner 28 Oct 08:40: a contact WITH a linked customer sees only that customer's figures, totals and rankings alike."""
    w = _world(db)
    contact = _contact(db, granted=True)
    _link(db, contact, w.in2)
    db.commit()
    body = _ok(client, contact, group_by=group_by, top_n=10 if group_by else None)
    assert _total(body) == D("200.00"), body
    if group_by:
        assert len(body["rows"]) == 1, body["rows"]


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
    body = _ok(client, contact, group_by="brand", top_n=10, mine=True)
    assert _total(body) == D("100.00") and len(body["rows"]) == 1, body
    # Owner 28 Oct 08:40: without `mine` the contact's linked customers are all it sees.
    body = _ok(client, contact, group_by="brand", top_n=10)
    assert _total(body) == D("1100.00") and len(body["rows"]) == 2, body


def test_a_salesperson_linked_only_outside_the_book_gets_zero_rows(client, db):
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    _link(db, contact, w.out)
    db.commit()
    resp = _ask(client, contact, group_by="brand", top_n=10, mine=True)
    assert resp.status_code != 200 or (_total(resp.json()) == 0 and not resp.json()["rows"]), resp.text
    # Owner 28 Oct 08:40: without `mine` the linked customer's own figures are what it sees.
    body = _ok(client, contact, group_by="brand", top_n=10)
    assert _total(body) == D("1000.00"), body


def test_a_granted_agent_link_only_contact_keeps_todays_behaviour(client, db):
    w = _world(db)
    contact = _contact(db, granted=True)
    book = link_agent(db, contact, "ZZT Book Agent")
    w.in1.sales_agent_id = book.id
    w.in2.sales_agent_id = book.id
    db.commit()
    body = _ok(client, contact, group_by="customer", top_n=10)
    assert _total(body) == ALL_TOTAL, body


# ------------------------------------------------------------------ 9. the echo says the run is narrowed to the asker's own customers

_BOOK_KEYS = {"book", "mine", "own_customers", "my_customers", "my_book"}


def _book_entries(body):
    """Echo entries marking the book narrowing: a book-like key, or a label naming the asker's own customers."""
    import re

    return [
        f for f in body.get("filters") or []
        if f.get("key") in _BOOK_KEYS or re.search(r"\b(my|own)\b.*\bcustomers\b|\bbook\b", str(f.get("label", "")), re.I)
    ]


@pytest.mark.parametrize("group_by", [None, "customer", "brand"])
def test_a_granted_salesperson_with_mine_gets_the_book_echo(client, db, group_by):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by=group_by, top_n=10 if group_by else None, mine=True)
    assert len(_book_entries(body)) == 1, body["filters"]


@pytest.mark.parametrize("group_by", [None, "customer", "brand"])
def test_an_ungranted_salesperson_with_mine_gets_the_book_echo(client, db, group_by):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by=group_by, top_n=10 if group_by else None, mine=True)
    assert len(_book_entries(body)) == 1, body["filters"]


@pytest.mark.parametrize("mine", [None, False])
def test_an_ungranted_salesperson_without_mine_gets_no_book_echo(client, db, mine):
    """Owner 28 Oct 08:40: "Limited to: your customers" prints only when actually narrowed."""
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by="customer", top_n=10, mine=mine)
    assert _book_entries(body) == [], body["filters"]


@pytest.mark.parametrize("mine", [None, False])
def test_near_miss_a_granted_salesperson_without_mine_gets_no_book_echo(client, db, mine):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=True), group_by="customer", top_n=10, mine=mine)
    assert _book_entries(body) == [], body["filters"]


@pytest.mark.parametrize("mine", [None, True])
def test_near_miss_a_granted_staff_contact_gets_no_book_echo(client, db, mine):
    _world(db)
    contact = _contact(db, granted=True)
    link_user(db, contact)
    db.commit()
    body = _ok(client, contact, group_by="customer", top_n=10, mine=mine)
    assert _book_entries(body) == [], body["filters"]


# ------------------------------------------------------------------ 10. outstanding kinds keep Q6 (security re-check of owner 28 Oct 08:40)
# The 08:40 ruling is about SALES figures. The outstanding kinds follow the Outstanding reveal: a salesperson without it
# stays on its own book there, and the agent axes stay refused.


def _open_world(db):
    """The `_world` customers with open demand (nothing delivered): outstanding in1 100 / in2 200 / out 1000."""
    other = seed_agent(db, code="ZZT Other Agent")
    w = SimpleNamespace()
    w.in1 = seed_customer(db, name="ZZT Book Customer One")
    w.in2 = seed_customer(db, name="ZZT Book Customer Two")
    w.out = seed_customer(db, name="ZZT Outside Customer")
    rows = [(w.in1, "1", 1, "100.00"), (w.in2, "2", 2, "200.00"), (w.out, "3", 10, "1000.00")]
    for cust, n, qty, total in rows:
        prod = _prod(db, f"ZZTOS-{n}", brand=_brand(db, f"ZZT OBrand {n}"), category=_category(db, f"ZZT OCat {n}"))
        seed_so_line(db, cust=cust, prod=prod, qty=qty, total=total, agent=other, delivered=0)
    db.flush()
    return w


def _outstanding(client, contact, **params):
    q = {"basis": "outstanding", "measure": "amount", **_as_contact(contact), **params}
    return client.get(ROUTE, params={k: v for k, v in q.items() if v is not None}, headers=KEY)


def _with_outstanding_reveal(db, contact):
    from app.services.contact_field_reveal_service import set_granted_keys

    set_granted_keys(db, contact.id, ["sales_orders.outstanding"], actor_id=None)
    db.commit()


@pytest.mark.parametrize("group_by", [None, "customer"])
def test_a_salesperson_without_the_outstanding_reveal_stays_on_their_book_there(client, db, group_by):
    """Owner 28 Oct 08:40 is for sales figures; the outstanding kinds keep Q6 (the Outstanding reveal)."""
    w = _open_world(db)
    contact = _salesperson(db, w, granted=False)
    resp = _outstanding(client, contact, group_by=group_by, top_n=10 if group_by else None)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert _total(body) == BOOK_TOTAL, body
    assert not any("Outside" in n for n in _names(body)), body["rows"]


@pytest.mark.parametrize("basis", ["outstanding", "unpaid"])
@pytest.mark.parametrize("group_by", ["sales_agent"])
def test_a_salesperson_without_the_outstanding_reveal_may_not_use_the_agent_axis(client, db, basis, group_by):
    w = _open_world(db)
    contact = _salesperson(db, w, granted=False)
    _refused(_outstanding(client, contact, basis=basis, group_by=group_by, top_n=10))


def test_a_salesperson_with_the_outstanding_reveal_sees_all_outstanding(client, db):
    w = _open_world(db)
    contact = _salesperson(db, w, granted=False)
    _with_outstanding_reveal(db, contact)
    body = _outstanding(client, contact, group_by="customer", top_n=10).json()
    assert _total(body) == ALL_TOTAL and w.out.customer_name in _names(body), body
    assert _outstanding(client, contact, group_by="sales_agent", top_n=10).status_code == 200


def test_the_sales_bases_stay_all_for_a_salesperson_without_a_reveal(client, db):
    w = _world(db)
    body = _ok(client, _salesperson(db, w, granted=False), group_by="customer", top_n=10)
    assert _total(body) == ALL_TOTAL, body
