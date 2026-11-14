"""TARGET-ACHIEVED-PERF fix round, UAC 12: a turn never starts a round it cannot finish
(`documentation/plans/sales/target-achieved-perf-14nov-acceptance-criteria.md` line 12).

Crew pass, typo question: 6 rounds and 8 tool calls all ok, then the next round's model call started with almost no
turn time left, timed out, and the turn ended `limited` / `error` with "I stopped because of an error" after 55 s.

(a) With less time left than a round needs (`loop.ROUND_MIN_SECONDS`) and tool results in hand, no further round is
    sent: the turn goes straight to its final answer from those results (status answered, no limit_hit, no error
    sentence). (b) A round's model call that times out anyway, tool results in hand: the same. With no tool result
    yet, today's behaviour stays. (c) Only the final answer itself failing ends the turn in an error.

No live LLM: the scripted provider and the injected clock of `test_agent_loop.py`; Postgres via the blank schema.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent.test_agent_loop import (  # noqa: F401  (fixtures)
    TWELVE,
    Mcp,
    ScriptedProvider,
    answer,
    asks,
    call,
    contact,
    db,
    run,
)


def _no_error_words(reply: str) -> None:
    said = reply.lower()
    assert "stopped because of an error" not in said, reply
    assert "error" not in said, reply
    assert "limit" not in said, reply


def _offered(seen: dict) -> list[str]:
    return [t["function"]["name"] for t in seen["tools"] or []]


def _timeouts():
    from app.services.chatbot.llm_call import TimedOut

    return [TimedOut("slow"), TimeoutError("slow")]


def test_T1_too_little_time_for_a_round_goes_straight_to_the_answer(db, contact):
    """12a: after a tool round the time left is just under what a round needs: the next model call is the final
    answer (only the answer tool offered), not another round, and the turn answers from the tool result."""
    from app.services.chatbot.agent import loop

    assert hasattr(loop, "ROUND_MIN_SECONDS"), "loop.ROUND_MIN_SECONDS: the least time a tool round needs"
    budget = loop.budgets_from_settings(db).max_seconds
    left = loop.ROUND_MIN_SECONDS - 0.5
    assert 1 <= left < budget
    clock = {"t": 0.0}
    provider = ScriptedProvider(
        [asks(call()), answer("There are 12 units.", figures=TWELVE)],
        # After the first round's model call the turn has `left` seconds: more than a call's 1 s floor, less than
        # a round needs.
        on_call=lambda n: clock.__setitem__("t", budget - left) if n == 1 else None,
    )
    result = run(db, contact, provider, Mcp(), clock=lambda: clock["t"])

    assert len(provider.seen) == 2
    assert _offered(provider.seen[1]) == ["answer"], "a round was sent with too little time left for it"
    assert result.status == "answered", result.status
    assert result.limit_hit is None
    assert "12 units" in result.reply_text and loop.NOT_VERIFIED not in result.reply_text
    _no_error_words(result.reply_text)


@pytest.mark.parametrize("timeout", _timeouts(), ids=["TimedOut", "TimeoutError"])
def test_T2_a_round_that_times_out_after_a_tool_result_still_answers(db, contact, timeout):
    """12b: the second round's model call times out with a tool result in hand: the turn answers from it, status
    answered, no limit_hit, no error sentence."""
    from app.services.chatbot.agent import loop

    provider = ScriptedProvider([asks(call()), timeout, answer("There are 12 units.", figures=TWELVE)])
    result = run(db, contact, provider, Mcp())

    assert result.status == "answered", (result.status, result.limit_hit, result.reply_text)
    assert result.limit_hit is None
    assert "12 units" in result.reply_text and loop.NOT_VERIFIED not in result.reply_text
    _no_error_words(result.reply_text)
    assert _offered(provider.seen[-1]) == ["answer"]


@pytest.mark.parametrize("timeout", _timeouts(), ids=["TimedOut", "TimeoutError"])
def test_T3_a_timeout_on_the_first_round_with_no_tool_result_is_unchanged(db, contact, timeout):
    """12b guard: nothing to answer from, so today's outcome stays: the turn fails with the provider reason."""
    provider = ScriptedProvider([timeout])
    result = run(db, contact, provider, Mcp())

    assert result.status == "failed"
    assert result.limit_hit is None
    assert result.reply_text == "The agent could not answer: the model provider failed."
    assert len(provider.seen) == 1


@pytest.mark.parametrize("timeout", _timeouts(), ids=["TimedOut", "TimeoutError"])
def test_T4_the_final_answer_itself_failing_is_still_an_error(db, contact, timeout):
    """12c guard: the round after the tool result times out AND the final answer call fails: today's error outcome
    (a contact turn reads no "what I read" line: the turn fails)."""
    provider = ScriptedProvider([asks(call()), timeout, TimeoutError("slow again")])
    result = run(db, contact, provider, Mcp())

    assert result.status == "failed", (result.status, result.reply_text)
    assert result.reply_text == "The agent could not answer: the model provider failed."
    assert _offered(provider.seen[-1]) == ["answer"]
