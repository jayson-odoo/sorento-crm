"""CHAT-LANGUAGE fix round 1, item 2 (B2): the reply language carries between turns.

Through `engine.run_turn` (the r9 console harness): an ms message, then a turn whose message
decides nothing, keeps the ms reply and writes `reply_language` "ms" into the session patch.
A second test drives the `run_tail` payload arm directly.
"""
from __future__ import annotations

from tests.chatbot._r9_engine_console import EngineConsole, product, stock
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture


def test_item2_an_ms_message_then_a_decision_free_turn_stays_ms(
    session_factory, monkeypatch, stub_access
):
    c = EngineConsole(session_factory, monkeypatch, stub_access, phone="+60000009301")
    c.say("ada stok SRTWC286-SH?", stock(product("SRTWC286-SH")))
    assert c.state["reply_language"] == "ms"

    # "SRTWC286-SH 2" has no marker word: nothing decides, the conversation's ms carries.
    second = c.say("SRTWC286-SH 2", stock(product("SRTWC286-SH", 2)))
    assert second.startswith("SRTWC286-SH x 2: kuantiti ini melebihi")
    assert "Sila rujuk jurujual anda." in second
    assert c.state["reply_language"] == "ms"


def test_item2_the_run_tail_payload_arm_writes_the_turn_language():
    """`run_tail`'s own payload (engine.py, the `reply_language` key): the item's language
    wins, else the carried one, else None."""
    from app.services.chatbot import engine

    seen: dict = {}

    def capture(db, *, respond_io_id, payload, base, turn_id):
        seen.update(payload)

    from app.services.chatbot.turn import state as turn_state

    import pytest

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(engine.turn_tail, "write_merged", capture)
        mp.setattr(engine, "_log_session_write", lambda *a, **k: None)
        for item, before, expected in (
            ({"reply_language": "zh"}, {"reply_language": "ms"}, "zh"),
            ({}, {"reply_language": "ms"}, "ms"),
            ({}, {}, None),
        ):
            seen.clear()
            engine.run_tail(
                _FakeDb(),
                turn_id="t",
                ctx={"session": {"session_vars": {}}},
                item=item,
                values={"answer": None},
                canned=None,
                branch_kind="casual",
                dry_run=False,
                contact_respond_id="c",
                turn_trace=_Trace(),
                state=turn_state.State(
                    focus=turn_state.Focus(), pending=None, profile=turn_state.Profile(), turn_no=1
                ),
                remembered_before=before,
            )
            assert seen.get("reply_language") == expected, (item, before, seen)
    finally:
        mp.undo()


class _FakeDb:
    def execute(self, *a, **k):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class _Trace:
    def record(self, *a, **k):
        return None

    def add(self, *a, **k):
        return None
