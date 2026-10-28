"""REPORT-SMART-L fix round (live spot check, PR note 6335349880): one 'may ask' rule at the
chatbot seam.

The engine refused every sales figure ask without `sales_orders.sales_report` before the tool
ran, so a live salesperson (ACTIVE CRM user with the salesperson role and an agent link with
customers) never reached the route that narrows them to their own book. The ranking kinds
(`sales_ranking`, and a `sales_analysis` by group that by_capability turns into the ranking) go
through to the report-ask tool; `top_selling` stays refused. Owner 28 Oct 08:40: a `sales_report` total passes too, like a ranking. Everyone else
without the grant stays refused. Fake names only (CONTACT A, SALESPERSON B).
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import CONTACT_ID
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    DENIAL,
    TOOL,
    _e,
    _hit,
    _names,
    _rank,
    _say_all,
    console,
    console_no_grant,
)
from tests.chatbot.test_report_smart_capability import _ask


def _contact_row(db):
    from app.models.access import RespondContact

    return db.query(RespondContact).filter(RespondContact.respond_io_id == str(CONTACT_ID)).one()


def _make_salesperson(console) -> None:
    """CONTACT A becomes SALESPERSON B: an ACTIVE user with the salesperson role, an agent link and a customer."""
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._chat_asker_seed import give_role, link_agent, link_user
    from tests._mc_lookup_seed import customer

    db = console.session_factory()
    try:
        contact = _contact_row(db)
        give_role(db, link_user(db, contact, name="ZZT Salesperson B"), "salesperson")
        agent = link_agent(db, contact, "ZZT Agent B")
        own = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT BOOK CUSTOMER SDN BHD")
        own.sales_agent_id = agent.id
        db.commit()
    finally:
        db.close()


def _agent_link_only(console) -> None:
    from tests._chat_asker_seed import link_agent

    db = console.session_factory()
    try:
        link_agent(db, _contact_row(db), "ZZT Agent B")
        db.commit()
    finally:
        db.close()


def _staff(console) -> None:
    from tests._chat_asker_seed import link_user

    db = console.session_factory()
    try:
        link_user(db, _contact_row(db), name="ZZT Staff A")
        db.commit()
    finally:
        db.close()


MY_RANKINGS = [
    ("my sales this month by customer", dict(order_status="sales_ranking")),
    ("jualan saya bulan ini ikut pelanggan", dict(order_status="sales_ranking")),
    ("我这个月的销售 按客户", dict(order_status="sales_ranking")),
    ("my sales by customer, amount delivered", dict(order_status="sales_ranking")),
    ("my sales this month by customer", dict(order_status="sales_analysis")),
    ("jualan saya ikut customer", dict(order_status="sales_analysis")),
    ("我的销售 按客户 分开", dict(order_status="sales_analysis")),
    ("sales of mine per customer lah", dict(order_status="sales_analysis")),
]


@pytest.mark.parametrize("body, shape", MY_RANKINGS)
def test_a_salesperson_without_the_grant_reaches_the_report_tool_with_mine(console_no_grant, body, shape) -> None:
    _make_salesperson(console_no_grant)
    qf = _ask(group_by="customer", top_n=5, measure="amount", basis="delivered", self_reference=True, **shape)
    text, calls = console_no_grant.say(qf, body)
    assert len(calls) == 1, (text, calls)
    assert calls[0].get("mine") is True and calls[0]["group_by"] == "customer", calls


REFUSED_KINDS = [
    ("top 5 selling items this month", dict(order_status="top_selling", group_by=None, rank_by="amount",
                                            rank_group="item", rank_direction="top", top_n=5, basis="delivered")),
    # ("my top selling items", ...) flipped by owner ruling 2 (REPORT-SMART-L R1): an ungranted live salesperson's
    # "my ..." item ranking is the own-book ranking; pinned in test_one_ranking_r1.py::test_r1_5d.
    ("本月 畅销产品 top 5", dict(order_status="top_selling", group_by=None, rank_by="amount", rank_group="item",
                                 rank_direction="top", top_n=5, basis="ordered")),
    ("item paling laku", dict(order_status="top_selling", group_by=None, rank_by="qty", rank_group="item",
                              rank_direction="top", top_n=5, basis="delivered")),
]


@pytest.mark.parametrize("body, shape", REFUSED_KINDS)
def test_a_salesperson_without_the_grant_and_no_link_gets_the_item_ranking_over_all(
    console_no_grant, monkeypatch, body, shape
) -> None:
    """Owner 28 Oct 10:15: REPORT-SMART R1 retires for a contact with no linked customer; the item ranking runs over
    ALL (no `mine`)."""
    _make_salesperson(console_no_grant)
    qf = _rank(domain_hint="order", intent_hint="check_order", **{"measure": "amount", **shape})
    text, log = _say_all(console_no_grant, monkeypatch, qf, body)
    ran = [a for n, a in log if n == TOOL]
    assert len(ran) == 1 and "crm_top_selling_report" not in _names(log), (text, log)
    assert not ran[0].get("mine"), ran


TOTALS = [
    ("sales report this month", dict(order_status="sales_report", group_by=None, measure=None, basis="delivered")),
    ("laporan jualan bulan ini", dict(order_status="sales_report", group_by=None, measure=None, basis="delivered")),
    ("销售报告 这个月", dict(order_status="sales_report", group_by=None, measure=None, basis="delivered")),
]


@pytest.mark.parametrize("body, shape", TOTALS)
def test_a_salesperson_without_the_grant_and_no_linked_customer_gets_the_total_over_all(console_no_grant, body, shape) -> None:
    """Owner 28 Oct 08:40: no linked customer sees ALL figures, so the total runs, never narrowed (no `mine`)."""
    _make_salesperson(console_no_grant)
    qf = _ask(**shape)
    text, calls = console_no_grant.say(qf, body)
    assert len(calls) == 1, (text, calls)
    assert not calls[0].get("mine"), calls


def test_my_total_for_a_salesperson_without_the_grant_is_still_the_own_book(console_no_grant) -> None:
    """The 23 Oct "my ..." own-book ruling stands: only a "my" ask is narrowed."""
    _make_salesperson(console_no_grant)
    qf = _ask(order_status="sales_report", group_by=None, measure=None, basis="delivered", self_reference=True)
    text, calls = console_no_grant.say(qf, "my sales report")
    assert len(calls) == 1 and calls[0].get("mine") is True, (text, calls)


@pytest.mark.parametrize("who", ["no_links", "agent_link_only"])
def test_near_miss_a_contact_that_is_not_a_live_salesperson_is_refused_without_the_grant(console_no_grant, who) -> None:
    if who == "agent_link_only":
        _agent_link_only(console_no_grant)
    qf = _ask(order_status="sales_ranking", group_by="customer", top_n=5, measure="amount", basis="delivered",
              self_reference=True)
    text, calls = console_no_grant.say(qf, "my sales this month by customer")
    assert calls == [] and text.strip() == DENIAL, (text, calls)


def test_near_miss_a_staff_contact_with_the_grant_runs_as_today(console) -> None:
    _staff(console)
    text, calls = console.say(_rank(_e("Sorento", "brand")), "top 3 salesman for Sorento brand last month")
    assert len(calls) == 1 and not calls[0].get("mine"), (text, calls)


def test_an_ungranted_salesperson_asking_the_yearly_comparison_is_refused_with_no_question_first(console_no_grant, monkeypatch) -> None:
    """Security re-check of owner 28 Oct 08:40: only a verdict that runs on the report ask passes the early gate. The
    Yearly comparison (`group_by` year, which `by_capability` leaves alone) is refused at once, never asked its basis."""
    _make_salesperson(console_no_grant)
    qf = _rank(domain_hint="order", intent_hint="check_order",
               **{"order_status": "sales_analysis", "group_by": "year", "measure": None, "basis": None})
    text, log = _say_all(console_no_grant, monkeypatch, qf, "sales by year")
    assert text.strip() == DENIAL, text
    assert not [n for n in _names(log) if n in (TOOL, "crm_sales_analysis", "crm_sales_report")], _names(log)
