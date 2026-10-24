"""REPORT-SMART-L R7 (EVAL-BENCH 1024g, flash-lite 6dbed193 / aaf0b04d): a measure typed in the answer to a TOTAL's
question is kept. Real engine seam, the live parse shapes. Fake codes."""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_one_ranking_r5_axis_refine import ANSWER_OP, SET, YEAR_2026, _ran, _verdict
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _e, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

NO_ANSWER = {"mode": None, "items": [], "picked": [], "qty_for_all": None}


def _row1() -> dict[str, Any]:
    """'Top sales for <product> in 2026': a total, no basis, no measure."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by=None, basis=None, measure=None, rank_by=None, top_n=None, entities=[_e(PRODUCT_CODE, "product")],
        domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)


def _row2(**over: Any) -> dict[str, Any]:
    base = dict(basis="delivered", measure=None, rank_by="quantity", group_by=None, ranking_refine=None, top_n=None,
                entities=[], entity_op="reuse", state_changes=list(ANSWER_OP), open_question_answer=dict(NO_ANSWER))
    base.update(over)
    return _verdict(**base)


def _axis(group_by: str, **over: Any) -> dict[str, Any]:
    base = dict(group_by=group_by, ranking_refine=True, basis="delivered", measure=None, rank_by=None, top_n=None,
                entities=[], entity_op="replace_combine",
                state_changes=[{"op": "set", "axis": group_by, "position": None}])
    base.update(over)
    return _verdict(**base)


def _total_then_answer(console, monkeypatch, answer: dict[str, Any]):
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _row1(), f"Top sales for {PRODUCT_CODE} in 2026")
    assert _ran(log) == [] and "Delivered" in text, ("setup", text, log)
    return _say_all(console, monkeypatch, answer, "qty, delivered")


def _flow(console, monkeypatch, answer: dict[str, Any]) -> None:
    text, log = _total_then_answer(console, monkeypatch, answer)
    ran = _ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and ran[0]["measure"] == "qty", (text, log)
    assert "Total 30 pcs, RM 1,200.00" in text, text  # the typed measure is listed first
    assert ran[0]["basis"] == "delivered" and ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran
    text, log = _say_all(console, monkeypatch, _axis("sales_agent"), "by salesppl")
    low = text.lower()
    assert _ran(log) == [] and "How many?" in text, (text, log)
    assert "quantity or" not in low and "measure" not in low and text.count("?") == 1, text
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 5, (text, log)
    assert ran[0]["measure"] == "qty" and ran[0]["basis"] == "delivered", ran
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran


def test_r7_1_flash_lite_rank_by_only_is_kept_through_the_next_axis(console, monkeypatch) -> None:
    _flow(console, monkeypatch, _row2())


def test_r7_2_mini_measure_qty_is_kept_through_the_next_axis(console, monkeypatch) -> None:
    _flow(console, monkeypatch, _row2(measure="qty"))


def test_r7_3_a_second_axis_while_how_many_is_open_still_asks_only_the_count(console, monkeypatch) -> None:
    _total_then_answer(console, monkeypatch, _row2())
    text, log = _say_all(console, monkeypatch, _axis("sales_agent"), "by salesppl")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _axis("customer"), "by customer")
    assert _ran(log) == [] and "How many?" in text and "quantity or" not in text.lower() and text.count("?") == 1, (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["measure"] == "qty", (text, log)


def test_r7_4_guard_an_answer_naming_no_measure_leaves_the_total_and_the_ranking_as_today(console, monkeypatch) -> None:
    text, log = _total_then_answer(console, monkeypatch, _row2(rank_by=None))
    ran = _ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and "measure" not in ran[0], (text, log)
    text, log = _say_all(console, monkeypatch, _axis("sales_agent"), "by salesppl")
    assert _ran(log) == [] and "How many?" in text and text.count("?") >= 2, (text, log)


def test_r7_5_guard_a_typed_count_on_the_total_answer_changes_nothing(console, monkeypatch) -> None:
    text, log = _total_then_answer(console, monkeypatch, _row2(top_n=10))
    ran = _ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and "top_n" not in ran[0], (text, log)


# ------------------------------------------------ review: a reply that fills no owed field is not the answer

BASIS_ONLY = "Delivered, ordered or outstanding?"
SWAP_ASKS = "1. How many? For example top 5.\n2. Delivered, ordered or outstanding?"


def _delivered(console, monkeypatch):
    v = _verdict(basis="delivered", ranking_refine=None, state_changes=list(ANSWER_OP), open_question_answer=dict(NO_ANSWER))
    return _say_all(console, monkeypatch, v, "delivered")


def _open_total(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _row1(), f"Top sales for {PRODUCT_CODE} in 2026")
    assert _ran(log) == [] and BASIS_ONLY in text, ("setup", text, log)


def test_r7_6_guard_a_new_axis_with_a_measure_still_swaps_into_the_open_ask(console, monkeypatch) -> None:
    _open_total(console, monkeypatch)
    v = _axis("sales_agent", measure="qty", basis=None)
    text, log = _say_all(console, monkeypatch, v, "by salesppl, qty")
    assert _ran(log) == [] and text == SWAP_ASKS, (text, log)
    text, log = _delivered(console, monkeypatch)
    assert _ran(log) == [] and text == "How many? For example top 5.", (text, log)


def test_r7_7_guard_a_fresh_ranking_with_a_measure_is_not_the_totals_answer(console, monkeypatch) -> None:
    _open_total(console, monkeypatch)
    v = _verdict(group_by="sales_agent", ranking_refine=False, measure="qty", basis=None, top_n=5,
                 domain_in_message=True, state_changes=list(SET), **YEAR_2026)
    text, log = _say_all(console, monkeypatch, v, "top 5 salesman by qty 2026")
    assert _ran(log) == [] and text == BASIS_ONLY, (text, log)
    text, log = _delivered(console, monkeypatch)
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 5, (text, log)
    assert ran[0]["measure"] == "qty" and ran[0]["basis"] == "delivered", ran


def test_r7_8_guard_a_comparison_with_a_measure_keeps_its_comparison(console, monkeypatch) -> None:
    _open_total(console, monkeypatch)
    v = _verdict(compare_to="last_year", measure="qty", basis=None, ranking_refine=None, state_changes=list(ANSWER_OP))
    text, log = _say_all(console, monkeypatch, v, "vs last year, qty")
    assert _ran(log) == [] and text == BASIS_ONLY, (text, log)
    text, log = _delivered(console, monkeypatch)
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["compare_to"] == "last_year" and not ran[0].get("group_by"), (text, log)
    assert "measure" not in ran[0] and ran[0]["basis"] == "delivered", ran
