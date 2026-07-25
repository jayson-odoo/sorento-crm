"""Item 3b — turn-scoped, strictly-keyed tool/guide result cache.

Two layers of test:

  * **Key / behavior unit tests** on ``_TurnToolCache`` directly — dedup within a
    turn (UAC3b.1), cross-user / conversation / turn isolation (UAC3b.2 SECURITY),
    and turn-scoping (UAC3b.3). These are pure, deterministic, network-free.
  * **Agent-loop wiring test** — proves ``_run_agent_loop`` routes its live MCP
    calls through the cache, so two identical tool calls in one turn issue only
    ONE live invocation (UAC3b.1 / UAC3b.4) — asserted via a call counter on a
    fake MCP client.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.ai_assistant_service import (
    AIAssistantChatService,
    _TurnToolCache,
)
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session


# ===========================================================================
# _TurnToolCache unit tests — key discipline + dedup + isolation
# ===========================================================================


class _Loader:
    """Counts how many times the live loader was invoked."""

    def __init__(self, ret: str):
        self.calls = 0
        self._ret = ret

    def __call__(self) -> str:
        self.calls += 1
        return self._ret


def _cache(user="u-A", conv="c-1", turn="t-1") -> _TurnToolCache:
    return _TurnToolCache(user_id=user, conversation_id=conv, turn_id=turn)


# --- UAC3b.1 — same tool + identical args twice in a turn → ONE live call ----
def test_identical_call_within_turn_is_cached():
    cache = _cache()
    loader = _Loader("STOCK=42")

    first = cache.get_or_call("crm_stock", {"sku": "ABC", "warehouse": "KL"}, loader)
    second = cache.get_or_call("crm_stock", {"sku": "ABC", "warehouse": "KL"}, loader)

    assert first == second == "STOCK=42"
    assert loader.calls == 1, "second identical call must be served from cache, not re-run"
    assert cache.live_calls == 1
    assert cache.hits == 1


def test_arg_order_does_not_change_key():
    """Canonical sorted-args hashing: {a,b} and {b,a} are the same call."""
    cache = _cache()
    loader = _Loader("X")
    cache.get_or_call("crm_stock", {"sku": "ABC", "warehouse": "KL"}, loader)
    cache.get_or_call("crm_stock", {"warehouse": "KL", "sku": "ABC"}, loader)
    assert loader.calls == 1


def test_different_args_are_separate_calls():
    cache = _cache()
    loader = _Loader("X")
    cache.get_or_call("crm_stock", {"sku": "ABC"}, loader)
    cache.get_or_call("crm_stock", {"sku": "XYZ"}, loader)
    assert loader.calls == 2, "different args must each issue a live call"
    assert cache.live_calls == 2
    assert cache.hits == 0


def test_different_tool_same_args_are_separate_calls():
    cache = _cache()
    loader = _Loader("X")
    cache.get_or_call("crm_stock", {"id": "1"}, loader)
    cache.get_or_call("crm_orders", {"id": "1"}, loader)
    assert loader.calls == 2


# --- UAC3b.2 (SECURITY) — cross-user / conversation / turn isolation ---------
def test_different_user_never_shares_cache_entry():
    """User B must NEVER receive user A's cached result. Distinct user_id =>
    distinct key => structural miss."""
    args = {"sku": "ABC"}
    a = _cache(user="user-A")
    b = _cache(user="user-B")

    # Keys must differ purely on principal.
    assert a.key("crm_stock", args) != b.key("crm_stock", args)

    a_loader = _Loader("A-only-secret")
    b_loader = _Loader("B-only-secret")
    a.get_or_call("crm_stock", args, a_loader)
    b_value = b.get_or_call("crm_stock", args, b_loader)

    assert b_value == "B-only-secret", "user B must get B's own result, never A's"
    assert b_loader.calls == 1, "user B's cache must miss and run its own loader"
    assert b.key("crm_stock", args) not in {a.key("crm_stock", args)}


def test_different_conversation_never_shares_cache_entry():
    args = {"sku": "ABC"}
    c1 = _cache(conv="conv-1")
    c2 = _cache(conv="conv-2")
    assert c1.key("crm_stock", args) != c2.key("crm_stock", args)


def test_different_turn_never_shares_cache_entry():
    args = {"sku": "ABC"}
    t1 = _cache(turn="turn-1")
    t2 = _cache(turn="turn-2")
    assert t1.key("crm_stock", args) != t2.key("crm_stock", args)


def test_key_is_stable_for_same_identity_and_args():
    args = {"sku": "ABC", "warehouse": "KL"}
    c = _cache()
    assert c.key("crm_stock", args) == c.key("crm_stock", dict(reversed(list(args.items()))))


# --- UAC3b.3 — turn-scoped: a fresh cache starts empty -----------------------
def test_new_turn_cache_starts_empty():
    cache = _cache(turn="turn-A")
    loader_a = _Loader("first-turn")
    cache.get_or_call("crm_stock", {"sku": "ABC"}, loader_a)
    assert loader_a.calls == 1

    # Simulate the next turn: respond() builds a brand-new cache instance.
    next_turn = _cache(turn="turn-B")
    loader_b = _Loader("second-turn")
    val = next_turn.get_or_call("crm_stock", {"sku": "ABC"}, loader_b)
    assert val == "second-turn", "a new turn must re-fetch (no cross-turn staleness)"
    assert loader_b.calls == 1
    assert next_turn.hits == 0


# ===========================================================================
# Agent-loop wiring — live MCP calls are deduplicated through the turn cache
# ===========================================================================


@pytest.fixture
def db_session() -> Session:
    with blank_session() as session:
        yield session


class _CountingMCPClient:
    """Fake MCPRuntimeClient that counts live ``call_tool`` invocations."""

    instances: list["_CountingMCPClient"] = []

    def __init__(self, *_a, **_k):
        self.call_tool_count = 0
        _CountingMCPClient.instances.append(self)

    def list_tools_with_schema(self):
        return {
            "crm_test_tool": {
                "description": "test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            }
        }

    def call_tool(self, tool_name, args):  # noqa: ANN001
        self.call_tool_count += 1
        return '{"result": "ok"}'


class _ScriptedProvider:
    """Returns a scripted sequence of ChatResults across iterations.

    Iteration 1: request the SAME tool twice with identical args.
    Iteration 2: final text answer, no tool calls → loop returns.
    """

    def __init__(self, *_a, **_k):
        self._n = 0

    def chat(self, _messages, tools=None, **_k):  # noqa: ANN001
        self._n += 1
        if self._n == 1 and tools:
            return ChatResult(
                content="",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                tool_calls=[
                    {"id": "c1", "name": "crm_test_tool", "arguments": {"x": "1"}},
                    {"id": "c2", "name": "crm_test_tool", "arguments": {"x": "1"}},
                ],
            )
        return ChatResult(
            content="final answer",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tool_calls=[],
        )


def test_agent_loop_dedups_identical_tool_calls_via_cache(db_session: Session, monkeypatch):
    import app.services.ai_assistant_service as svc_module

    _CountingMCPClient.instances.clear()
    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _CountingMCPClient)
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: _ScriptedProvider())

    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()

    turn_cache = _TurnToolCache(user_id="95709c37-0fb4-5c00-8686-536c019e6fb7", conversation_id="conv-1", turn_id="turn-1")

    text, tool_calls, _usage = svc._run_agent_loop(
        config=cfg,
        history=[],
        user_message="give me the test data please",  # NOT a guide question
        standalone_query="give me the test data please",
        selected_tools=[{"tool_name": "crm_test_tool"}],
        sources=[],
        turn_cache=turn_cache,
    )

    assert text == "final answer"
    # The LLM requested the identical tool+args twice; only ONE live MCP call.
    total_live = sum(c.call_tool_count for c in _CountingMCPClient.instances)
    assert total_live == 1, (
        "two identical tool calls in one turn must hit the cache; only one live "
        f"MCP call expected, got {total_live}"
    )
    assert turn_cache.live_calls == 1
    assert turn_cache.hits == 1
    # Both calls still surface in the tool-call log (cached result reused).
    assert len([c for c in tool_calls if c.tool_name == "crm_test_tool"]) == 2
