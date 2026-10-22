"""REPORT-SMART-L round S1: sales reports on parser v92 with the State path on.

EVAL-BENCH note 6316652256; plan documentation/plans/chatbot/PLAN-report-smart-v92-1022.md
(UAC report-smart-v92-1022-acceptance-criteria.md, AC1 to AC4). Parse shapes are the live v92 ones.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    PERIOD_Q,
    _e,
    _rank,
    _refine,
    _reply,
    _seed_cabana,
    console,
)
from tests.chatbot.test_report_smart_capability import _ask
from tests.chatbot.test_report_smart_step7 import (  # noqa: F401
    KEEP,
    SALES_FRAME,
    THIS_YEAR,
    _apply_state,
    _held,
    _sales_focus,
    _state_on,
    _step3,
)

NO_DATES = {"date_filter_start": None, "date_filter_end": None}
SWITCH = {"op": "switch_domain", "axis": None, "position": None}
SORT = {"op": "set", "axis": "sort", "position": None}


def _step2_ask(console) -> None:
    """Step 2: the ask naming neither measure nor basis; both are asked."""
    console.cabana = _seed_cabana(console)
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure=None, basis=None, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year",
    )
    assert calls == [], (text, calls)


def _v92_step3_answer(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="sales", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        entities=[], group_by="sales_agent", top_n=3, measure="qty", basis="delivered",
        state_changes=list(KEEP), **NO_DATES,
    )
    base.update(over)
    return _rank(**base)


def _v92_step4_refine(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
        entities=[], group_by="sales_agent", top_n=3, measure="qty", basis="ordered",
        state_changes=[SWITCH], **NO_DATES,
    )
    base.update(over)
    return _rank(**base)


ORDERED_BODIES = [
    "ordered", "by ordered please", "按下单的", "ikut order", "ordered lah", "改成 ordered", "ordered sales",
    "tukar ke ordered",
]
ORDERED_OPS = [[SWITCH], list(KEEP), [SWITCH, SORT]]


def _ask_and_answer(console) -> None:
    _step2_ask(console)
    text, calls = console.say(_v92_step3_answer(), "qty, delivered")
    assert len(calls) == 1, ("setup: the ranking did not run", text, calls)


# ---- AC2: the answered ask stores the sales domain ----


@pytest.mark.parametrize("body", ["qty, delivered", "by quantity, delivered", "数量, 已送货", "kuantiti, delivered",
                                  "qty delivered lah", "1 delivered", "quantity & 已送货", "ikut qty, delivered"])
def test_ac2_an_answered_two_choice_sales_ask_stores_the_sales_domain(console, body) -> None:
    from app.services.chatbot import engine as engine_mod

    ran = _state_on(console)
    _step2_ask(console)
    after: list[Any] = []
    real = engine_mod.turn_apply

    def spy(*a: Any, **k: Any) -> Any:
        res = real(*a, **k)
        after.append(res[0].focus)
        return res

    console.monkeypatch.setattr(engine_mod, "turn_apply", spy)
    text, calls = console.say(_v92_step3_answer(), body)
    assert ran, "harness: the State path never ran"
    assert len(calls) == 1, (text, calls)
    assert after and after[-1].domains == ["sales"], [f.domains for f in after]


# ---- AC1: step 4 refine after the ask + answer path ----


@pytest.mark.parametrize("ops", ORDERED_OPS, ids=["switch", "keep", "switch_sort"])
@pytest.mark.parametrize("body", ORDERED_BODIES)
def test_ac1_the_ordered_refine_after_the_answered_ask_reruns_the_held_ranking(console, body, ops) -> None:
    ran = _state_on(console)
    _ask_and_answer(console)
    text, calls = console.say(_v92_step4_refine(state_changes=list(ops)), body)
    assert ran, "harness: the State path never ran"
    assert PERIOD_Q not in text, text
    assert len(calls) == 1, (text, calls)
    assert calls[0]["basis"] == "ordered", calls
    _held(calls[0], console)


# ---- AC3: step 9 refine after the step-8 breakdown ----

AMOUNT_BODIES = ["amount, delivered", "by amount delivered", "金额, 已送货", "ikut amount, delivered",
                 "amount delivered pls", "RM, delivered", "按金额 delivered", "jumlah RM yang delivered"]
SEP_MONTH = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}


@pytest.mark.parametrize("body", AMOUNT_BODIES)
def test_ac3_a_refine_after_the_breakdown_keeps_its_count_and_period(console, body) -> None:
    ran = _state_on(console)
    text, calls = console.say(
        _ask(order_status="sales_analysis", group_by="sales_agent", measure="qty", sales_basis="delivered",
             state_changes=[SWITCH, {"op": "set", "axis": "period", "position": None},
                            {"op": "set", "axis": "quantity", "position": None}], **SEP_MONTH),
        "Total sale for all sale agents on September 2026",
    )
    assert len(calls) == 1, ("setup: the breakdown did not run", text, calls)
    text, calls = console.say(
        _rank(domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
              entities=[], group_by="sales_agent", top_n=None, measure="amount", basis="delivered",
              state_changes=[SWITCH], **NO_DATES),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert "Which period?" not in text and "How many" not in text, text
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["measure"] == "amount" and args["basis"] == "delivered", args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert args["top_n"] >= 100, args


# ---- unit: the held sales frame survives a refine's switch_domain ----


@pytest.mark.parametrize("hint", ["sales", "order"])
def test_ac1_a_sales_ranking_refine_with_switch_domain_keeps_the_held_frame(hint) -> None:
    from tests.chatbot._turn_helpers import verdict

    out = _apply_state(_sales_focus(), verdict(
        domain_hint=hint, intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
        state_changes=[SWITCH],
    ))
    assert out.valid is True, out.log
    assert out.state.focus.sales_ranking_frame == SALES_FRAME, out.state.focus
    assert out.state.focus.domains == ["sales"], out.state.focus.domains


# ---- AC4 near misses: a real switch still drops the held report ----


def test_ac4_near_miss_a_stock_ask_drops_the_held_sales_frame() -> None:
    from tests.chatbot._turn_helpers import verdict

    out = _apply_state(_sales_focus(), verdict(domain_hint="inventory", intent_hint="check_stock",
                                               state_changes=[SWITCH]))
    assert out.valid is True, out.log
    assert out.state.focus.sales_ranking_frame is None
    assert out.state.focus.domains == ["inventory"]


def test_ac4_near_miss_an_outstanding_order_ask_drops_the_held_sales_frame() -> None:
    from tests.chatbot._turn_helpers import verdict

    out = _apply_state(_sales_focus(), verdict(domain_hint="order", intent_hint="check_order",
                                               order_status="outstanding", state_changes=[SWITCH]))
    assert out.valid is True, out.log
    assert out.state.focus.sales_ranking_frame is None


# ---- near miss: a top selling ask onto the same sales domain is not a refine of the held ranking ----

TOP_SELLING_BODIES = [
    "top 5 selling items this month", "best selling 5 items this month", "本月 top 5 畅销产品",
    "5 item paling laku bulan ini", "top 5 items sold this month lah", "这个月卖最好的 5 个产品",
    "item paling banyak jual bulan ni, top 5", "top 5 hot selling items October",
]
OCT = {"date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}


@pytest.mark.parametrize("hint", ["sales", "order"])
@pytest.mark.parametrize("body", TOP_SELLING_BODIES)
def test_near_miss_a_top_selling_ask_after_a_ranking_runs_the_top_selling_tool(console, monkeypatch, body, hint) -> None:
    from tests.chatbot.test_report_ask_lane import TOOL, _names, _say_all

    ran = _state_on(console)
    _step3(console)
    qf = _rank(
        domain_hint=hint, intent_hint="check_order", order_status="top_selling", ranking_refine=False,
        entities=[], group_by=None, top_n=5, measure=None, basis="delivered", rank_by="amount",
        rank_group="item", rank_direction="top", state_changes=[SWITCH], **OCT,
    )
    text, log = _say_all(console, monkeypatch, qf, body)
    assert ran, "harness: the State path never ran"
    assert "crm_top_selling_report" in _names(log), (_names(log), text)
    assert TOOL not in _names(log), (_names(log), text)


# ---- live turn 34f16b3d: the answer repeats the held brand (entity_op reuse) ----

ANSWER_OP = [{"op": "answer", "axis": None, "position": None}]
ANSWER_BODIES = [
    "qty, delivered", "by quantity, delivered", "数量, 已送货", "kuantiti, yang delivered", "qty delivered lah",
    "ikut qty, delivered", "按 qty 已送货", "quantity and delivered please",
]


def _repeating_answer(*entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="sales", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        entities=list(entities), group_by="sales_agent", top_n=3, measure="qty", basis="delivered",
        state_changes=list(ANSWER_OP), entity_op="reuse", **NO_DATES,
    )
    base.update(over)
    return _rank(**base)


@pytest.mark.parametrize("repeat", ["brand", "brand_twice"])
@pytest.mark.parametrize("body", ANSWER_BODIES)
def test_an_answer_repeating_the_held_brand_fills_the_open_slot_and_runs(console, body, repeat) -> None:
    ran = _state_on(console)
    _step2_ask(console)
    held = [_e("Cabana", "brand")] * (1 if repeat == "brand" else 2)
    text, calls = console.say(_repeating_answer(*held), body)
    assert ran, "harness: the State path never ran"
    assert PERIOD_Q not in text, text
    assert len(calls) == 1, (text, calls)
    _held(calls[0], console)
    assert calls[0]["basis"] == "delivered" and calls[0]["measure"] == "qty", calls


def _seed_other_brand(console) -> None:
    import uuid

    from app.models.product import Brand
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = console.session_factory()
    try:
        db.add(Brand(id=str(uuid.uuid4()), brand_code="ZZTOTH", brand_name="Otherbrand", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("body", ["qty, delivered for otherbrand", "otherbrand pls qty delivered", "otherbrand ikut qty, delivered"])
def test_near_miss_an_answer_naming_a_different_brand_is_a_new_ask_and_drops_the_slot(console, body) -> None:
    ran = _state_on(console)
    _step2_ask(console)
    _seed_other_brand(console)
    text, calls = console.say(
        _repeating_answer(_e("Otherbrand", "brand"), entity_op="set",
                          state_changes=[{"op": "set", "axis": "brand", "position": None}]),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert calls == [] and PERIOD_Q in text, (text, calls)  # the held period was not lent to it
