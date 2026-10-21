"""OVERNIGHT reset class: after "Clear all" the small-talk reply said "Last time: <today>, Stock:
Asked about stock for ..." where "Last time" was TODAY's still-open conversation. "Last time"
names a CLOSED episode only; with none, there is no "Last time" line. The history list other
readers get (a history question) still holds the open conversation first.

Same play harness as the S4 fallback corpus (`test_memory_s4_fallback_replay`): synthetic
contact, the parser and the clarifier stubbed, real engine and memory.
"""
from __future__ import annotations

from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_memory_s4_fallback_replay import (  # noqa: F401
    _Lane,
    _play,
    lane,
    sent_text,
)

OPEN_CODE = "ZZTOPEN100"
CLOSED_CODE = "ZZTSHUT200"
STOCK_TURN = {
    "message": f"check stock {OPEN_CODE}",
    "verdict": {
        "domain_hint": "inventory",
        "entities": [
            {"raw": OPEN_CODE, "hint": "product", "canonical_code": OPEN_CODE, "current_message": True,
             "confident": True, "hint_confident": True}
        ],
    },
}
CLOSED_FRAME = {
    "days_ago": 2,
    "domain": "inventory",
    "summary": f"Asked about stock for {CLOSED_CODE}, but nothing was found.",
}


def _case(*, frames: list, turn_verdict: dict, message: str = "clear all") -> dict:
    return {
        "given": {"memory_level": "full", "first_name": "Tan", "frames": frames, "live_turns": [STOCK_TURN]},
        "turn": {"message": message, "verdict": turn_verdict, "clarifier": {"ack": "Sure.", "language": "en"}},
    }


SMALL_TALK = {"message_type": "casual"}


def test_only_an_open_conversation_today_has_no_last_time_line(session_factory, stub_access, lane):
    case = _case(frames=[], turn_verdict=SMALL_TALK)
    result, _prompt, _pk = _play(session_factory, stub_access, lane, case, "clear all", ablate=False)
    sent = sent_text(result)
    assert "Last time" not in sent, sent
    assert OPEN_CODE not in sent, sent


def test_last_time_names_the_closed_episode_not_the_open_conversation(session_factory, stub_access, lane):
    case = _case(frames=[CLOSED_FRAME], turn_verdict=SMALL_TALK)
    result, _prompt, _pk = _play(session_factory, stub_access, lane, case, "clear all", ablate=False)
    sent = sent_text(result)
    assert "Last time: " in sent, sent
    assert CLOSED_CODE in sent and OPEN_CODE not in sent, sent


def test_guard_a_history_question_still_lists_the_open_conversation_first(session_factory, stub_access, lane):
    case = _case(
        frames=[CLOSED_FRAME],
        turn_verdict={"message_type": "history_question", "domain_hint": None, "intent_hint": None, "entities": []},
        message="what did i ask",
    )
    result, _prompt, _pk = _play(session_factory, stub_access, lane, case, "what did i ask", ablate=False)
    sent = sent_text(result)
    assert OPEN_CODE in sent and CLOSED_CODE in sent, sent
    assert sent.index(OPEN_CODE) < sent.index(CLOSED_CODE), sent
