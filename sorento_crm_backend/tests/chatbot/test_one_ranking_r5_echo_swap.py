"""REPORT-SMART-L R5 (EVAL-BENCH v103 refold, flash-lite a342e9f0 / b491ba35, mini 7928e3b7): the open ask's own axis
said again is re-asked with no miss line (R3); an axis change the parser flags neither refine nor fresh swaps in (R4);
a sales ranking's `status` that is a report basis is its basis (R10). Real engine seam, the live shapes. Fake codes."""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_one_ranking_r5_axis_refine import ANSWER_OP, YEAR_2026, _open_how_many, _ran, _verdict
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

FILL = {"mode": "fill", "picked": [], "items": [], "qty_for_all": None}


def _echo(group_by: str, **over: Any) -> dict[str, Any]:
    """The live reply: the axis typed, ranking_refine null, the `answer` op, mode fill, nothing filled, no entity."""
    base = dict(ranking_refine=None, state_changes=list(ANSWER_OP), open_question_answer=dict(FILL))
    base.update(over)
    return _verdict(group_by=group_by, **base)


def test_r3_the_held_axis_said_again_is_asked_again_with_no_miss_line(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _echo("sales_agent"), "by salesppl")
    assert _ran(log) == [] and "How many?" in text and "as a number" not in text, (text, log)
    text, log = _say_all(console, monkeypatch, _echo("sales_agent"), "by salesppl")
    ran = _ran(log)  # a second echo is a second miss: the default top 10 runs, as today
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 10, (text, log)


def test_r3_then_r4_the_new_axis_swaps_in_and_the_count_runs_with_the_filters(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _echo("sales_agent"), "by salesppl")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    r4 = _echo("customer", state_changes=[*ANSWER_OP, {"op": "set", "axis": "group_by", "position": None}])
    text, log = _say_all(console, monkeypatch, r4, "by customer")
    assert _ran(log) == [] and "How many?" in text and "as a number" not in text, (text, log)
    assert "Which period" not in text and "Delivered" not in text, text  # only the count is owed
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran
    assert ran[0]["measure"] == "qty" and ran[0]["basis"] == "delivered", ran


def test_r4_guard_the_same_reply_flagged_a_fresh_ask_is_a_new_ask(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    r4 = _echo("customer", ranking_refine=False, state_changes=[*ANSWER_OP, {"op": "set", "axis": "group_by", "position": None}])
    text, log = _say_all(console, monkeypatch, r4, "by customer")
    assert _ran(log) == [] and "Which period?" in text, (text, log)


def test_r4_guard_a_new_subject_is_a_new_ask_whatever_the_refine_flag(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    r4 = _echo("customer", state_changes=[{"op": "new_subject", "axis": None, "position": None}])
    text, log = _say_all(console, monkeypatch, r4, "by customer")
    assert _ran(log) == [] and "Which period?" in text, (text, log)


def test_r10_a_ranking_whose_status_is_a_basis_runs_on_that_basis(console, monkeypatch) -> None:
    _state_on(console)
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", status="outstanding",
        group_by="sales_agent", top_n=5, measure="qty", basis="outstanding", ranking_refine=False,
        entities=[_e(PRODUCT_CODE, "product")], domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
    text, log = _say_all(console, monkeypatch, qf, "Top 5 salesppl in 2026 for cb6635, by qty, outstanding")
    assert "which document" not in text.lower(), text
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["basis"] == "outstanding" and ran[0]["group_by"] == "sales_agent", (text, log)
    assert ran[0]["top_n"] == 5, ran


def test_r10_guard_only_a_sales_ranking_status_becomes_a_basis() -> None:
    from app.services.chatbot.lanes.business import report_ask

    plain = {"order_status": "outstanding", "status": "outstanding", "basis": None}
    assert report_ask.status_as_basis(plain) == plain
    ranked = report_ask.status_as_basis({"order_status": "sales_ranking", "status": "outstanding", "document": ["SO"], "basis": None})
    assert ranked["basis"] == "outstanding" and "status" not in ranked and "document" not in ranked, ranked
    kept = report_ask.status_as_basis({"order_status": "sales_ranking", "status": "outstanding", "basis": "ordered"})
    assert kept["basis"] == "ordered", kept
    pending = {"order_status": "sales_ranking", "status": "pending", "basis": None}
    assert report_ask.status_as_basis(pending) == pending


# ------------------------------------------------ review: the reply's own values win over the held ones

import pytest  # noqa: E402

YEAR_2025 = {"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"}


def _swap_reply(refine: Any, **over: Any) -> dict[str, Any]:
    return _echo("customer", ranking_refine=refine, state_changes=[*ANSWER_OP, {"op": "set", "axis": "group_by", "position": None}], **over)


def _then_top5():
    return _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP)


@pytest.mark.parametrize("refine", [None, True])
def test_r34b_1_a_period_typed_with_the_new_axis_wins_over_the_held_one(console, monkeypatch, refine) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _swap_reply(refine, **YEAR_2025), "customers 2025")
    assert _ran(log) == [] and "How many?" in text and "Which period" not in text, (text, log)
    text, log = _say_all(console, monkeypatch, _then_top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, (text, log)
    assert ran[0]["date_from"] == "2025-01-01" and ran[0]["date_to"] == "2025-12-31", ran
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["basis"] == "delivered" and ran[0]["measure"] == "qty", ran


@pytest.mark.parametrize("field, value", [("measure", "amount"), ("basis", "ordered")])
def test_r34b_2_a_measure_or_basis_typed_with_the_new_axis_wins(console, monkeypatch, field, value) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _swap_reply(None, **{field: value}), "customers " + value)
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _then_top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0][field] == value and ran[0]["group_by"] == "customer", (text, log)
    assert ran[0]["date_from"] == "2026-01-01" and ran[0]["product_code"] == PRODUCT_CODE, ran
    other, held = ("basis", "delivered") if field == "measure" else ("measure", "qty")
    assert ran[0][other] == held, ran


@pytest.mark.parametrize("mode", [{"mode": "fill", "picked": [], "items": [], "qty_for_all": None}, None], ids=["fill", "null"])
@pytest.mark.parametrize("axis", ["sales_agent", "customer"], ids=["echo", "swap"])
def test_r34b_3_a_channel_typed_with_the_axis_is_kept(console, monkeypatch, axis, mode) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _echo(axis, sales_channel="dealer", open_question_answer=mode), "by it dealer only")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _then_top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == axis and ran[0].get("channel") == "dealer", (text, log)


def test_r34b_4_a_new_subject_op_is_a_new_ask_with_the_state_applier_off(console, monkeypatch) -> None:
    """Without the State prompt nothing drops the open ask on `new_subject`: `_swappable` itself must."""
    from app.services.chatbot.lanes.business import report_ask

    extras = {"args": {"group_by": "sales_agent"}}
    slot_reply = _echo("customer", state_changes=[{"op": "new_subject", "axis": None, "position": None}])
    assert report_ask.names_its_own_ask(slot_reply, {"extras": extras}) is True
    plain = _echo("customer")
    assert report_ask.names_its_own_ask(plain, {"extras": extras}) is False


@pytest.mark.parametrize("mode", [{"mode": "fill", "picked": [], "items": [], "qty_for_all": None}, None], ids=["fill", "null"])
def test_r34b_5_a_forged_engine_channel_key_from_the_parser_is_never_applied(console, monkeypatch, mode) -> None:
    _open_how_many(console, monkeypatch)
    forged = _echo("customer", open_question_answer=mode, required_ask_channel="project")
    text, log = _say_all(console, monkeypatch, forged, "by customer")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _then_top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and not ran[0].get("channel"), (text, log)
