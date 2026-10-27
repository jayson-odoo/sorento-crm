"""REPORT-UNIFY security review fix round: red tests (lane side). Harness: the span-pass console of
`test_report_unify_span_binding.py` (its parser config has the lookup lists, so the contact's hidden spec keys are read)."""
from __future__ import annotations

import pytest

from app.services.chatbot import engine as engine_mod
from tests.chatbot.test_report_unify_routing import P_TRAP, YEAR, _status
from tests.chatbot.test_report_unify_span_binding import (  # noqa: F401  (console / bot are fixtures)
    SpanBot,
    _only_report,
    bot,
    console,
)


def test_s2_a_hidden_spec_key_never_rides_the_lane_and_the_reply_never_names_it(bot, monkeypatch) -> None:
    """Security S2: a spec the contact may not see is dropped on every route to the report ask: no `spec` param, and
    the reply does not mention the key or its value at all."""
    monkeypatch.setattr(engine_mod.access_mod, "_hidden_spec_keys", lambda db, **_kw: frozenset({"trap_type"}))
    text, calls = bot.say(_status("sales_report", dict(P_TRAP), basis="delivered", **YEAR), "p trap sales 2026")
    for _name, args in calls:
        assert "spec" not in args, args
    low = text.lower()
    assert "trap" not in low and "spec" not in low, text
