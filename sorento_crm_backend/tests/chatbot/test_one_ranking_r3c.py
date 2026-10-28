"""REPORT-SMART-L one ranking, round R3c (AC-OR3, owner ruling Q2 b): a row pick opens the item detail.

After an item ranking run on the report engine: the reply tells the user to reply with a rank number;
the number opens that item's sales by customer and by month (a category row opens its items), on the
report engine, with the period, basis and measure held; "outstanding" re-runs the same ranking on the
outstanding basis. Fake names only.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import TOOL, _names, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

OLD_TOOL = "crm_top_selling_report"
YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
P1, P2, P3 = ("aaaaaaaa-0000-4000-8000-00000000000%d" % i for i in (1, 2, 3))
C1, C2 = "bbbbbbbb-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002"
OFFER_ITEM = "Reply with a rank number to see that item's customers and months."
OFFER_CATEGORY = "Reply with a rank number to see that category's top items."

ROWS = {
    "product": [{"rank": i, "name": f"ZZT-ITEM-{i}", "qty": 40 - i, "amount": 400.0 - i, "keys": [k]}
                for i, k in ((1, P1), (2, P2), (3, P3))],
    "category": [{"rank": i, "name": f"ZZT CAT {i}", "qty": 40 - i, "amount": 400.0 - i, "keys": [k]}
                 for i, k in ((1, C1), (2, C2))],
    "customer": [{"rank": 1, "name": "ZZT CUSTOMER ONE", "qty": 9, "amount": 90.0, "keys": ["cust-1"]},
                 {"rank": 2, "name": "ZZT CUSTOMER TWO", "qty": 8, "amount": 80.0, "keys": ["cust-2"]}],
    "month": [{"rank": 1, "name": "2026-09", "qty": 5, "amount": 50.0, "keys": []}],
}


def _body(args: dict[str, Any]) -> dict[str, Any]:
    group_by = args.get("group_by")
    rows = ROWS.get(group_by, []) if group_by else []
    return {
        "status": "ok", "message": None, "basis": args.get("basis", "delivered"),
        "basis_label": "outstanding orders" if args.get("basis") == "outstanding" else "delivered sales",
        "measure": args.get("measure", "amount"), "sort": args.get("sort", "desc"), "group_by": group_by,
        "group_label": (group_by or "").replace("_", " ").title() or None,
        "date_from": args.get("date_from"), "date_to": args.get("date_to"),
        "filters": [], "rows": rows, "more": 0, "total_count": len(rows), "total": {"qty": 50, "amount": 500.0},
    }


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _ranking(group_by: str = "product", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="top_selling", group_by=group_by,
        rank_group="item" if group_by == "product" else "category", rank_direction="top", top_n=10, measure="qty",
        basis="delivered", rank_by="quantity", entities=[], domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
    base.update(overrides)
    return _parser_output(**base)


def _pick(position: int) -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], order_status=None,
        reference_positions=[position], open_question_answer={"mode": "pick", "picked": [position], "items": [], "qty_for_all": None},
        state_changes=[{"op": "answer", "axis": None, "position": position}])


def _on_screen(console, monkeypatch, group_by: str = "product") -> str:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _ranking(group_by), "top 10 selling items this year by qty delivered")
    assert OLD_TOOL not in _names(log) and len([1 for n, _a in log if n == TOOL]) == 1, ("setup", text, log)
    return text


def _ran(log: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [a for n, a in log if n == TOOL]


def test_r3c_1_the_item_ranking_reply_tells_the_user_to_reply_with_a_rank_number(console, monkeypatch) -> None:
    assert OFFER_ITEM in _on_screen(console, monkeypatch)


def test_r3c_1_the_category_ranking_reply_offers_its_top_items(console, monkeypatch) -> None:
    assert OFFER_CATEGORY in _on_screen(console, monkeypatch, "category")


def test_r3c_2_a_row_pick_opens_that_items_sales_by_customer_and_by_month(console, monkeypatch) -> None:
    _on_screen(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _pick(2), "2")
    assert OLD_TOOL not in _names(log), _names(log)
    ran = _ran(log)
    assert sorted(a.get("group_by") for a in ran) == ["customer", "month"], (text, log)
    for args in ran:
        assert args.get("product_ids") == [P2] or args.get("product_code") == "ZZT-ITEM-2", args
        assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
        assert args["basis"] == "delivered" and args["measure"] == "qty", args
    assert "ZZT CUSTOMER ONE" in text and "Sep 2026" in text, text  # both breakdowns are in the reply


def test_r3c_3_a_category_row_pick_opens_that_categorys_items(console, monkeypatch) -> None:
    _on_screen(console, monkeypatch, "category")
    text, log = _say_all(console, monkeypatch, _pick(1), "1")
    assert OLD_TOOL not in _names(log), _names(log)
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    args = ran[0]
    assert args["group_by"] == "product" and args.get("category_ids") == [C1], args
    assert args["date_from"] == "2026-01-01" and args["basis"] == "delivered" and args["measure"] == "qty", args


@pytest.mark.parametrize("label", ["top_selling", "sales_ranking"])
def test_r3c_4_outstanding_reruns_the_same_ranking_on_the_outstanding_basis(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", entities=[], group_by=None, top_n=None, measure=None,
        basis="outstanding", rank_by=None, rank_group=None, domain_in_message=False,
        order_status=label, state_changes=[{"op": "set", "axis": "sort", "position": None}],
        **({"ranking_refine": True} if label == "sales_ranking" else {}))
    text, log = _say_all(console, monkeypatch, qf, "outstanding")
    assert OLD_TOOL not in _names(log) and "crm_outstanding_report" not in _names(log), _names(log)
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["basis"] == "outstanding" and ran[0]["group_by"] == "product" and ran[0]["top_n"] == 10, ran
    assert ran[0]["measure"] == "qty" and ran[0]["date_from"] == "2026-01-01", ran


def test_r3c_5_guard_a_number_reply_with_no_ranking_on_screen_runs_no_ranking(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _pick(2), "2")
    assert _ran(log) == [] and OLD_TOOL not in _names(log), (text, log)


def test_r3c_5_a_customer_ranking_row_pick_opens_that_customers_products(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(
        console, monkeypatch,
        _ranking("customer", order_status="sales_ranking", rank_group=None), "top 10 customers this year by qty delivered")
    assert len(_ran(log)) == 1, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _pick(1), "1")
    # REPORT-SMART-L R5 B (owner b2) supersedes the old "opens nothing" guard: a customer row opens its products.
    assert OLD_TOOL not in _names(log) and sorted(a["group_by"] for a in _ran(log)) == ["month", "product"], (text, log)


# ---------------------------------------------------------------- review: one reply, and the printed code picks a row


def test_r3c_review_2_an_item_detail_over_the_limit_splits_as_one_reply(console, monkeypatch) -> None:
    import re

    many = {**ROWS, "customer": [{"rank": i, "name": f"ZZT CUSTOMER {i:04d} SDN BHD", "qty": 500 - i, "amount": 5000.0 - i,
                                  "keys": [f"cust-{i}"]} for i in range(1, 301)],
            "month": [{"rank": i, "name": f"2026-{i:02d}", "qty": 5, "amount": 50.0, "keys": []} for i in range(1, 13)]}
    monkeypatch.setattr(lane_tests, "_fake_body", lambda args: {**_body(args), "rows": many.get(args.get("group_by"), []),
                                                              "total_count": len(many.get(args.get("group_by"), []))})
    from app.services.chatbot import console_service

    _on_screen(console, monkeypatch)
    results: list[Any] = []
    real = console_service.run_console_turn
    monkeypatch.setattr(console_service, "run_console_turn", lambda *a, **k: results.append(real(*a, **k)) or results[-1])
    text, log = _say_all(console, monkeypatch, _pick(2), "2")
    assert len(_ran(log)) == 2, (text, log)
    parts = [results[-1].reply_text, *results[-1].send_messages]  # the parts the customer gets, in order
    assert len(parts) > 1 and all(len(p) <= 3900 for p in parts), [len(p) for p in parts]
    marks = [re.match(r"\((\d+)/(\d+)\)", p) for p in parts]
    assert all(marks), [p[:12] for p in parts]
    assert [int(m.group(1)) for m in marks] == list(range(1, len(parts) + 1)), [m.group(0) for m in marks]
    assert {int(m.group(2)) for m in marks} == {len(parts)}, [m.group(0) for m in marks]  # one numbering for the whole detail
    joined = "\n".join(parts)
    assert "ZZT CUSTOMER 0001" in joined and "Dec 2026" in joined, "both halves are in the reply"


def test_r3c_review_3_typing_a_category_rows_printed_code_picks_that_row(console, monkeypatch) -> None:
    from tests.chatbot.test_report_ask_lane import _e

    coded = {"product": ROWS["product"], "customer": ROWS["customer"], "month": ROWS["month"],
             "category": [{"rank": 1, "name": "ZZ Category A", "code": "ZZCATA", "qty": 39, "amount": 399.0, "keys": [C1]},
                          {"rank": 2, "name": "ZZ Category B", "code": "ZZCATB", "qty": 38, "amount": 398.0, "keys": [C2]}]}
    monkeypatch.setattr(lane_tests, "_fake_body", lambda args: {**_body(args), "rows": coded.get(args.get("group_by"), [])})
    text = _on_screen(console, monkeypatch, "category")
    assert "1. ZZCATA" in text, text  # the ranking prints the code
    typed = _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", entities=[_e("ZZCATA", "category")],
        order_status=None, domain_in_message=False, state_changes=[{"op": "answer", "axis": None, "position": None}])
    text, log = _say_all(console, monkeypatch, typed, "ZZCATA")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "product" and ran[0].get("category_ids") == [C1], ran
