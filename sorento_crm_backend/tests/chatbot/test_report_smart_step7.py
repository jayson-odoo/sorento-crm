"""REPORT-SMART-1021: a refine keeps the held report; only the parser restarts the frame.

#1721 hand test steps 4 to 7, measured live by crew's EVAL-BENCH on 21 Oct (turns 934cbac8,
d0c982df, dded3dc7; parser v77): the live parser REPEATS the held axis, count and measure on
most refines (98 of 130 live `ranking_refine` parses carry a `group_by`). So a frame restart
keyed on `group_by` turned "ordered" into a fresh ask that lost the held period, and the next
ask typed again was then eaten as that period's answer.

The rule now (crew ruling, 21 Oct): only the parser restarts the frame, with its
`new_subject` op; a `ranking_refine` verdict re-runs the held report with the keys it names,
period and filters held; and a refine naming its own entity or `new_subject` is never taken as
the answer to an open question. Parser fields only; the words are decoration.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    PERIOD_Q,
    _e,
    _rank,
    _refine,
    _reply,
    _seed_cabana,
    console,
)

THIS_YEAR = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
_NUMBERED = re.compile(r"^\s*([1-9])[.)]", re.M)
NEW_SUBJECT = [{"op": "new_subject", "axis": None, "position": None}]


def _live_refine(**overrides: Any) -> dict[str, Any]:
    """A refine as the live parser emits it: the held axis, count and measure repeated."""
    base: dict[str, Any] = dict(group_by="sales_agent", top_n=3, measure="qty",
                                state_changes=[{"op": "set", "axis": "sort", "position": None}])
    base.update(overrides)
    return _refine(**base)


def _step3(console) -> None:
    """Steps 2-3: top 3 sales agents for the brand this year, qty, delivered."""
    console.cabana = _seed_cabana(console)
    _text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="delivered", **THIS_YEAR),
        "who's the top 3 salesman for cabana this year",
    )
    assert calls, "setup: the ranking did not run"


def _held(args: dict[str, Any], console) -> None:
    assert args["brand_ids"] == [console.cabana], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 3, args


def test_step4_a_live_shape_refine_reruns_the_held_ranking_with_its_period(console) -> None:
    _step3(console)
    text, calls = console.say(_live_refine(basis="ordered"), "ordered")
    assert len(calls) == 1, (text, calls)  # never "Which period?"
    assert calls[0]["basis"] == "ordered" and calls[0]["measure"] == "qty", calls
    _held(calls[0], console)


def test_step4_paraphrase_a_live_shape_two_key_refine_keeps_the_period_too(console) -> None:
    _step3(console)
    text, calls = console.say(_live_refine(basis="delivered", measure="amount", top_n=None), "amount, delivered")
    assert len(calls) == 1, (text, calls)
    assert calls[0]["measure"] == "amount", calls
    _held(calls[0], console)


def test_step5_the_ask_typed_again_as_a_refine_reruns_the_held_report_with_its_channel(console) -> None:
    """dded3dc7: the whole ask typed again, parsed as a refine with no new_subject op. The
    parser said refine, so the held report re-runs with the channel; it is never a period answer."""
    _step3(console)
    console.say(_live_refine(basis="ordered"), "ordered")
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="ordered", sales_channel="dealer",
              ranking_refine=True, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year, dealer sales only",
    )
    assert len(calls) == 1, (text, calls)
    assert calls[0]["channel"] == "dealer", calls
    _held(calls[0], console)


def test_step5_with_new_subject_the_ask_typed_again_is_a_new_frame_asking_both(console) -> None:
    """The parser's `new_subject` restarts the frame: neither measure nor basis named, both asked."""
    _step3(console)
    console.say(_live_refine(basis="ordered"), "ordered")
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure=None, basis=None, sales_channel="dealer",
              ranking_refine=True, state_changes=NEW_SUBJECT, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year, dealer sales only",
    )
    assert calls == [], (text, calls)
    assert [int(n) for n in _NUMBERED.findall(text)] == [1, 2], text
    text, calls = console.say(_reply(measure="qty", basis="delivered"), "qty, delivered")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["basis"] == "delivered" and args["measure"] == "qty" and args["channel"] == "dealer", args
    _held(args, console)


def test_an_ask_typed_again_under_an_open_question_is_never_its_answer(console) -> None:
    """A refine naming its own entity while a question is open is a new ask (the slot is
    dropped), so the open ask's axis never runs on it."""
    _step3(console)
    text, calls = console.say(
        _rank(group_by="customer", top_n=5, measure="amount", basis="delivered",
              date_filter_start=None, date_filter_end=None),
        "top 5 customers",
    )
    assert calls == [] and PERIOD_Q in text, (text, calls)
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="delivered", sales_channel="dealer",
              ranking_refine=True, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year, dealer sales only",
    )
    assert all(c.get("group_by") != "customer" for c in calls), (text, calls)


def test_near_miss_a_bare_channel_refine_keeps_the_held_choices(console) -> None:
    _step3(console)
    text, calls = console.say(_refine(sales_channel="dealer"), "dealer sales only")
    assert len(calls) == 1, (text, calls)
    assert calls[0]["basis"] == "delivered" and calls[0]["measure"] == "qty" and calls[0]["channel"] == "dealer", calls
    _held(calls[0], console)


# ---- EVAL-BENCH re-run on bcbc823214 (crew note 6312251738): the State path drops the frame ----
#
# Live (parser v77, State prompt on), turn 516a6b39: step 4 ran the refine, and the turn's
# domain was written `sales` (`turn_runtime._report_status_means_order_domain`: a sales figure
# status is the `sales` domain). Step 5's parse names the same ask with the prompt's own
# `domain_hint "order"`, so `chat_state.apply_changes` read `order` against the held `sales`
# as a domain switch and dropped the domain-bound axes, the held report frame included: the
# refine then ran as a fresh ask with no period ("Which period?"), and step 6's "qty,
# delivered" was taken as that period's answer. One domain reading for both: the State's
# switch check reads the message's domain the way the turn writes it.

KEEP = [{"op": "keep", "axis": None, "position": None}]
SALES_FRAME = {
    "group_by": "sales_agent", "top_n": 3, "measure": "qty", "basis": "ordered",
    "date_from": "2026-01-01", "date_to": "2026-12-31", "sort": "desc",
}


def _apply_state(focus, v):
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import State

    return chat_state.apply_changes(
        State(focus=focus, turn_no=5), v, open_question=None,
        domains=["inventory", "incoming", "order", "sales", "product_attachment"],
        kinds=["product", "customer", "brand", "category"], brands=["SORENTO", "MOCHA"],
        positions_read_elsewhere=False,
    )


def _sales_focus():
    from app.services.chatbot.turn.state import Focus

    return Focus(domains=["sales"], status="sales_ranking", sales_ranking_frame=dict(SALES_FRAME),
                 date_window={"start": "2026-01-01", "end": "2026-12-31", "mode": None})


@pytest.mark.parametrize("status", ["sales_ranking", "sales_report", "sales_analysis", "top_selling"])
def test_a_sales_figure_ask_under_the_prompts_order_domain_is_not_a_switch_off_the_held_sales(status) -> None:
    """516a6b39: the parse names `order` for a sales figure ask; the turn holds `sales`. Not a
    switch: the held report frame and status stay for the lane to read."""
    from tests.chatbot._turn_helpers import verdict

    out = _apply_state(_sales_focus(), verdict(
        domain_hint="order", intent_hint="check_order", order_status=status, ranking_refine=True,
        sales_channel="dealer", state_changes=KEEP, **THIS_YEAR,
    ))
    assert out.valid is True, out.log
    assert out.state.focus.sales_ranking_frame == SALES_FRAME, out.state.focus
    assert out.state.focus.domains == ["sales"], out.state.focus.domains


def test_the_sales_word_on_an_order_ask_is_not_a_switch_off_the_held_order_list() -> None:
    """The same normalisation's other half: `sales` with no sales figure status is the order
    ask (`_report_status_means_order_domain`), so an order list held is not switched away."""
    from app.services.chatbot.turn.state import Focus
    from tests.chatbot._turn_helpers import verdict

    focus = Focus(domains=["order"], status="open", sort={"by": "date", "dir": "desc"})
    out = _apply_state(focus, verdict(domain_hint="sales", intent_hint="check_order", state_changes=KEEP))
    assert out.valid is True, out.log
    assert out.state.focus.status == "open" and out.state.focus.sort == {"by": "date", "dir": "desc"}
    assert out.state.focus.domains == ["order"]


@pytest.mark.parametrize("order_status", ["outstanding", None])
def test_near_miss_an_order_ask_echoing_the_held_sales_status_is_still_a_switch(order_status) -> None:
    """Review should-fix 1: the held status echoed back (`status` equal to the State's) is not
    the message's own report kind, so an outstanding / order ask under `order` after a held top
    selling ranking is still the switch to `order` (the echo cleared, as r10 clears it)."""
    from app.services.chatbot.turn.state import Focus
    from tests.chatbot._turn_helpers import verdict

    focus = Focus(domains=["sales"], status="top_selling", sales_channel="dealer", sort={"by": "qty", "dir": "desc"})
    out = _apply_state(focus, verdict(domain_hint="order", intent_hint="check_order", status="top_selling",
                                      order_status=order_status, state_changes=KEEP))
    assert out.valid is True, out.log
    assert out.state.focus.domains == ["order"], out.state.focus.domains
    assert out.state.focus.status is None and out.verdict.get("status") is None, (out.state.focus, out.verdict)


def test_near_miss_a_real_domain_switch_off_a_held_report_still_drops_its_frame() -> None:
    from tests.chatbot._turn_helpers import verdict

    out = _apply_state(_sales_focus(), verdict(domain_hint="inventory", intent_hint="check_stock", state_changes=KEEP))
    assert out.valid is True, out.log
    assert out.state.focus.sales_ranking_frame is None
    assert out.state.focus.domains == ["inventory"]


def _state_on(console) -> list[int]:
    """The live turn path: the State prompt on (`ParserConfig.state_block`), so the engine runs
    `chat_state.apply_changes` on every parse carrying `state_changes`. Returns a run counter."""
    import dataclasses

    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.turn import chat_state

    real_config, real_apply = parser_mod.resolve_config, chat_state.apply_changes
    ran: list[int] = []

    def counted(*a: Any, **k: Any) -> Any:
        ran.append(1)
        return real_apply(*a, **k)

    console.monkeypatch.setattr(
        parser_mod, "resolve_config", lambda db, **kw: dataclasses.replace(real_config(db, **kw), state_block=True)
    )
    console.monkeypatch.setattr(chat_state, "apply_changes", counted)
    return ran


def test_step5_state_on_the_ask_typed_again_reruns_the_held_report_with_its_channel(console) -> None:
    """516a6b39 with the State path on: step 4's refine ran and wrote the `sales` domain; the
    re-typed ask (parser `order`, op `keep`, refine) re-runs the held report with the dealer
    channel and its period, never "Which period?"."""
    ran = _state_on(console)
    _step3(console)
    console.say(_live_refine(basis="ordered", state_changes=[{"op": "set", "axis": "status", "position": None}]),
                "ordered")
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="ordered", sales_channel="dealer",
              ranking_refine=True, state_changes=KEEP, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year, dealer sales only",
    )
    assert ran, "harness: the State path never ran"
    assert PERIOD_Q not in text, text
    assert len(calls) == 1, (text, calls)
    assert calls[0]["channel"] == "dealer" and calls[0]["basis"] == "ordered", calls
    _held(calls[0], console)


def test_step6_state_on_measure_and_basis_after_the_rerun_refine_the_report(console) -> None:
    """d7be934d: "qty, delivered" right after step 5 re-runs the held report delivered, with the
    channel, brand and period held; it is never read as a period."""
    ran = _state_on(console)
    _step3(console)
    console.say(_live_refine(basis="ordered", state_changes=[{"op": "set", "axis": "status", "position": None}]),
                "ordered")
    console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="ordered", sales_channel="dealer",
              ranking_refine=True, state_changes=KEEP, **THIS_YEAR),
        "who's the top 3 salesman for cabana this year, dealer sales only",
    )
    text, calls = console.say(
        _live_refine(basis="delivered", state_changes=[{"op": "answer", "axis": None, "position": None}]),
        "qty, delivered",
    )
    assert ran, "harness: the State path never ran"
    assert "as a period" not in text and PERIOD_Q not in text, text
    assert len(calls) == 1, (text, calls)
    assert calls[0]["basis"] == "delivered" and calls[0]["channel"] == "dealer", calls
    _held(calls[0], console)
