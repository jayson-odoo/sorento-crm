"""AGENT-PANEL-FIXES C: a quotation compare turn stops resending every tool schema.

Measured on a seeded compare turn with the real MCP catalogue (53 tools offered to an admin): every round sent
93,991 characters of tool schemas (~23.5k tokens) beside a 6,842-character system prompt, a 5,972-character page
note and a 3,431-character tool result. The owner's 3-round turn read 88,995 input tokens.

AGENT-CONTEXT-BUDGET slice 2 retired the narrowing after the lines: step 1 is now the short core set and the list
only grows, so the lines join after it.
"""
from __future__ import annotations

from tests.chatbot.agent.test_agent_quote_compare import (  # noqa: F401 - fixtures
    LINES,
    Prov,
    _answer,
    _listeners,
    _panel_run,
    _round,
    _seed_world,
    _tc,
    _viewer,
    db,
)

names = lambda s: [x["function"]["name"] for x in s]  # noqa: E731


def test_a_whole_turn_whose_ref_is_not_found_keeps_every_tool_for_the_next_round(db):
    from app.models.base import company_scope

    world = _seed_world(db)
    user_id = _viewer(db)
    with company_scope(db, frozenset({world.company_id})):
        _result, prov, _rec = _panel_run(
            db, user_id,
            [_round(_tc(LINES, {"project_id": world.project_id, "refs": ["QT-2026-9999-R1"]}, "c1")), _answer("Not found.")],
            seed_ids=[world.project_id], company_id=world.company_id,
        )
    first, second = (names(s["tools"]) for s in prov.seen)
    # AGENT-CONTEXT-BUDGET slice 2: nothing is taken away; the lines, called before they were loaded, join.
    assert LINES not in first and second == [*first, LINES], (first, second)


def test_a_whole_compare_turn_opens_on_the_core_set_then_adds_only_the_lines(db):
    from app.models.base import company_scope

    world = _seed_world(db)
    user_id = _viewer(db)
    with company_scope(db, frozenset({world.company_id})):
        result, prov, _rec = _panel_run(
            db, user_id, [_round(_tc(LINES, {"project_id": world.project_id}, "c1")), _answer("Compared.")],
            seed_ids=[world.project_id], company_id=world.company_id,
        )
    assert result.status == "answered", (result.status, result.reply_text)
    first, second = (names(s["tools"]) for s in prov.seen)
    # AGENT-CONTEXT-BUDGET slice 2 (replaces the narrowing of C): step 1 is the core set, the lines join after it.
    assert "crm_tools_load" in first and "answer" in first and LINES not in first, first
    assert second == [*first, LINES], second


class _KeyProv(Prov):
    def __init__(self, script):
        super().__init__(script)
        self.keys: list = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        if kw.get("json_schema") is None:
            self.keys.append(kw.get("prompt_cache_key"))
        return super().chat(messages, tools=tools, reasoning_effort=reasoning_effort, **kw)


def _keys_for(db, monkeypatch, provider_name):
    from app.models.base import company_scope
    from app.services.chatbot.agent import loop
    from tests.chatbot.agent import test_agent_quote_compare as qc

    monkeypatch.setattr(loop, "DEFAULT_PROVIDER", provider_name)
    world = _seed_world(db)
    user_id = _viewer(db)
    prov = _KeyProv([_round(_tc(LINES, {"project_id": world.project_id}, "c1")), _answer("Compared.")])
    monkeypatch.setattr(qc, "Prov", lambda script: prov)
    with company_scope(db, frozenset({world.company_id})):
        qc._panel_run(db, user_id, [], seed_ids=[world.project_id], company_id=world.company_id)
    return prov.keys


def test_every_main_round_sends_one_cache_key_to_a_provider_with_an_automatic_cache(db, monkeypatch):
    """OpenAI routes a request to its prompt cache by the key; one key per agent label and user."""
    keys = _keys_for(db, monkeypatch, "openai")
    assert len(keys) == 2 and all(keys) and len(set(keys)) == 1, keys


def test_gemini_gets_no_cache_key(db, monkeypatch):
    """Review round 1: on Gemini the key creates an explicit cache (a blocking create per user, day and tool list),
    not measured yet, so it is not sent."""
    assert _keys_for(db, monkeypatch, "gemini") == [None, None]
