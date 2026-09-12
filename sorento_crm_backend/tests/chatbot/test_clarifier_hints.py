"""AC-1024: the low-signal clarifier receives `focus_hints` + `open_question: None`;
`casual` gives it nothing.

Today `lanes/casual.py::construct_user_prompt` returns six fields
(`message_type, intent_hint, domain_hint, session_vars, entities, user_goal`) and blanks
`session_vars` to `{}` for `casual` / `unknown`. Lane 1 (D15) replaces the raw
`session_vars` echo with the dialogue module's typed hints: `focus_hints` (alive slots
only) for `low_signal` and `unknown`, `open_question: None` alongside it, and nothing at
all for `casual`.

RED: `construct_user_prompt`'s output has no `focus_hints` key at all yet.
"""
from __future__ import annotations

from app.services.chatbot.lanes import casual


def _ctx(message_type: str = "clarification", intent_hint=None, domain_hint=None, user_goal="hi", text="hi"):
    return {
        "parse": {
            "output": {
                "message_type": message_type,
                "intent_hint": intent_hint,
                "domain_hint": domain_hint,
                "user_goal": user_goal,
            }
        },
        "session": {
            "session_vars": {
                "variables": {
                    "focus": {"products": {"value": [{"code": "ZZT-1"}], "set_at_turn": 1}},
                    "open_question": None,
                }
            }
        },
        "text": {"message": {"message": {"text": text}}},
    }


class TestClarifierReceivesFocusHints:
    def test_low_signal_and_unknown_receive_focus_hints_and_null_open_question(self) -> None:
        # `low_signal` is the LANE's name (`lanes/casual.py`'s own docstring: "the
        # `low_signal` lane"); the parser's `message_type` value that reaches it is
        # `clarification` (see `MESSAGE_TYPES` in contracts.py - there is no literal
        # `"low_signal"` message_type). `unknown` is a message_type in its own right.
        for message_type in ("clarification", "unknown"):
            ctx = _ctx(message_type=message_type)
            out = casual.construct_user_prompt(ctx, {"resolutions": []})
            assert "focus_hints" in out, (
                f"construct_user_prompt has no focus_hints key yet for {message_type!r} "
                f"(keys={sorted(out)})"
            )
            assert out.get("open_question") is None, message_type

    def test_casual_receives_nothing(self) -> None:
        ctx = _ctx(message_type="casual")
        out = casual.construct_user_prompt(ctx, {"resolutions": []})
        assert "focus_hints" not in out
        assert not out.get("session_vars")
        assert "open_question" not in out
