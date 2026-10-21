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
