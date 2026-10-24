"""REPORT-SMART-L R6 review: production (a CLOSED LISTS prompt that never defines `axis_words`) stays off: the config
says so and the closed-lists strict schema carries no such key. Fake template only."""
from __future__ import annotations

from app.services.chatbot.head import closed_lists_prompt
from tests.chatbot.test_chat_state_parser_input import (  # noqa: F401 - fixture + helper
    _fresh_prompt_cache,
    _resolve,
)

BASE = "Rules {{current_date}}. compare_to previous_period.\n" + closed_lists_prompt.MARKER + "\nlisted items.\n"


def test_a_closed_lists_prompt_that_never_says_axis_words_stays_off(monkeypatch, session_factory) -> None:
    config = _resolve(monkeypatch, session_factory, BASE)
    assert config.closed_lists is True
    assert config.axis_words is False
    assert config.json_schema is not None
    assert "axis_words" not in config.json_schema["properties"]
    assert "axis_words" not in config.json_schema["required"]


def test_a_closed_lists_prompt_that_defines_axis_words_offers_it(monkeypatch, session_factory) -> None:
    config = _resolve(monkeypatch, session_factory, BASE + "axis_words: the words naming the ranked axis, or null.\n")
    assert config.closed_lists is True and config.axis_words is True
    assert "axis_words" in config.json_schema["properties"] and "axis_words" in config.json_schema["required"]
