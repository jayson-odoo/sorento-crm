"""RED tests - REPORT-SMART-L R1 security: item and category rankings on the report-ask route.

Top selling refuses a granted contact that is neither staff nor linked to a customer (403
`customer_not_permitted`). The report ask must refuse a granted live salesperson the same way when
they do not ask for their own book (`mine` None / False), for `group_by` product and category,
whether their agent link has customers or an empty book. With `mine` true they get their book only;
staff with the switch see every customer; an ungranted salesperson with `mine` true gets their book
(ruling 2). Postgres only; every row seeded here (generic names). Beside
`tests/test_report_ask_my_sales_route.py`, whose world and helpers are reused.
"""
from __future__ import annotations

import pytest

from tests._chat_asker_seed import give_role, link_agent
from tests.test_report_ask_my_sales_route import (  # noqa: F401  (client / db are fixtures)
    ALL_TOTAL,
    BOOK_TOTAL,
    _ask,
    _contact,
    _names,
    _ok,
    _salesperson,
    _total,
    _world,
    client,
    db,
)

ITEM_AXES = ["product", "category"]


def _empty_book_salesperson(db):
    from tests._chat_asker_seed import link_user

    contact = _contact(db, granted=True)
    give_role(db, link_user(db, contact), "salesperson")
    link_agent(db, contact, "ZZT Empty Book Agent")
    db.commit()
    return contact


def _refused_not_permitted(resp) -> None:
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("code") == "customer_not_permitted", body
    assert not body.get("rows"), body


@pytest.mark.parametrize("mine", [None, False])
@pytest.mark.parametrize("group_by", ITEM_AXES)
def test_r1_sec_a_granted_salesperson_with_a_book_is_refused_items_without_my(client, db, group_by, mine) -> None:
    w = _world(db)
    contact = _salesperson(db, w, granted=True)
    _refused_not_permitted(_ask(client, contact, group_by=group_by, top_n=10, mine=mine))


@pytest.mark.parametrize("mine", [None, False])
@pytest.mark.parametrize("group_by", ITEM_AXES)
def test_r1_sec_a_granted_salesperson_with_an_empty_book_is_refused_items_without_my(client, db, group_by, mine) -> None:
    _world(db)
    contact = _empty_book_salesperson(db)
    _refused_not_permitted(_ask(client, contact, group_by=group_by, top_n=10, mine=mine))


@pytest.mark.parametrize("group_by", ITEM_AXES)
def test_r1_sec_guard_the_same_salesperson_with_my_gets_only_their_book(client, db, group_by) -> None:
    w = _world(db)
    contact = _salesperson(db, w, granted=True)
    body = _ok(client, contact, group_by=group_by, top_n=10, mine=True)
    assert _total(body) == BOOK_TOTAL, body
    assert not any("Outside" in n or "Brand 3" in n or "Cat 3" in n or "MS-3" in n for n in _names(body)), body["rows"]


@pytest.mark.parametrize("group_by", ITEM_AXES)
def test_r1_sec_guard_staff_with_the_switch_sees_every_customer(client, db, group_by) -> None:
    from tests._chat_asker_seed import link_user

    _world(db)
    contact = _contact(db, granted=True)
    link_user(db, contact)
    from tests.test_top_selling_report import _access

    _access(db, contact, "Sorento Office")
    db.commit()
    body = _ok(client, contact, group_by=group_by, top_n=10)
    assert _total(body) == ALL_TOTAL, body


@pytest.mark.parametrize("group_by", ITEM_AXES)
def test_r1_sec_guard_an_ungranted_salesperson_with_my_gets_their_book(client, db, group_by) -> None:
    w = _world(db)
    contact = _salesperson(db, w, granted=False)
    body = _ok(client, contact, group_by=group_by, top_n=10, mine=True)
    assert _total(body) == BOOK_TOTAL, body
