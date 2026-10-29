"""AGENTIC-P1 card sections 1, 5, 6, 7: the tool loop, its budgets, the figure check.

Postgres via the blank schema for the contact, user and turn row. No live LLM and no MCP:
a scripted provider returns `ChatResult` objects from a list and records (deep copies of)
what it was sent; `mcp_call` is a recording fake.
"""
from __future__ import annotations

import copy
import json

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.agent._seed import seed_agent_contact

STOCK = "crm_inventory_stock_balance_list"

CATALOG = {
    STOCK: {
        "description": "Stock on hand",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "space_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["contact_id", "space_id", "query"],
        },
    },
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def contact(db):
    return seed_agent_contact(db)


def call(name=STOCK, args=None, cid="call-1"):
    return {"id": cid, "name": name, "arguments": {"query": "SRTWT7445"} if args is None else args}


def answer(text, *, prompt=100, completion=10, cached=0):
    return ChatResult(
        content=text, prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion, cached_tokens=cached,
    )


def asks(*calls, prompt=100, completion=10, continuation=None, cached=0):
    return ChatResult(
        content="", prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion, tool_calls=list(calls), continuation=continuation,
        cached_tokens=cached,
    )


class ScriptedProvider:
    def __init__(self, script, on_call=None):
        self.script = list(script)
        self.seen: list[dict] = []
        self.on_call = on_call

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append(
            {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "effort": reasoning_effort}
        )
        if self.on_call:
            self.on_call(len(self.seen))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Mcp:
    def __init__(self, result=None):
        self.result = {"items": [{"qty": 12}], "has_result": True} if result is None else result
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return self.result


def _set_budgets(db, **cols):
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    for k, v in cols.items():
        setattr(row, k, v)
    db.flush()
    return row


def run(db, contact, provider, mcp=None, text="stock of SRTWT7445?", **kw):
    from app.services.agent.loop import run_agent_turn

    return run_agent_turn(
        db,
        contact_respond_id=contact["respond_id"],
        text=text,
        provider=provider,
        mcp_call=mcp or Mcp(),
        catalog=CATALOG,
        **kw,
    )


def _turn_row(db, result):
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()


# ------------------------------------------------------------------ a normal turn


def test_a_two_round_turn_calls_the_tool_then_answers(db, contact):
    provider = ScriptedProvider([asks(call()), answer("There are 12 units.")])
    mcp = Mcp()

    result = run(db, contact, provider, mcp)

    assert result.status == "answered"
    assert result.limit_hit is None
    assert result.rounds == 2
    assert result.reply_text == "There are 12 units."
    assert [(c["name"], c["status"]) for c in result.tool_calls] == [(STOCK, "ok")]
    assert "ms" in result.tool_calls[0]
    assert len(provider.seen) == 2
    assert mcp.calls[0][0] == STOCK
    assert mcp.calls[0][1]["contact_id"] == contact["respond_id"]


def test_the_first_call_sees_a_system_prompt_the_user_text_and_only_permitted_tools(db, contact):
    provider = ScriptedProvider([answer("Hello.")])
    run(db, contact, provider, text="hello there")

    first = provider.seen[0]
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][-1] == {"role": "user", "content": "hello there"}
    # the seeded user holds inventory.stock.view and order_management.orders.view
    names = {t["function"]["name"] for t in first["tools"]}
    assert STOCK in names
    assert "crm_procurement_grn_summary" not in names
    for t in first["tools"]:
        props = t["function"]["parameters"]["properties"]
        assert "contact_id" not in props and "space_id" not in props


def test_the_turn_writes_one_agent_row(db, contact):
    provider = ScriptedProvider([asks(call()), answer("There are 12 units.")])
    result = run(db, contact, provider)

    rows = db.query(ChatbotTurn).filter(ChatbotTurn.contact_respond_id == contact["respond_id"]).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == result.turn_id
    assert row.ingress == "agent"
    assert row.is_test is True
    assert row.status == "done"
    assert row.envelope["text"] == "stock of SRTWT7445?"
    assert row.envelope["agent_conversation_id"] == result.conversation_id
    assert row.response["reply_text"] == "There are 12 units."
    assert row.response["status"] == "answered"
    assert row.response["limit_hit"] is None
    digest = row.response["tool_digest"]
    assert len(digest) == 1 and digest[0]["name"] == STOCK and digest[0]["status"] == "ok"
    trace_text = json.dumps(row.trace)
    assert "agent_round" in trace_text and "agent_tool" in trace_text


def test_usage_is_summed_over_the_turns_model_calls_and_logged(db, contact):
    from app.models.ai_assistant import AIAssistantUsageLog

    provider = ScriptedProvider(
        [asks(call(), prompt=100, completion=10, cached=40), answer("There are 12 units.", prompt=150, completion=20, cached=60)]
    )
    result = run(db, contact, provider)

    assert result.usage == {
        "prompt_tokens": 250, "completion_tokens": 30, "cached_tokens": 100, "calls": 2,
    }
    rows = db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_agent").all()
    assert rows
    assert sum(r.prompt_tokens for r in rows) == 250
    assert sum(r.completion_tokens for r in rows) == 30


def test_round_two_replays_the_round_one_continuation_unchanged(db, contact):
    signature = {"provider": "gemini", "parts": [{"thoughtSignature": "SIG-ABC", "functionCall": {"name": STOCK}}]}
    provider = ScriptedProvider([asks(call(), continuation=signature), answer("There are 12 units.")])

    run(db, contact, provider)

    second = provider.seen[1]["messages"]
    assistants = [m for m in second if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["continuation"] == signature
    assert assistants[0]["tool_calls"][0]["id"] == "call-1"
    assert assistants[0]["tool_calls"][0]["function"]["name"] == STOCK
    tool_msgs = [m for m in second if m["role"] == "tool"]
    assert len(tool_msgs) == 1 and tool_msgs[0]["tool_call_id"] == "call-1"
    assert "12" in tool_msgs[0]["content"]


def test_an_assistant_message_without_a_continuation_has_no_such_key(db, contact):
    provider = ScriptedProvider([asks(call()), answer("There are 12 units.")])
    run(db, contact, provider)
    assistants = [m for m in provider.seen[1]["messages"] if m["role"] == "assistant"]
    assert "continuation" not in assistants[0]


# ------------------------------------------------------------------ budgets


def test_max_rounds_forces_a_final_call_with_no_tools(db, contact):
    _set_budgets(db, chatbot_agent_max_rounds=2)
    provider = ScriptedProvider(
        [asks(call(cid="c1")), asks(call(cid="c2")), answer("I could only check part of it.")]
    )

    result = run(db, contact, provider)

    assert result.status == "limited"
    assert result.limit_hit == "rounds"
    assert result.rounds == 2
    assert result.reply_text == "I could only check part of it."
    assert len(provider.seen) == 3
    assert provider.seen[0]["tools"] and provider.seen[1]["tools"]
    assert provider.seen[2]["tools"] is None
    row = _turn_row(db, result)
    assert row.response["limit_hit"] == "rounds" and row.response["status"] == "limited"


def test_max_seconds_uses_the_injected_clock(db, contact):
    clock = {"t": 0.0}
    provider = ScriptedProvider(
        [asks(call(cid="c1")), answer("Partial answer.")],
        on_call=lambda n: clock.__setitem__("t", clock["t"] + 100.0) if n == 1 else None,
    )

    result = run(db, contact, provider, clock=lambda: clock["t"])

    assert result.status == "limited"
    assert result.limit_hit == "seconds"
    assert provider.seen[-1]["tools"] is None


def test_max_input_tokens_sums_prompt_tokens_across_calls(db, contact):
    _set_budgets(db, chatbot_agent_max_input_tokens=10_000)
    provider = ScriptedProvider([asks(call(), prompt=10_001), answer("Partial answer.")])

    result = run(db, contact, provider)

    assert result.status == "limited"
    assert result.limit_hit == "input_tokens"
    assert provider.seen[-1]["tools"] is None


def test_more_than_four_calls_in_a_round_run_four_and_deny_the_rest(db, contact):
    six = [call(cid=f"c{i}", args={"query": f"q{i}"}) for i in range(6)]
    provider = ScriptedProvider([asks(*six), answer("There are 12 units.")])
    mcp = Mcp()

    result = run(db, contact, provider, mcp)

    assert len(mcp.calls) == 4
    tool_msgs = [m for m in provider.seen[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == [f"c{i}" for i in range(6)]
    for extra in tool_msgs[4:]:
        assert "denied" in extra["content"].lower()
    assert result.status == "answered"


def test_budgets_default_when_no_settings_row(db):
    from app.services.agent.loop import Budgets, budgets_from_settings

    assert db.query(SystemSetting).count() == 0
    b = budgets_from_settings(db)
    assert isinstance(b, Budgets)
    assert (b.max_rounds, b.max_seconds, b.max_input_tokens, b.compact_tokens, b.calls_per_round) == (
        8, 45, 150_000, 40_000, 4,
    )


def test_budgets_read_the_four_system_settings_columns(db):
    from app.services.agent.loop import budgets_from_settings

    _set_budgets(
        db,
        chatbot_agent_max_rounds=3,
        chatbot_agent_max_seconds=20,
        chatbot_agent_max_input_tokens=50_000,
        chatbot_agent_compact_tokens=9_000,
    )
    b = budgets_from_settings(db)
    assert (b.max_rounds, b.max_seconds, b.max_input_tokens, b.compact_tokens) == (3, 20, 50_000, 9_000)


def test_a_fresh_settings_row_carries_the_documented_defaults(db):
    from app.services.agent.loop import budgets_from_settings

    _set_budgets(db)
    db.refresh(db.query(SystemSetting).first())
    b = budgets_from_settings(db)
    assert (b.max_rounds, b.max_seconds, b.max_input_tokens, b.compact_tokens) == (8, 45, 150_000, 40_000)


# ------------------------------------------------------------------ failure


def test_a_provider_error_before_any_tool_result_is_a_failed_turn(db, contact):
    provider = ScriptedProvider([RuntimeError("provider down")])

    result = run(db, contact, provider)

    assert result.status == "failed"
    assert result.reply_text.startswith("The agent could not answer")
    row = _turn_row(db, result)
    assert row.status == "failed"
    assert row.ingress == "agent" and row.is_test is True


def test_no_provider_and_no_key_is_a_failed_turn_not_a_crash(db, contact):
    from app.services.agent.loop import run_agent_turn

    result = run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text="hi", mcp_call=Mcp(), catalog=CATALOG
    )
    assert result.status == "failed"
    assert result.reply_text.startswith("The agent could not answer")


def test_a_provider_error_after_a_tool_result_takes_the_limit_path(db, contact):
    provider = ScriptedProvider([asks(call()), RuntimeError("provider blip"), answer("Partial answer.")])

    result = run(db, contact, provider)

    assert result.status == "limited"
    assert result.reply_text == "Partial answer."
    assert provider.seen[-1]["tools"] is None


def test_a_refused_contact_propagates_agent_refused(db):
    from app.services.agent.access import AgentRefused
    from app.services.agent.loop import run_agent_turn

    with pytest.raises(AgentRefused) as exc:
        run_agent_turn(
            db, contact_respond_id="ZZT-nobody", text="hi", provider=ScriptedProvider([]), mcp_call=Mcp(),
            catalog=CATALOG,
        )
    assert exc.value.reason == "contact_not_found"


# ------------------------------------------------------------------ figure check


def test_an_unsupported_figure_triggers_one_repair_round(db, contact):
    provider = ScriptedProvider(
        [asks(call()), answer("There are 99 units."), answer("There are 12 units.")]
    )

    result = run(db, contact, provider)

    assert result.reply_text == "There are 12 units."
    assert result.status == "answered"
    assert len(provider.seen) == 3
    repair_prompt = json.dumps(provider.seen[2]["messages"][-1])
    assert "99" in repair_prompt


def test_a_figure_still_unsupported_after_the_repair_is_replaced(db, contact):
    provider = ScriptedProvider(
        [asks(call()), answer("There are 99 units."), answer("Still 99 units here.")]
    )

    result = run(db, contact, provider)

    assert "99" not in result.reply_text
    assert "(not verified)" in result.reply_text
    assert len(provider.seen) == 3  # one repair round only


def test_a_figure_from_the_users_own_message_is_supported(db, contact):
    provider = ScriptedProvider([answer("Here are 50 rows.")])

    result = run(db, contact, provider, text="show me 50 rows")

    assert result.reply_text == "Here are 50 rows."
    assert len(provider.seen) == 1


@pytest.mark.parametrize(
    "reply, sources, expected",
    [
        ("Stock is 1,200 units", ['{"qty": 1200}'], []),
        ("Stock is 1200 units", ["qty 1,200"], []),
        ("Total 45.5", ['{"total": 45.5}'], []),
        ("Total 45.5", ['{"total": 40}'], ["45.5"]),
        ("As of 2026-10-29 there are 7", ["7"], []),
        ("SRTWT7445 has 7 units", ["7"], []),
        ("There are 99 and 12", ["12"], ["99"]),
        ("No figures here", [], []),
    ],
)
def test_unsupported_figures(reply, sources, expected):
    from app.services.agent.loop import unsupported_figures

    assert sorted(unsupported_figures(reply, sources)) == sorted(expected)


# ------------------------------------------------------------------ memory read-back


def test_history_from_an_earlier_turn_appears_in_the_next_turns_messages(db, contact):
    first = ScriptedProvider([answer("Hello there.")])
    run(db, contact, first, text="first question")

    second = ScriptedProvider([answer("Welcome back.")])
    run(db, contact, second, text="second question")

    msgs = second.seen[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert {"role": "user", "content": "first question"} in msgs
    assistant = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["content"].startswith("Hello there.")
    assert msgs[-1] == {"role": "user", "content": "second question"}
    assert msgs.index({"role": "user", "content": "first question"}) < msgs.index(assistant[0])


def test_a_new_conversation_hides_earlier_turns_from_the_next_turn(db, contact):
    from app.services.agent import memory

    run(db, contact, ScriptedProvider([answer("Hello there.")]), text="first question")
    memory.new_conversation(db, contact["respond_id"])

    second = ScriptedProvider([answer("Fresh start.")])
    run(db, contact, second, text="second question")

    contents = [m["content"] for m in second.seen[0]["messages"] if isinstance(m.get("content"), str)]
    assert "first question" not in contents
