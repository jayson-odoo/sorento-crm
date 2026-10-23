"""REPORT-SMART-L one ranking, round R1 (AC-OR1, AC-OR-ACCESS): every ranking runs on the report engine.

Owner rulings 23 Oct: an item or category ranking (the parser's `top_selling` label with
`rank_group` item / category) goes to `crm_report_ask` like every other ranking; what is missing
is asked in ONE reply; never the catalogue line, a grain question or `crm_top_selling_report`.
The unification widens nothing: the Sales report switch for everyone, except a live
salesperson's "my ..." own-book ask; an unlinked non-staff contact is refused an item / category
ranking as top selling refuses it today; a dealer sees its own customers. Fake names and codes.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    CATALOGUE_LINE,
    SEP,
    TOOL,
    _names,
    _say_all,
    console,
    console_no_grant,
)
from tests.chatbot.test_report_smart_salesperson_gate import _make_salesperson
from tests.chatbot.test_report_smart_step7 import KEEP
from tests.test_report_ask_route import client, db  # noqa: F401 - fixtures of the route tests

OLD_TOOL = "crm_top_selling_report"
YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
_NUMBERED = re.compile(r"^\s*([1-9])[.)]", re.M)


def _top_selling(**overrides: Any) -> dict[str, Any]:
    """The owner's T1 as the live parser read it: label top_selling, axis product, grain item."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="top_selling", group_by="product",
        rank_group="item", rank_direction="top", top_n=30, measure=None, basis=None, rank_by=None,
        entities=[], domain_in_message=True, state_changes=list(KEEP), **YEAR_2026,
    )
    base.update(overrides)
    return _parser_output(**base)


def _answer(**overrides: Any) -> dict[str, Any]:
    """The owner's T2 ('Delivered qty'): the parser labels it sales_ranking and declares a fill."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", rank_group="item",
        group_by=None, top_n=None, measure="qty", basis="delivered", entities=[],
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
        state_changes=[{"op": "answer", "axis": None, "position": None}],
        date_filter_start=None, date_filter_end=None,
    )
    base.update(overrides)
    return _parser_output(**base)


def _ran(log: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [a for n, a in log if n == TOOL]


def _clean(text: str, log: list[tuple[str, dict[str, Any]]]) -> None:
    assert OLD_TOOL not in _names(log), _names(log)
    assert text.strip() != CATALOGUE_LINE and "I can rank sales by" not in text, text
    assert "rank by" not in text.lower() and "product or category" not in text.lower(), text  # no grain question


# ---------------------------------------------------------------- 1. T1 then T2


def test_r1_1_the_item_ask_asks_what_is_missing_in_one_reply_then_the_answer_runs(console, monkeypatch) -> None:
    text, log = _say_all(console, monkeypatch, _top_selling(), "Top 30 selling item this year")
    assert _names(log) == [], log
    _clean(text, log)
    assert [int(n) for n in _NUMBERED.findall(text)] == [1, 2], text  # measure and basis, one reply
    text, log = _say_all(console, monkeypatch, _answer(), "Delivered qty")
    assert OLD_TOOL not in _names(log), _names(log)
    assert len(_ran(log)) == 1, (text, log)
    args = _ran(log)[0]
    assert args["group_by"] == "product" and args["top_n"] == 30, args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args


# ---------------------------------------------------------------- 2. the full item ask


def test_r1_2_a_full_item_ask_runs_on_the_report_engine(console, monkeypatch) -> None:
    text, log = _say_all(
        console, monkeypatch, _top_selling(top_n=10, measure="qty", basis="delivered", rank_by="quantity"),
        "top 10 selling items this year by qty delivered")
    _clean(text, log)
    assert len(_ran(log)) == 1, (text, log)
    args = _ran(log)[0]
    assert args["group_by"] == "product" and args["top_n"] == 10, args


# ---------------------------------------------------------------- 3. category


def test_r1_3_which_category_sells_most_asks_what_is_missing_then_ranks_categories(console, monkeypatch) -> None:
    text, log = _say_all(
        console, monkeypatch,
        _top_selling(group_by=None, rank_group="category", top_n=None, date_filter_start=None, date_filter_end=None),
        "which category sells most")
    assert _names(log) == [], log
    _clean(text, log)
    assert "Which period" in text, text
    text, log = _say_all(
        console, monkeypatch, _answer(top_n=5, rank_group="category", **SEP), "september, top 5, qty, delivered")
    assert OLD_TOOL not in _names(log), _names(log)
    assert len(_ran(log)) == 1, (text, log)
    assert _ran(log)[0]["group_by"] == "category", log


# ---------------------------------------------------------------- 4. the old lane dispatch (a live session)


def test_r1_4_a_top_selling_verdict_reaching_the_old_dispatch_is_sent_to_the_report_engine(console, monkeypatch) -> None:
    """A live session mid-ranking never passed `by_capability`: drive the verdict straight to the lane dispatch."""
    from app.services.chatbot.lanes.business import report_ask

    monkeypatch.setattr(report_ask, "by_capability", lambda verdict: verdict)
    text, log = _say_all(
        console, monkeypatch, _top_selling(top_n=10, measure="qty", basis="delivered", rank_by="quantity"),
        "top 10 selling items this year by qty delivered")
    assert OLD_TOOL not in _names(log), _names(log)
    assert len(_ran(log)) == 1 and _ran(log)[0]["group_by"] == "product", (text, log)


# ---------------------------------------------------------------- 5. access (lane level)

FULL_ITEMS = dict(top_n=5, measure="qty", basis="delivered", rank_by="quantity")


def test_r1_5a_staff_with_the_switch_runs_an_item_ranking(console, monkeypatch) -> None:
    from tests.chatbot.test_report_smart_salesperson_gate import _staff

    _staff(console)
    text, log = _say_all(console, monkeypatch, _top_selling(**FULL_ITEMS), "top 5 selling items this year")
    assert OLD_TOOL not in _names(log) and len(_ran(log)) == 1, (text, log)


def test_r1_5b_guard_a_contact_without_the_switch_is_refused_an_item_ranking(console_no_grant, monkeypatch) -> None:
    text, log = _say_all(console_no_grant, monkeypatch, _top_selling(**FULL_ITEMS), "top 5 selling items this year")
    assert not [n for n in _names(log) if n in (TOOL, OLD_TOOL)], _names(log)
    assert text.strip(), text


def test_r1_5c_guard_an_ungranted_salesperson_without_my_is_refused_items(console_no_grant, monkeypatch) -> None:
    _make_salesperson(console_no_grant)
    text, log = _say_all(
        console_no_grant, monkeypatch, _top_selling(self_reference=None, **FULL_ITEMS), "top selling items this year")
    assert not [n for n in _names(log) if n in (TOOL, OLD_TOOL)], _names(log)
    assert text.strip(), text


def test_r1_5d_an_ungranted_salesperson_my_items_gets_the_own_book_ranking(console_no_grant, monkeypatch) -> None:
    # Ruling 2: "Limited to: your customers" is the route's header for `mine`; the lane sends mine.
    _make_salesperson(console_no_grant)
    text, log = _say_all(
        console_no_grant, monkeypatch, _top_selling(self_reference=True, **FULL_ITEMS), "my top selling items this year")
    assert OLD_TOOL not in _names(log), _names(log)
    assert len(_ran(log)) == 1, (text, log)
    args = _ran(log)[0]
    assert args.get("mine") is True and args["group_by"] == "product", args


# ---------------------------------------------------------------- 5. access (the route)


def test_r1_5e_a_granted_unlinked_non_staff_contact_is_refused_an_item_ranking(client, db) -> None:
    from tests.test_report_ask_route import _ask, _code, _full, _ranking_world

    _ranking_world(db)
    resp = _ask(client, _full(db), group_by="product", top_n=3)
    assert resp.status_code == 403 and _code(resp) == "customer_not_permitted", resp.text


def test_r1_5e_the_same_contact_is_refused_a_category_ranking(client, db) -> None:
    from tests.test_report_ask_route import _ask, _code, _full, _ranking_world

    _ranking_world(db)
    resp = _ask(client, _full(db), group_by="category", top_n=3)
    assert resp.status_code == 403 and _code(resp) == "customer_not_permitted", resp.text


def test_r1_5f_guard_a_dealer_gets_only_its_own_customers_items(client, db) -> None:
    from tests.test_report_ask_route import D, _dealer, _ok, _ranking_world, _sale, money, seed_customer, unique_code

    w = _ranking_world(db)
    other = seed_customer(db, name=unique_code("Other"))
    _sale(db, cust=other, wh=w.wh, agent=w.a1, prod=w.p1, qty=500, total="50000.00")
    body = _ok(client, _dealer(db, w), group_by="product", top_n=10)
    assert body["total"]["qty"] == 70 and money(body["total"]["amount"]) == D("5250.00"), body["total"]


# ---------------------------------------------------------------- 6. near misses


def test_r1_6_guard_a_salesman_ranking_is_unchanged(console) -> None:
    text, calls = console.say(
        _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_ranking", group_by="sales_agent",
                       top_n=5, measure="qty", basis="delivered", entities=[], state_changes=list(KEEP), **YEAR_2026),
        "top 5 salesman this year")
    assert len(calls) == 1 and calls[0]["group_by"] == "sales_agent" and calls[0]["top_n"] == 5, (text, calls)


def test_r1_6_guard_total_sales_this_month_still_uses_the_sales_report_tool(console, monkeypatch) -> None:
    text, log = _say_all(
        console, monkeypatch,
        _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_report", group_by=None,
                       top_n=None, measure=None, basis=None, entities=[], domain_in_message=True, **SEP),
        "total sales this month")
    assert "crm_sales_report" in _names(log), (text, log)
    assert TOOL not in _names(log), _names(log)
