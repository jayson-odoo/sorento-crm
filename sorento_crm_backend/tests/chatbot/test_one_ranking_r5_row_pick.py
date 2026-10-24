"""REPORT-SMART-L R5 B (owner ruling 24 Oct, b2): a rank number after a sales agent or customer ranking opens
that row's detail on the report engine (agent -> its customers, customer -> its products, each plus by month),
the period, product, basis, measure and other filters held; guards for what arms no pick. Fake names only."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_one_ranking_r3c as r3c
from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _names, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

OFFER_AGENT = "Reply with a rank number to see that sales agent's customers and months."
OFFER_CUSTOMER = "Reply with a rank number to see that customer's products and months."
A1, A2 = "cccccccc-0000-4000-8000-000000000001", "cccccccc-0000-4000-8000-000000000002"
K1, K2 = "dddddddd-0000-4000-8000-000000000001", "dddddddd-0000-4000-8000-000000000002"


def _rows(names: list[str], keys: list[list[str]]) -> list[dict[str, Any]]:
    return [{"rank": i, "name": n, "qty": 40 - i, "amount": 400.0 - i, "keys": k} for i, (n, k) in enumerate(zip(names, keys), 1)]


ROWS = {
    **r3c.ROWS,
    "sales_agent": _rows(["ZZT AGENT ONE", "ZZT AGENT TWO"], [[A1], [A2]]),
    "customer": _rows(["ZZT CUSTOMER ONE", "ZZT CUSTOMER TWO"], [[K1], [K2]]),
    "brand": _rows(["ZZT BRAND ONE"], [["eeeeeeee-0000-4000-8000-000000000001"]]),
    "channel": _rows(["dealer"], [["dealer"]]),
    "location": _rows(["ZZT WAREHOUSE"], [["ZZW"]]),
}


def _body(args: dict[str, Any]) -> dict[str, Any]:
    out = r3c._body(args)
    group_by = args.get("group_by")
    out["rows"] = ROWS.get(group_by, []) if group_by else []
    out["total_count"] = len(out["rows"])
    if args.get("compare_to"):
        out["compare_to"] = args["compare_to"]
    return out


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _ranking(group_by: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        order_status="sales_ranking", rank_group=None, entities=[_e(PRODUCT_CODE, "product")], top_n=5)
    base.update(over)
    return r3c._ranking(group_by, **base)


def _on_screen(console, monkeypatch, group_by: str, **over: Any) -> str:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _ranking(group_by, **over), f"top 5 {group_by} in 2026 for {PRODUCT_CODE}")
    assert len(r3c._ran(log)) == 1, ("setup", text, log)
    return text


def _no_pick(position: int) -> dict[str, Any]:
    return {**r3c._pick(position), "open_question_answer": {"mode": None, "picked": [], "items": [], "qty_for_all": None}}


def test_b1_an_agent_row_pick_opens_that_agents_customers_and_months(console, monkeypatch) -> None:
    text = _on_screen(console, monkeypatch, "sales_agent")
    assert OFFER_AGENT in text, text
    text, log = _say_all(console, monkeypatch, r3c._pick(2), "2")
    assert "I can rank sales by" not in text, text
    ran = r3c._ran(log)
    assert sorted(a.get("group_by") for a in ran) == ["customer", "month"], (text, log)
    for args in ran:
        assert args.get("sales_agent_ids") == [A2], args
        assert args.get("product_code") == PRODUCT_CODE, args
        assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
        assert args["basis"] == "delivered" and args["measure"] == "qty", args


def test_b2_a_customer_row_pick_opens_that_customers_products_and_months(console, monkeypatch) -> None:
    text = _on_screen(console, monkeypatch, "customer")
    assert OFFER_CUSTOMER in text, text
    text, log = _say_all(console, monkeypatch, r3c._pick(1), "1")
    assert "I can rank sales by" not in text, text
    ran = r3c._ran(log)
    assert sorted(a.get("group_by") for a in ran) == ["month", "product"], (text, log)
    for args in ran:
        assert args.get("customer_ids") == [K1], args
        assert args["date_from"] == "2026-01-01" and args["basis"] == "delivered" and args["measure"] == "qty", args


def test_b3_the_offer_lines_are_catalogued_in_malay_and_chinese() -> None:
    from app.services.chatbot import label_catalog

    for line in (OFFER_AGENT, OFFER_CUSTOMER):
        entry = label_catalog.LABELS.get(line) or {}
        assert entry.get("ms") and entry.get("zh"), line
        assert label_catalog.Localizer("ms", {line: entry["ms"]}).text(line) == entry["ms"]


def test_b4_guard_item_and_category_picks_are_unchanged(console, monkeypatch) -> None:
    _on_screen(console, monkeypatch, "product", order_status="top_selling", rank_group="item", entities=[])
    text, log = _say_all(console, monkeypatch, r3c._pick(2), "2")
    assert sorted(a.get("group_by") for a in r3c._ran(log)) == ["customer", "month"], (text, log)


def test_b4_guard_a_compare_to_ranking_arms_no_pick(console, monkeypatch) -> None:
    text = _on_screen(console, monkeypatch, "sales_agent", compare_to="last_year")
    assert OFFER_AGENT not in text, text
    text, log = _say_all(console, monkeypatch, r3c._pick(1), "1")
    assert r3c._ran(log) == [], (text, log)


@pytest.mark.parametrize("group_by", ["month", "brand", "channel", "location"])
def test_b4_guard_other_axes_arm_no_pick(console, monkeypatch, group_by) -> None:
    text = _on_screen(console, monkeypatch, group_by)
    assert "Reply with a rank number" not in text, text
    text, log = _say_all(console, monkeypatch, r3c._pick(1), "1")
    assert r3c._ran(log) == [], (text, log)


def test_b4_pin_gemini_no_pick_shape_for_a_number_still_opens_the_row(console, monkeypatch) -> None:
    """open_question_answer mode null, picked []: the pickers' decide still reads the number from the
    reference positions, so the row opens (pinned: the parser's mode is not what arms the pick)."""
    _on_screen(console, monkeypatch, "sales_agent")
    text, log = _say_all(console, monkeypatch, _no_pick(2), "2")
    assert sorted(a.get("group_by") for a in r3c._ran(log)) == ["customer", "month"], (text, log)


def test_b5_guard_axis_less_top_sales_asks_only_the_basis_then_runs_a_total(console, monkeypatch) -> None:
    _state_on(console)
    first = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", rank_direction="top",
        ranking_refine=False, group_by=None, top_n=None, measure=None, basis=None,
        entities=[_e(PRODUCT_CODE, "product")], domain_in_message=True, state_changes=list(KEEP), **r3c.YEAR_2026)
    text, log = _say_all(console, monkeypatch, first, f"Top sales for {PRODUCT_CODE} in 2026")
    assert r3c._ran(log) == [], (text, log)
    assert "delivered" in text.lower() and "rank sales by" not in text and "By what" not in text, text
    assert "How many" not in text and "Which period" not in text, text
    answer = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by=None, top_n=None, measure=None, basis="delivered", entities=[], domain_in_message=False,
        state_changes=[{"op": "answer", "axis": None, "position": None}],
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None})
    text, log = _say_all(console, monkeypatch, answer, "delivered")
    ran = r3c._ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and ran[0]["basis"] == "delivered", (text, log)


# ------------------------------------------------ review: no offer on a detail, scope pins


@pytest.mark.parametrize(
    ("group_by", "over", "position"),
    [("product", {"order_status": "top_selling", "rank_group": "item", "entities": []}, 2), ("sales_agent", {}, 2), ("customer", {}, 1)],
)
def test_b6_a_row_detail_prints_no_offer_for_a_list_it_never_armed(console, monkeypatch, group_by, over, position) -> None:
    _on_screen(console, monkeypatch, group_by, **over)
    text, log = _say_all(console, monkeypatch, r3c._pick(position), str(position))
    assert len(r3c._ran(log)) == 2, (text, log)
    assert "Reply with a rank number" not in text, text


def test_b6_the_ranking_itself_still_prints_its_offer(console, monkeypatch) -> None:
    assert OFFER_AGENT in _on_screen(console, monkeypatch, "sales_agent")


def test_b7_a_customer_row_detail_keeps_the_held_product(console, monkeypatch) -> None:
    _on_screen(console, monkeypatch, "customer")
    _text, log = _say_all(console, monkeypatch, r3c._pick(1), "1")
    assert all(a.get("product_code") == PRODUCT_CODE for a in r3c._ran(log)), log


def test_b8_the_detail_axis_must_match_the_ranking_on_screen() -> None:
    from app.services.chatbot.lanes.business import report_ask

    frame = {"group_by": "sales_agent", "date_from": "2026-01-01", "date_to": "2026-12-31", "basis": "delivered", "measure": "qty"}
    agreeing = {"sales_ranking_frame": frame, "ranking_detail": {"group_by": "sales_agent", "name": "x", "keys": [A1]}}
    outcome, _line = report_ask.settle(None, agreeing, [])
    assert outcome is not None and outcome.extras.get("detail") is True and outcome.extras["args"]["sales_agent_ids"] == [A1]
    mismatch = {"sales_ranking_frame": frame, "ranking_detail": {"group_by": "customer", "name": "x", "keys": [K1]}}
    outcome, _line = report_ask.settle(None, mismatch, [])
    assert outcome is None or not outcome.extras.get("detail"), outcome


def test_b9_my_ranking_pick_keeps_mine_in_the_detail(console, monkeypatch) -> None:
    _on_screen(console, monkeypatch, "customer", self_reference=True)
    first = r3c._ran(_say_all(console, monkeypatch, r3c._pick(1), "1")[1])
    assert first and all(a.get("mine") is True for a in first), first


def test_b10_a_refused_product_detail_is_said_as_the_refusal(console, monkeypatch) -> None:
    message = "You can only see sales for your own account."
    _on_screen(console, monkeypatch, "customer")
    console.refuse = {"message": message, "detail": None, "code": "customer_not_permitted"}
    text, log = _say_all(console, monkeypatch, r3c._pick(1), "1")
    assert text.strip() == message, (text, log)


def test_b11_the_roster_rows_carry_the_axis_as_their_entity_type() -> None:
    from app.services.chatbot.lanes.business import fetch

    for group_by, entity_type in (("sales_agent", "sales_agent"), ("customer", "customer"), ("product", "product"), ("category", "category")):
        out = fetch._report_ask_output(
            {"response": "x\n\n1. A", "drill_rows": {"group_by": group_by, "rows": [{"name": "A", "keys": ["k"]}]}},
            {"semantic_input": {"report_ask_args": {"group_by": group_by}}})
        rows = out["outstanding_ask"]["last_result_set"]
        assert [r["entity_type"] for r in rows] == [entity_type], (group_by, rows)
