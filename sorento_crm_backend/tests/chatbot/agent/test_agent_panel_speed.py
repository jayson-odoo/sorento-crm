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
    ok = [{"name": LINES, "status": "ok"}]
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
    ok = [{"name": LINES, "status": "ok"}]
    assert narrow_after_query(schemas, [{"name": LINES}], ok, plan_parts=2) == schemas


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


def test_every_main_round_asks_the_provider_to_cache_the_stable_prefix(db):
    """Gemini caches system prompt + tools only when asked (`llm_provider.GeminiProvider._generate`); OpenAI routes on
    the key. One key for the agent's label and the user: the prefix (system prompt with the user's name and date, the
    user's tools) is that user's."""
    from app.models.base import company_scope
    from tests.chatbot.agent import test_agent_quote_compare as qc

    world = _seed_world(db)
    user_id = _viewer(db)
    prov = _KeyProv([_round(_tc(LINES, {"project_id": world.project_id}, "c1")), _answer("Compared.")])
    original = qc.Prov
    qc.Prov = lambda script: prov
    try:
        with company_scope(db, frozenset({world.company_id})):
            qc._panel_run(db, user_id, [], seed_ids=[world.project_id], company_id=world.company_id)
    finally:
        qc.Prov = original
    assert len(prov.keys) == 2 and all(prov.keys), prov.keys
    assert len(set(prov.keys)) == 1
