"""AGENTIC-P1 round 5d: dates in the reply are not figures (red first)."""
from __future__ import annotations

import pytest

from tests.chatbot.agent.test_agent_round5c import (  # noqa: F401 - fixtures and helpers
    Mcp,
    Provider,
    STOCK,
    answer_call,
    asks,
    call,
    contact,
    db,
    run,
)

REPORT = "crm_report_ask"


@pytest.mark.parametrize(
    "reply",
    [
        "It arrives on 15 Nov 2026.",
        "It arrives on 15 November.",
        "It arrives on 15th Nov.",
        "It arrives Nov 15, 2026.",
        "It arrives November 15.",
        "It arrives 15/11/2026.",
        "It arrives 15-11-2026.",
        "It arrives 15.11.2026.",
        "Total from 1 Jan to 30 Oct 2026 only",
        "It ships in 2026.",
        "Back in Oct 2026 it was fine",
    ],
)
def test_dates_are_not_figures(reply):
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures(reply, []) == []


def test_a_range_and_a_made_up_sum_are_still_checked():
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures("Between 12-15 units", []) == ["12", "15 units"]
    assert unsupported_figures("Total is 12 units", ["5", "7"]) == ["12 units"]
    assert unsupported_figures("Total is 2,026 units", []) == ["2,026 units"]
    assert unsupported_figures("Cost 2000.50", []) == ["2000.50"]


def test_an_eta_reply_with_a_written_date_is_untouched(db, contact):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("It arrives on 15 Nov 2026."),
        ]
    )
    result = run(db, contact, provider, Mcp({"items": [{"eta": "2026-11-15"}], "has_result": True}))
    assert result.reply_text == "It arrives on 15 Nov 2026."
    assert len(provider.seen) == 2


def test_a_report_total_with_a_written_period_is_untouched(db, contact):
    envelope = {
        "result_type": "report_ask",
        "response": "Period: 1 Jan 2026 to 30 Oct 2026\nTotal RM 2,000,000.00",
        "has_result": True,
    }
    text = "Total sales 1 Jan to 30 Oct 2026 were RM2,000,000.00."
    provider = Provider(
        [
            asks(call(REPORT, {"query": "x"}, "c1")),
            answer_call(text, figures=[{"value": "2,000,000.00", "call_id": "c1"}]),
        ]
    )
    result = run(db, contact, provider, Mcp(envelope))
    assert result.reply_text == text
    assert len(provider.seen) == 2


def test_the_day_of_a_written_date_in_a_result_backs_nothing(db, contact):
    text = "There are 15 units."
    figures = [{"value": "15", "call_id": "c1"}]
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call(text, figures=figures),
            answer_call(text, figures=figures, cid="a2"),
        ]
    )
    result = run(db, contact, provider, Mcp({"items": [{"eta": "15 Nov 2026"}], "has_result": True}))
    assert "(not verified)" in result.reply_text


def test_redaction_leaves_written_dates_alone():
    from app.services.chatbot.agent.loop import _redact_written

    assert _redact_written("Ships 15 Nov 2026 with 9 units", {"9 units"}) == "Ships 15 Nov 2026 with (not verified)"


def test_clean_detail_keeps_a_time_of_day():
    from app.services.chatbot.agent.tools import clean_detail

    out = clean_detail("slot 10:30 is taken, could not reach localhost:8000")
    assert "10:30" in out and "localhost" not in out and "8000" not in out
