"""AGENT-PANEL-FIXES C: a quotation compare turn stops resending every tool schema.

Measured on a seeded compare turn with the real MCP catalogue (53 tools offered to an admin): every round sent
93,991 characters of tool schemas (~23.5k tokens) beside a 6,842-character system prompt, a 5,972-character page
note and a 3,431-character tool result. The owner's 3-round turn read 88,995 input tokens.
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


def _schemas(*extra):
    return [{"type": "function", "function": {"name": n}} for n in
            (LINES, "crm_query", "crm_describe", "answer", "plan", "crm_inventory_stock_balance_list", *extra)]


def test_after_a_quotation_lines_round_that_answered_only_that_tool_and_answer_remain():
    from app.services.chatbot.agent.loop import narrow_after_query

    schemas = _schemas()
    ok = [{"name": LINES, "status": "ok", "complete": True}]
    assert names(narrow_after_query(schemas, [{"name": LINES}], ok)) == [LINES, "answer", "plan"]
    assert names(narrow_after_query(schemas, [{"name": "plan"}, {"name": LINES}], ok)) == [LINES, "answer", "plan"]


def test_a_quotation_lines_round_that_failed_or_ran_beside_another_tool_keeps_every_schema():
    from app.services.chatbot.agent.loop import narrow_after_query

    schemas = _schemas()
    assert narrow_after_query(schemas, [{"name": LINES}], [{"name": LINES, "status": "invalid"}]) == schemas
    both = [{"name": LINES, "status": "ok"}, {"name": "crm_inventory_stock_balance_list", "status": "ok"}]
    assert narrow_after_query(schemas, [{"name": LINES}, {"name": "crm_inventory_stock_balance_list"}], both) == schemas


def test_a_multi_part_question_keeps_every_schema_after_the_lines():
    from app.services.chatbot.agent.loop import narrow_after_query

    schemas = _schemas()
    ok = [{"name": LINES, "status": "ok", "complete": True}]
    assert narrow_after_query(schemas, [{"name": LINES}], ok, plan_parts=2) == schemas


def test_a_lookup_with_a_ref_not_found_or_no_document_keeps_every_schema():
    """Review round 1: the tool answers ok with refs in not_found (another project's quotation), so the model still
    needs crm_projects_find and the rest."""
    from app.services.chatbot.agent.loop import narrow_after_query

    schemas = _schemas()
    assert narrow_after_query(schemas, [{"name": LINES}], [{"name": LINES, "status": "ok"}]) == schemas


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
    assert sorted(second) == sorted(first)


def test_a_whole_compare_turn_sends_the_full_tool_list_once_then_only_the_lines_and_answer(db):
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
    assert len(first) > 3 and LINES in first
    assert sorted(second) == sorted([LINES, "answer", "plan"]), second


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
