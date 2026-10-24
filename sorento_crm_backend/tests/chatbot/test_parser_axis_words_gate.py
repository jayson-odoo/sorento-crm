"""REPORT-SMART-L R6: `by_words` is read by the sales ranking lane, where a PRESENT null means "no axis typed". The
schema is shared by every prompt version and strict output requires every key, so a version that does not define the
field (production v92) would answer null on every parse. The parser layer therefore follows the prompt, as it does for
`compare_to`: no definition in the prompt text, no key in the schema and none in the verdict. Fake data only."""
from __future__ import annotations

import json

from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_parser_gemini_lite import _capture_chat, _config, _emission_result


def _with_by_words(value):
    return _emission_result(content=json.dumps({**{k: None for k in parser_mod.DECLARED_KEYS}, "by_words": value}))


def test_a_prompt_that_does_not_define_by_words_never_yields_the_key(monkeypatch) -> None:
    _capture_chat(monkeypatch, _with_by_words(None))
    out = parser_mod.parse(_config(by_words=False), "block")
    assert "by_words" not in out


def test_a_prompt_that_defines_by_words_keeps_the_key(monkeypatch) -> None:
    _capture_chat(monkeypatch, _with_by_words(None))
    out = parser_mod.parse(_config(by_words=True), "block")
    assert "by_words" in out and out["by_words"] is None
    _capture_chat(monkeypatch, _with_by_words("by customer"))
    assert parser_mod.parse(_config(by_words=True), "block")["by_words"] == "by customer"


def test_the_schema_sent_follows_the_prompt(monkeypatch) -> None:
    seen = _capture_chat(monkeypatch, _with_by_words(None))
    parser_mod.parse(_config(by_words=False), "block")
    sent = seen[0]["json_schema"]
    assert "by_words" not in sent["properties"] and "by_words" not in sent["required"]
    parser_mod.parse(_config(by_words=True), "block")
    sent = seen[1]["json_schema"]
    assert "by_words" in sent["properties"] and "by_words" in sent["required"]
    # a bare config keeps the extended schema, like `report_fields`
    assert parser_mod.ParserConfig(system_prompt="", prompt_version=1, provider="p", model="m", api_key="k").by_words is True
