"""AGENTIC-REASONING-VIS (PLAN-agentic-reasoning-vis-30oct.md), red first.

The model's reasoning for each round of an agent turn is asked for, kept on the turn (same trace column
and retention as the steps), returned on both console routes, and never reaches the reply, the memory
history or the tool digest. Providers are stubs; no live LLM call. Every text below is made up.
"""
from __future__ import annotations

import json

from app.services.llm_provider import AnthropicProvider, ChatResult, GeminiProvider
from tests.chatbot.agent.test_agent_loop import (  # noqa: F401 - helpers and fixtures, not tests
    STOCK,
    TWELVE,
    Mcp,
    ScriptedProvider,
    answer,
    asks,
    call,
    contact,
    db,
    run,
)
from tests.test_llm_provider import (
    _AntResponse,
    _AntTextBlock,
    _AntToolUseBlock,
    _AntUsage,
    _GeminiTransport,
    _install,
    _StubAnthropicClient,
)

THOUGHT_1 = "Plan: look up the stock balance for the code first."
THOUGHT_2 = "The balance came back as 12, so answer with that figure."


def _reasoned(result: ChatResult, text: str) -> ChatResult:
    result.reasoning_text = text
    return result


# ------------------------------------------------------------------ Gemini


def _gemini_thought_response() -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": THOUGHT_1, "thought": True},
                        {"functionCall": {"name": "stock_balance", "args": {"code": "ZZT1"}}, "thoughtSignature": "c2ln"},
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5, "thoughtsTokenCount": 7, "totalTokenCount": 23},
    }


def _gemini_thought_and_text_response() -> dict:
    body = _gemini_thought_response()
    body["candidates"][0]["content"]["parts"] = [
        {"text": THOUGHT_2, "thought": True},
        {"text": "There are 12 units."},
    ]
    return body


def test_gemini_asks_for_thoughts_only_when_the_caller_does(monkeypatch):
    t = _install(monkeypatch, _GeminiTransport(_gemini_thought_and_text_response()))
    provider = GeminiProvider("k", default_model="gemini-3.5-flash")
    provider.chat([{"role": "user", "content": "q"}], include_thoughts=True)
    assert t.body["generationConfig"]["thinkingConfig"]["includeThoughts"] is True
    provider.chat([{"role": "user", "content": "q"}])
    assert "includeThoughts" not in t.body["generationConfig"]["thinkingConfig"]


def test_gemini_2_0_gets_no_thinking_config_even_when_thoughts_are_asked(monkeypatch):
    t = _install(monkeypatch, _GeminiTransport(_gemini_thought_and_text_response()))
    GeminiProvider("k", default_model="gemini-2.0-flash").chat([{"role": "user", "content": "q"}], include_thoughts=True)
    assert "thinkingConfig" not in t.body["generationConfig"]


def test_gemini_thought_parts_are_reasoning_never_the_answer(monkeypatch):
    _install(monkeypatch, _GeminiTransport(_gemini_thought_and_text_response()))
    result = GeminiProvider("k").chat([{"role": "user", "content": "q"}], include_thoughts=True)
    assert result.content == "There are 12 units."
    assert result.reasoning_text == THOUGHT_2


def test_gemini_thought_beside_a_function_call_is_reasoning_and_the_call_still_runs(monkeypatch):
    _install(monkeypatch, _GeminiTransport(_gemini_thought_response()))
    result = GeminiProvider("k").chat([{"role": "user", "content": "q"}], include_thoughts=True)
    assert result.content == ""
    assert result.reasoning_text == THOUGHT_1
    assert [c["name"] for c in result.tool_calls] == ["stock_balance"]
    # The signed turn is still replayed whole (#1979).
    assert result.continuation["parts"] == _gemini_thought_response()["candidates"][0]["content"]["parts"]


def test_gemini_without_thought_parts_has_no_reasoning(monkeypatch):
    body = _gemini_thought_and_text_response()
    body["candidates"][0]["content"]["parts"] = [{"text": "plain"}]
    _install(monkeypatch, _GeminiTransport(body))
    result = GeminiProvider("k").chat([{"role": "user", "content": "q"}])
    assert result.content == "plain" and result.reasoning_text == ""


# ------------------------------------------------------------------ Anthropic


class _Thinking:
    def __init__(self, thinking: str) -> None:
        self.type = "thinking"
        self.thinking = thinking
        self.signature = "sig"


def _anthropic(monkeypatch, content, **kwargs):
    stub = _StubAnthropicClient()
    stub.messages._next = _AntResponse(content=content, usage=_AntUsage(3, 4))
    monkeypatch.setattr(AnthropicProvider, "_client", lambda self, **_k: stub)
    result = AnthropicProvider("k").chat([{"role": "user", "content": "q"}], **kwargs)
    return stub.last_kwargs, result


def test_anthropic_thinking_text_is_reasoning_never_the_answer(monkeypatch):
    _, result = _anthropic(
        monkeypatch,
        [_Thinking(THOUGHT_1), _AntTextBlock("checking"), _AntToolUseBlock("toolu_1", "stock_balance", {})],
        model="claude-sonnet-4-6", reasoning_effort="medium", include_thoughts=True,
    )
    assert result.content == "checking"
    assert result.reasoning_text == THOUGHT_1


def test_anthropic_adaptive_thinking_asks_for_a_summary_only_when_thoughts_are_asked(monkeypatch):
    kwargs, _ = _anthropic(
        monkeypatch, [_AntTextBlock("a")], model="claude-opus-5-5", reasoning_effort="medium", include_thoughts=True
    )
    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    kwargs, _ = _anthropic(monkeypatch, [_AntTextBlock("a")], model="claude-opus-5-5", reasoning_effort="medium")
    assert kwargs["thinking"] == {"type": "adaptive"}


def test_anthropic_empty_thinking_gives_no_reasoning(monkeypatch):
    _, result = _anthropic(
        monkeypatch, [_Thinking(""), _AntTextBlock("a")], model="claude-opus-5-5", reasoning_effort="medium"
    )
    assert result.reasoning_text == ""


# ------------------------------------------------------------------ the agent loop


def _two_round_script():
    return [
        _reasoned(asks(call()), THOUGHT_1),
        _reasoned(answer("There are 12 units.", figures=TWELVE), THOUGHT_2),
    ]


def test_the_loop_asks_every_turn_call_for_thoughts(db, contact):
    seen: list[dict] = []

    class Recording(ScriptedProvider):
        def chat(self, messages, **kw):
            seen.append(kw)
            return super().chat(messages, **kw)

    run(db, contact, Recording(_two_round_script()))
    assert [kw.get("include_thoughts") for kw in seen] == [True, True]


def test_each_rounds_reasoning_is_stored_on_the_turn(db, contact):
    from app.services.chatbot.agent import memory

    result = run(db, contact, ScriptedProvider(_two_round_script()))
    steps = memory.steps_for_turn(db, result.turn_id)
    assert steps["reasoning"] == [{"round": 1, "text": THOUGHT_1}, {"round": 2, "text": THOUGHT_2}]
    assert [(c["name"], c["round"]) for c in steps["tool_calls"]] == [(STOCK, 1)]


def test_reasoning_never_reaches_the_reply_the_digest_or_the_result(db, contact):
    from app.models.chatbot_turn import ChatbotTurn

    result = run(db, contact, ScriptedProvider(_two_round_script()))
    row = db.get(ChatbotTurn, result.turn_id)
    for leaked in (result.reply_text, json.dumps(row.response), json.dumps(result.tool_calls)):
        assert THOUGHT_1 not in leaked and THOUGHT_2 not in leaked
    # Control: it IS on the turn, so the test cannot pass because nothing was stored.
    assert THOUGHT_1 in json.dumps(row.trace)


def test_the_next_turn_does_not_send_the_earlier_reasoning_back_to_the_model(db, contact):
    run(db, contact, ScriptedProvider(_two_round_script()))
    second = ScriptedProvider([answer("Hello.")])
    run(db, contact, second, text="and now?")
    sent = json.dumps(second.seen[0]["messages"])
    assert THOUGHT_1 not in sent and THOUGHT_2 not in sent
    assert "There are 12 units." in sent  # control: the history itself is there


def test_reasoning_is_clipped_and_carries_no_record_id(db, contact):
    from app.services.chatbot.agent import memory

    rid = "0f8fad5b-d9cb-469f-a165-70867728950e"
    long = f"Record {rid} looks right. " + "x" * 9000
    script = [_reasoned(answer("Hello."), long)]
    result = run(db, contact, ScriptedProvider(script))
    (entry,) = memory.steps_for_turn(db, result.turn_id)["reasoning"]
    assert rid not in entry["text"]
    assert entry["text"].startswith("Record ")
    assert len(entry["text"]) <= 4001


def test_a_turn_without_reasoning_has_an_empty_list(db, contact):
    from app.services.chatbot.agent import memory

    result = run(db, contact, ScriptedProvider([asks(call()), answer("There are 12 units.", figures=TWELVE)]))
    assert memory.steps_for_turn(db, result.turn_id)["reasoning"] == []


def test_the_forced_final_answers_reasoning_follows_the_last_round(db, contact):
    from app.models.user import SystemSetting
    from app.services.chatbot.agent import memory

    row = db.query(SystemSetting).first() or SystemSetting()
    row.chatbot_agent_max_rounds = 1
    db.add(row)
    db.flush()
    script = [_reasoned(asks(call()), THOUGHT_1), _reasoned(answer("There are 12 units.", figures=TWELVE), THOUGHT_2)]
    result = run(db, contact, ScriptedProvider(script), Mcp())
    assert result.status == "limited"
    assert memory.steps_for_turn(db, result.turn_id)["reasoning"] == [
        {"round": 1, "text": THOUGHT_1},
        {"round": 2, "text": THOUGHT_2},
    ]


def test_steps_from_an_older_trace_still_read():
    from app.services.chatbot.agent.memory import steps_from_trace

    trace = [
        {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 1, "completion_tokens": 1},
        {"kind": "agent_tool", "name": STOCK, "status": "ok", "ms": 4},
    ]
    steps = steps_from_trace(trace)
    assert steps["reasoning"] == []
    assert steps["tool_calls"] == [{"name": STOCK, "status": "ok", "ms": 4, "round": 1}]



def test_reasoning_carries_none_of_the_contacts_own_ids(db, contact):
    from app.services.chatbot.agent import memory

    script = [_reasoned(answer("Hello."), f"The contact {contact['respond_id']} asked about stock.")]
    result = run(db, contact, ScriptedProvider(script))
    (entry,) = memory.steps_for_turn(db, result.turn_id)["reasoning"]
    assert contact["respond_id"] not in entry["text"]
    assert entry["text"].startswith("The contact ")
