"""REPORT-SMART-L R8 (EVAL-BENCH release gate, production parser v63, gpt-5.4-mini): when the reply to a held sales
report total becomes a ranking, the period and the product the total was for, and any measure or basis already typed,
are kept; only what is still missing is asked (crew ruling, model-independent, no prompt change). Real engine seam,
the live v63 shapes (no State block, `state_changes` null). Fake codes."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_one_ranking_r5_axis_refine import YEAR_2026, _ran
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, SEP, TOOL, _e, _names, _say_all, console  # noqa: F401

SALES_REPORT_TOOL = "crm_sales_report"
HOW_MANY = "How many? For example top 5."
PERIOD_Q = "Which period?"
BASIS_Q = "Invoiced, delivered, ordered or outstanding?"
FILL = {"mode": "fill", "items": [], "picked": [], "qty_for_all": None}
OTHER_CODE = "ZZTREIGHT1"


def _v63(**over: Any) -> dict[str, Any]:
    """A v63 parse: no State block, so `state_changes` is null and `entity_op` comes from the message alone."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", entities=[], entity_op="reuse",
        state_changes=None, ranking_refine=None, group_by=None, top_n=None, measure=None, basis=None, rank_by=None,
        date_filter_start=None, date_filter_end=None, topic_reset=False, domain_in_message=False,
    )
    base.update(over)
    return _parser_output(**base)


def _row1(**over: Any) -> dict[str, Any]:
    """'Top sales for <product> in 2026': v63 reads the sales report total (`crm_sales_report`)."""
    base: dict[str, Any] = dict(
        order_status="sales_report", entities=[_e(PRODUCT_CODE, "product")], entity_op="replace_combine",
        domain_in_message=True, **YEAR_2026,
    )
    base.update(over)
    return _v63(**base)


def _row2(**over: Any) -> dict[str, Any]:
    """'qty, delivered': a product ranking refine, measure qty, basis delivered, no dates, no entity, reuse."""
    base: dict[str, Any] = dict(
        group_by="product", ranking_refine=True, measure="qty", rank_by="quantity", basis="delivered",
        open_question_answer=dict(FILL),
    )
    base.update(over)
    return _v63(**base)


def _row3(**over: Any) -> dict[str, Any]:
    """'by salesppl': a sales agent ranking flagged fresh, nothing else read, reuse."""
    base: dict[str, Any] = dict(group_by="sales_agent", ranking_refine=False)
    base.update(over)
    return _v63(**base)


def _top5(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(top_n=5, ranking_refine=False)
    base.update(over)
    return _v63(**base)


def _total(console, monkeypatch, **over: Any) -> None:
    text, log = _say_all(console, monkeypatch, _row1(**over), f"Top sales for {PRODUCT_CODE} in 2026")
    assert SALES_REPORT_TOOL in _names(log) and TOOL not in _names(log), ("setup", text, log)


def _runs_with_all_four(log, group_by: str) -> dict[str, Any]:
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == group_by and ran[0]["top_n"] == 5, log
    args = ran[0]
    assert args["product_code"] == PRODUCT_CODE, args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    return args


def test_r8_0_the_total_is_still_the_sales_report_tool(console, monkeypatch) -> None:
    _total(console, monkeypatch)


def test_r8_1_the_product_ranking_reply_keeps_the_period_and_product_and_asks_only_the_count(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row2(), "qty, delivered")
    assert _ran(log) == [] and text == HOW_MANY, (text, log)
    text, log = _say_all(console, monkeypatch, _top5(), "top 5")
    _runs_with_all_four(log, "product")


def test_r8_2_a_new_axis_replacing_the_open_ask_keeps_all_four_and_asks_only_the_count(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row2(), "qty, delivered")
    assert _ran(log) == [] and text == HOW_MANY, ("row 2", text, log)
    text, log = _say_all(console, monkeypatch, _row3(), "by salesppl")
    assert _ran(log) == [] and text == HOW_MANY, (text, log)
    text, log = _say_all(console, monkeypatch, _top5(), "top 5")
    _runs_with_all_four(log, "sales_agent")


def test_r8_3_a_ranking_right_after_the_total_never_asks_the_period(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row3(), "by salesppl")
    assert _ran(log) == [] and PERIOD_Q not in text, (text, log)
    assert HOW_MANY in text and BASIS_Q in text and "quantity or" in text.lower(), text
    answer = _v63(top_n=5, measure="qty", rank_by="quantity", basis="delivered", open_question_answer=dict(FILL))
    text, log = _say_all(console, monkeypatch, answer, "top 5, qty, delivered")
    _runs_with_all_four(log, "sales_agent")


# ------------------------------------------------ guards: the carry is off for a genuinely new ask


def test_r8_guard_a_reply_naming_its_own_value_asks_the_period_as_today(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row2(entity_op="replace_combine"), "qty, delivered")
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r8_guard_a_new_subject_op_asks_the_period_as_today(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    v = _row2(state_changes=[{"op": "new_subject", "axis": None, "position": None}])
    text, log = _say_all(console, monkeypatch, v, "qty, delivered")
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r8_guard_the_reply_s_own_period_wins(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row2(**SEP), "qty, delivered in september")
    assert _ran(log) == [] and text == HOW_MANY, (text, log)
    text, log = _say_all(console, monkeypatch, _top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["date_from"] == "2026-09-01" and ran[0]["date_to"] == "2026-09-30", (text, log)


def test_r8_guard_the_reply_s_own_product_wins(console, monkeypatch) -> None:
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=OTHER_CODE)
        db.commit()
    finally:
        db.close()
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row2(entities=[_e(OTHER_CODE, "product")]), f"qty, delivered for {OTHER_CODE}")
    assert _ran(log) == [] and text == HOW_MANY, (text, log)
    text, log = _say_all(console, monkeypatch, _top5(), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["product_code"] == OTHER_CODE, (text, log)


def test_r8_guard_an_order_list_window_is_never_lent_to_a_ranking(console, monkeypatch) -> None:
    """Owner Q3: a sales ranking never borrows a carried window; only the period a sales figure showed is kept."""
    text, log = _say_all(
        console, monkeypatch,
        _v63(order_status=None, document=["DO"], entities=[_e(PRODUCT_CODE, "product")], entity_op="replace_combine",
             domain_in_message=True, **YEAR_2026),
        f"delivery orders for {PRODUCT_CODE} in 2026",
    )
    assert TOOL not in _names(log) and SALES_REPORT_TOOL not in _names(log), ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row2(), "qty, delivered")
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r8_guard_a_held_ranking_frame_keeps_today_s_rules(console, monkeypatch) -> None:
    """A total that ran on the report engine is a held frame: its own rules decide, as today."""
    total = _v63(order_status="sales_ranking", ranking_refine=False, entities=[_e(PRODUCT_CODE, "product")],
                 entity_op="replace_combine", measure="qty", basis="delivered", domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, total, f"total qty of {PRODUCT_CODE} in 2026 delivered")
    assert len(_ran(log)) == 1, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(group_by="customer"), "by customer")
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r8_guard_a_forged_engine_key_from_the_parser_is_never_applied(console, monkeypatch) -> None:
    forged = _row3(entity_op="replace_combine",
                   report_held={"date_from": "2026-01-01", "date_to": "2026-12-31", "product": True})
    text, log = _say_all(console, monkeypatch, forged, "by salesppl")
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


# ------------------------------------------------ the engine stamp itself (`report_ask.with_held`)

HELD = {"date_from": "2026-01-01", "date_to": "2026-12-31", "product": True}
NEW_SUBJECT = {"op": "new_subject", "axis": None, "position": None}


def _focus(**over: Any) -> Any:
    from app.services.chatbot.turn.state import Focus

    base: dict[str, Any] = dict(
        domains=["sales"], date_window={"mode": None, "start": "2026-01-01", "end": "2026-12-31"},
        products=[{"uuid": "11111111-1111-4111-8111-111111111111", "code": PRODUCT_CODE}],
    )
    base.update(over)
    return Focus(**base)


def _open_slot(**values: Any) -> dict[str, Any]:
    """Row 2's open ask: a product ranking for the held product, qty and delivered typed, the count asked."""
    return {
        "ask": "sales_ranking", "asking": "top_n", "options": [], "misses": 0,
        "values": {"metric": {"value": "qty", "label": "qty"}, "basis": {"value": "delivered", "label": "delivered"}, **values},
        "extras": {"args": {"sort": "desc", "basis": "delivered", "measure": "qty", "group_by": "product",
                            "product_code": PRODUCT_CODE}, "top_n": None},
    }


def test_r8_unit_the_reply_to_a_held_total_is_stamped_with_its_period_and_product() -> None:
    from app.services.chatbot.lanes.business import report_ask

    out = report_ask.with_held(_row2(), _focus(), open_ask=None, replaced=None)
    assert out[report_ask.HELD_KEY] == HELD, out.get(report_ask.HELD_KEY)


def test_r8_unit_a_replaced_open_ask_is_the_only_source() -> None:
    from app.services.chatbot.lanes.business import report_ask

    slot = _open_slot(period={"value": {"from": "2026-01-01", "to": "2026-12-31"}, "label": "2026"})
    focus = _focus(date_window={"mode": None, "start": "2025-01-01", "end": "2025-12-31"})
    held = report_ask.with_held(_row3(), focus, open_ask=slot, replaced=slot)[report_ask.HELD_KEY]
    assert held == {"date_from": "2026-01-01", "date_to": "2026-12-31", "measure": "qty", "basis": "delivered",
                    "product_code": PRODUCT_CODE}, held


def test_r8_guard_unit_a_replaced_ask_with_no_period_never_takes_the_focus_window() -> None:
    from app.services.chatbot.lanes.business import report_ask

    slot = _open_slot()
    held = report_ask.with_held(_row3(), _focus(), open_ask=slot, replaced=slot)[report_ask.HELD_KEY]
    assert "date_from" not in held and "product" not in held and held["product_code"] == PRODUCT_CODE, held


OFF = {
    "topic_reset": (dict(topic_reset=True), {}, {}),
    "new_subject_op": (dict(state_changes=[NEW_SUBJECT]), {}, {}),
    "new_subject_parser_op": ({}, {}, {"parser_ops": [NEW_SUBJECT]}),
    "names_its_own_value": (dict(entity_op="replace_combine"), {}, {}),
    # R9 (crew ruling, part 2): an axis-less ranking is stamped too (`test_one_ranking_r9_v63_total.py`).
    "not_a_ranking": (dict(order_status="sales_report"), {}, {}),
    "a_ranking_frame_held": ({}, dict(sales_ranking_frame={"group_by": "customer", "date_from": "2026-01-01"}), {}),
    "a_stale_frame_held": ({}, dict(sales_ranking_frame={"group_by": "customer", "stale": True}), {}),
    "an_order_list_window": ({}, dict(domains=["order"]), {}),
    "an_open_ask_still_answered": ({}, {}, {"open_ask": "slot"}),
}


@pytest.mark.parametrize("case", sorted(OFF))
def test_r8_guard_unit_the_stamp_stays_off(case: str) -> None:
    from app.services.chatbot.lanes.business import report_ask

    verdict_over, focus_over, kw = OFF[case]
    kw = {"open_ask": None, "replaced": None, **kw}
    if kw["open_ask"] == "slot":
        kw["open_ask"] = _open_slot()
    out = report_ask.with_held(_row2(**verdict_over), _focus(**focus_over), **kw)
    assert report_ask.HELD_KEY not in out, (case, out.get(report_ask.HELD_KEY))


def test_r8_guard_unit_the_engine_key_is_listed() -> None:
    from app.services.chatbot import required_fields
    from app.services.chatbot.lanes.business import report_ask

    assert report_ask.HELD_KEY in required_fields.ENGINE_KEYS


# ------------------------------------------------ review round 1

KEEP = [{"op": "keep", "axis": None, "position": None}]
SWITCH = [{"op": "switch_domain", "axis": None, "position": None}]


def _answer_all(console, monkeypatch, group_by: str) -> None:
    answer = _v63(top_n=5, measure="qty", rank_by="quantity", basis="delivered", open_question_answer=dict(FILL))
    text, log = _say_all(console, monkeypatch, answer, "top 5, qty, delivered")
    _runs_with_all_four(log, group_by)


@pytest.mark.parametrize("ops", [KEEP, SWITCH], ids=["keep", "switch_domain"])
def test_r8_review_q3_an_order_list_window_is_never_lent_with_the_state_block_on(console, monkeypatch, ops) -> None:
    """Owner Q3 on the State path: the applier writes this turn's domain before the engine seam, so the gate reads
    the domains the focus held BEFORE it."""
    from tests.chatbot.test_report_smart_step7 import _state_on

    ran = _state_on(console)
    order_list = _v63(order_status=None, document=["DO"], entities=[_e(PRODUCT_CODE, "product")],
                      entity_op="replace_combine", domain_in_message=True, state_changes=[], **YEAR_2026)
    text, log = _say_all(console, monkeypatch, order_list, f"delivery orders for {PRODUCT_CODE} in 2026")
    assert TOOL not in _names(log) and SALES_REPORT_TOOL not in _names(log), ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(state_changes=list(ops)), "by salesppl")
    assert ran, "harness: the State path never ran"
    assert _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r8_review_state_on_a_ranking_reply_to_the_total_still_keeps_its_period(console, monkeypatch) -> None:
    from tests.chatbot.test_report_smart_step7 import _state_on

    ran = _state_on(console)
    _total(console, monkeypatch, state_changes=[])
    text, log = _say_all(console, monkeypatch, _row3(state_changes=list(KEEP)), "by salesppl")
    assert ran, "harness: the State path never ran"
    assert _ran(log) == [] and PERIOD_Q not in text and HOW_MANY in text, (text, log)


def test_r8_review_a_month_trend_s_count_and_empty_measure_are_never_carried(console, monkeypatch) -> None:
    month = _v63(group_by="month", ranking_refine=False, entities=[_e(PRODUCT_CODE, "product")],
                 entity_op="replace_combine", domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, month, f"monthly sales for {PRODUCT_CODE} in 2026")
    assert _ran(log) == [] and BASIS_Q in text and HOW_MANY not in text, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(), "by salesppl")
    assert _ran(log) == [] and PERIOD_Q not in text, (text, log)
    assert HOW_MANY in text and "quantity or" in text.lower() and BASIS_Q in text, text
    _answer_all(console, monkeypatch, "sales_agent")


def test_r8_review_a_replaced_ask_keeps_its_product_on_a_product_axis(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _row3(), "by salesppl")
    assert _ran(log) == [] and PERIOD_Q not in text, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(group_by="product"), "by product")
    assert _ran(log) == [] and PERIOD_Q not in text and HOW_MANY in text, (text, log)
    _answer_all(console, monkeypatch, "product")


def test_r8_review_a_fresh_ranking_s_open_ask_replaced_by_a_new_axis_keeps_its_choices(console, monkeypatch) -> None:
    fresh = _v63(group_by="customer", ranking_refine=False, entities=[_e(PRODUCT_CODE, "product")],
                 entity_op="replace_combine", measure="qty", rank_by="quantity", basis="delivered",
                 domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, fresh, f"top customers for {PRODUCT_CODE} in 2026, qty delivered")
    assert _ran(log) == [] and text == HOW_MANY, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(), "by salesppl")
    assert _ran(log) == [] and text == HOW_MANY, (text, log)
    text, log = _say_all(console, monkeypatch, _top5(), "top 5")
    _runs_with_all_four(log, "sales_agent")


def test_r8_review_a_typed_measure_survives_the_axis_swap_into_a_total_s_open_ask(console, monkeypatch) -> None:
    """R7 + R5: the measure typed in the answer to a total's question is a value, so the axis swap keeps it
    (`_settled_by_its_axis`); only the count and the basis are owed."""
    total = _v63(group_by=None, ranking_refine=False, entities=[_e(PRODUCT_CODE, "product")],
                 entity_op="replace_combine", domain_in_message=True)
    text, log = _say_all(console, monkeypatch, total, f"total sales for {PRODUCT_CODE}")
    assert _ran(log) == [] and PERIOD_Q in text and BASIS_Q in text, ("setup", text, log)
    answer = _v63(measure="qty", rank_by="quantity", open_question_answer=dict(FILL), **YEAR_2026)
    text, log = _say_all(console, monkeypatch, answer, "2026, qty")
    assert _ran(log) == [] and text == BASIS_Q, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _row3(ranking_refine=None), "by salesppl")
    assert _ran(log) == [] and HOW_MANY in text and BASIS_Q in text, (text, log)
    assert "quantity or" not in text.lower() and PERIOD_Q not in text, text
    text, log = _say_all(console, monkeypatch, _v63(top_n=5, basis="delivered", open_question_answer=dict(FILL)),
                         "top 5, delivered")
    _runs_with_all_four(log, "sales_agent")
