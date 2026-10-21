"""REPORT-SMART-1021 step 1: a re-typed ranking starts a new report frame.

PR #1721 hand test step 7 (crew relay, 21 Oct 2026, names masked): right after a held ranking
(top 3 sales agents for a brand this year, settled as qty then re-run as ordered), the user
re-typed the WHOLE ask with one more word ("..., dealer sales only"). The bot ran at once with
the held basis and measure (trace: basis=ordered measure=qty channel=dealer), where a new ask
naming neither must ask both in ONE numbered reply.

The parser's channel rule maps "dealer only" to `ranking_refine` true, so the re-typed ask
reached `_refine`. The structural tell is the parser's own `group_by`: a refine has `group_by`
null (prompt R-X-05, "only the fields the message names ... `group_by` null"), and a message
naming its own axis is a new ask. Parser fields only; the message words are decoration.
"""
from __future__ import annotations

import re
from typing import Any

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    _e,
    _rank,
    _refine,
    _reply,
    _seed_cabana,
    console,
)

THIS_YEAR = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
_NUMBERED = re.compile(r"^\s*([1-9])[.)]", re.M)


def _step6(console) -> None:
    """Step 6: top 3 sales agents for the brand this year, qty, then re-run by ordered."""
    console.cabana = _seed_cabana(console)
    _text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="delivered", **THIS_YEAR),
        "who's the top 3 salesman for cabana this year",
    )
    assert calls, "setup: step 6 did not run"
    _text, calls = console.say(_refine(basis="ordered"), "ordered")
    assert len(calls) == 1 and calls[0]["basis"] == "ordered", calls


def _step7(**overrides: Any) -> dict[str, Any]:
    """Step 7: the whole ask re-typed with a channel word, naming neither measure nor basis."""
    base: dict[str, Any] = dict(
        top_n=3, measure=None, basis=None, rank_by=None, sales_channel="dealer", ranking_refine=True, **THIS_YEAR
    )
    base.update(overrides)
    return _rank(_e("Cabana", "brand"), **base)


def _asks_metric_and_basis(text: str) -> None:
    assert [int(n) for n in _NUMBERED.findall(text)] == [1, 2], text
    low = text.lower()
    assert "quantity" in low and "delivered" in low, text


def test_step7_a_retyped_ranking_flagged_refine_asks_metric_and_basis_in_one_reply(console) -> None:
    _step6(console)
    text, calls = console.say(_step7(), "who's the top 3 salesman for cabana this year, dealer sales only")
    assert calls == [], (text, calls)
    _asks_metric_and_basis(text)


def test_step7_the_answer_runs_the_new_ask_with_its_own_channel_and_the_answered_choices(console) -> None:
    _step6(console)
    console.say(_step7(), "who's the top 3 salesman for cabana this year, dealer sales only")
    text, calls = console.say(_reply(measure="qty", basis="delivered"), "qty, delivered")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["basis"] == "delivered" and args["measure"] == "qty", args
    assert args["channel"] == "dealer" and args["group_by"] == "sales_agent" and args["top_n"] == 3, args
    assert args["brand_ids"] == [console.cabana], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


def test_step7_paraphrase_the_retype_parsed_as_top_selling_with_refine_is_a_new_ask_too(console) -> None:
    """The same re-type read under another report type with the refine flag (PR-B S3's
    `as_held_refine` seam) never re-runs the held frame either."""
    _step6(console)
    text, calls = console.say(_step7(order_status="top_selling"), "top 3 sales person cabana 2026 dealer only")
    assert all(c.get("basis") != "ordered" for c in calls), (text, calls)
    if not calls:
        _asks_metric_and_basis(text)


def test_step7_paraphrase_a_retyped_ask_that_restates_its_own_choices_runs_with_them(console) -> None:
    _step6(console)
    text, calls = console.say(_step7(measure="amount", basis="delivered"), "top 3 salesman cabana this year by amount delivered dealer")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["measure"] == "amount" and args["basis"] == "delivered" and args["channel"] == "dealer", args


def test_step7_near_miss_a_bare_channel_refine_still_keeps_the_held_choices(console) -> None:
    """A real refine (group_by null, only the channel) keeps the held basis and measure."""
    _step6(console)
    text, calls = console.say(_refine(sales_channel="dealer"), "dealer sales only")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["basis"] == "ordered" and args["measure"] == "qty" and args["channel"] == "dealer", args
