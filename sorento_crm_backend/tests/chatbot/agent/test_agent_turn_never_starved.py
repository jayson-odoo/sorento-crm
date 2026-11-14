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


# ------------------------------------------------------------------ review round: 12c on a staff panel turn


def _staff_run(db, contact, provider, **kw):
    """The same turn on the staff panel: `forced_final` then answers "What I read: ..." when the final call fails,
    instead of raising, so the outcome is set by the round path that called it."""
    from tests.chatbot.agent._ported_reads_support import panel_turn

    with panel_turn(contact["user_id"]):
        return run(db, contact, provider, Mcp(), **kw)


def _ended_in_error(result) -> None:
    """12c: the final answer failed, so the turn is an error, as the old round-timeout path set it; never
    answered (an answered turn can also arm the knowledge-miss offer)."""
    assert result.status == "limited", (result.status, result.limit_hit, result.reply_text)
    assert result.limit_hit == "error", (result.status, result.limit_hit, result.reply_text)


def test_T4b_staff_panel_too_little_time_then_the_final_answer_fails_is_an_error(db, contact):
    """12a then 12c: too little time left for a round, the final answer call fails."""
    from app.services.chatbot.agent import loop

    budget = loop.budgets_from_settings(db).max_seconds
    left = loop.ROUND_MIN_SECONDS - 0.5
    clock = {"t": 0.0}
    provider = ScriptedProvider(
        [asks(call()), TimeoutError("slow again")],
        on_call=lambda n: clock.__setitem__("t", budget - left) if n == 1 else None,
    )
    result = _staff_run(db, contact, provider, clock=lambda: clock["t"])

    assert _offered(provider.seen[-1]) == ["answer"]
    assert "could not finish the answer" in result.reply_text, result.reply_text
    _ended_in_error(result)


@pytest.mark.parametrize("timeout", _timeouts(), ids=["TimedOut", "TimeoutError"])
def test_T4c_staff_panel_round_timeout_then_the_final_answer_fails_is_an_error(db, contact, timeout):
    """12b then 12c: a round times out with a tool result in hand, the final answer call fails too."""
    provider = ScriptedProvider([asks(call()), timeout, TimeoutError("slow again")])
    result = _staff_run(db, contact, provider)

    assert _offered(provider.seen[-1]) == ["answer"]
    assert "could not finish the answer" in result.reply_text, result.reply_text
    _ended_in_error(result)


# ------------------------------------------------------------------ UAC 13: the forced final answer gets a real wait


#: What the slow final answer needs of the fake clock (crew trace: a 50-row answer under load ran past 10 s).
FINAL_NEEDS = 20.0
#: Turn time left when the turn goes to its final answer (crew trace 06a33482: ~7 s of 45).
LEFT = 7.0


class SlowFinal(ScriptedProvider):
    """The final answer call (only the answer tool offered) needs FINAL_NEEDS seconds of the fake clock: given less,
    it times out as the provider would; given that much, it answers. Every final call's timeout is recorded."""

    def __init__(self, script, clock, on_call=None):
        super().__init__(script, on_call=on_call)
        self.clock = clock
        self.final_timeouts: list = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        if _offered({"tools": tools}) == ["answer"]:
            from app.services.chatbot.llm_call import TimedOut

            timeout = kw.get("timeout")
            self.final_timeouts.append(timeout)
            if timeout is None or timeout < FINAL_NEEDS:
                self.seen.append({"messages": messages, "tools": tools, "effort": reasoning_effort})
                self.clock["t"] += timeout if timeout is not None else FINAL_NEEDS
                raise TimedOut("the final answer needed longer")
            self.clock["t"] += FINAL_NEEDS
        return super().chat(messages, tools=tools, reasoning_effort=reasoning_effort, **kw)


def _answered_from_results(result) -> None:
    from app.services.chatbot.agent import loop

    assert result.status == "answered", (result.status, result.limit_hit, result.reply_text)
    assert result.limit_hit is None
    assert "could not finish" not in result.reply_text.lower(), result.reply_text
    assert "12 units" in result.reply_text and loop.NOT_VERIFIED not in result.reply_text


def test_T5_a_slow_final_answer_after_the_too_little_time_guard_still_answers(db, contact):
    """UAC 13 on the 12a path: ~7 s left, no new round, and the final answer that needs 20 s completes."""
    from app.services.chatbot.agent import loop

    budget = loop.budgets_from_settings(db).max_seconds
    assert 1 <= LEFT < loop.ROUND_MIN_SECONDS
    clock = {"t": 0.0}
    provider = SlowFinal(
        [asks(call()), answer("There are 12 units.", figures=TWELVE)], clock,
        on_call=lambda n: clock.__setitem__("t", budget - LEFT) if n == 1 else None,
    )
    result = run(db, contact, provider, Mcp(), clock=lambda: clock["t"])

    assert provider.final_timeouts, "the turn went to its final answer"
    _answered_from_results(result)


@pytest.mark.parametrize("timeout", _timeouts(), ids=["TimedOut", "TimeoutError"])
def test_T6_a_slow_final_answer_after_a_round_timeout_still_answers(db, contact, timeout):
    """UAC 13 on the 12b path: the second round times out leaving ~7 s, and the final answer that needs 20 s
    completes."""
    from app.services.chatbot.agent import loop

    budget = loop.budgets_from_settings(db).max_seconds
    clock = {"t": 0.0}
    provider = SlowFinal(
        [asks(call()), timeout, answer("There are 12 units.", figures=TWELVE)], clock,
        # The round's call is sent with the whole turn ahead of it, and times out with ~7 s left.
        on_call=lambda n: clock.__setitem__("t", budget - LEFT) if n == 2 else None,
    )
    result = run(db, contact, provider, Mcp(), clock=lambda: clock["t"])

    assert provider.final_timeouts, "the turn went to its final answer"
    _answered_from_results(result)


def test_T7_the_final_answer_wait_is_always_finite(db, contact):
    """Guard: the real wait is a number of seconds, never None (no timeout) or unbounded."""
    import math

    from app.services.chatbot.agent import loop

    budget = loop.budgets_from_settings(db).max_seconds
    clock = {"t": 0.0}
    provider = SlowFinal(
        [asks(call()), answer("There are 12 units.", figures=TWELVE)], clock,
        on_call=lambda n: clock.__setitem__("t", budget - LEFT) if n == 1 else None,
    )
    run(db, contact, provider, Mcp(), clock=lambda: clock["t"])

    assert provider.final_timeouts
    for timeout in provider.final_timeouts:
        assert isinstance(timeout, (int, float)) and not isinstance(timeout, bool), timeout
        assert math.isfinite(timeout) and timeout > 0, timeout
