"""CHAT-LANGUAGE slice 2: compose still recognises the localized bare "no results" fallback."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.chatbot import label_catalog
from app.services.chatbot.label_catalog import Localizer
from app.services.chatbot.turn.compose import compose

from tests.chatbot.test_chat_language_render import _env, _policy, _state


def _text(lane_text: str, lang: str | None) -> str:
    ctx = SimpleNamespace(localizer=Localizer(lang, label_catalog.defaults(lang))) if lang else None
    env = _env(lane_text)
    env["figures"] = []
    return compose([env], _state(), _policy(), ctx=ctx).text


def test_the_english_bare_fallback_is_replaced_by_the_subject_line():
    text = _text("No matching results found.", None)
    assert "No matching results found." not in text
    assert "found for" in text


def test_an_ms_and_a_zh_bare_fallback_are_recognised_the_same_way():
    for lang in ("ms", "zh"):
        localized = label_catalog.LABELS["No matching results found."][lang]
        text = _text(localized, lang)
        assert localized not in text, lang
        assert "found for" in text, lang
