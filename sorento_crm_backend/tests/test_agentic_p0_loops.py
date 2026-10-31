"""AGENTIC-P0-PROVIDER: the assistant's tool loops carry the provider's native continuation and the label's effort.

A provider hands back `ChatResult.continuation` (a Gemini thought signature, Claude thinking blocks) on a
tool-calling round; the loop must echo it on the assistant message it appends, or the provider rebuilds the
turn without it. The `agent_system` label's `reasoning_effort` reaches every call of both loops, and an unset
one sends no `reasoning_effort` at all. Providers are stubs; no real LLM call.
"""
from __future__ import annotations

import copy

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session

_NATIVE = {"provider": "gemini", "parts": [{"functionCall": {"name": "x", "args": {}}, "thoughtSignature": "c2ln"}]}


class _GuideMCP:
    def __init__(self, *_a, **_k):
        pass

    def list_tools_with_schema(self):
        return {
            "crm_test_tool": {"description": "t", "inputSchema": {"type": "object", "properties": {}}},
            "user_guides_read": {"description": "g", "inputSchema": {"type": "object", "properties": {}}},
        }

    def call_tool(self, tool_name, args):  # noqa: ANN001
        return '{"result": "ok"}'


class _RecordingProvider:
    """Round 1 calls a tool and returns a native continuation; round 2 answers. Records every call."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.calls: list[dict] = []

    def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001
        self.calls.append({"messages": copy.deepcopy(messages), **kwargs})
        if len(self.calls) == 1:
            return ChatResult(
                content="",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                tool_calls=[{"id": "c1", "name": self.tool, "arguments": {}}],
                continuation=_NATIVE,
            )
        return ChatResult(content="final answer", prompt_tokens=1, completion_tokens=1, total_tokens=2)


@pytest.fixture
def svc(monkeypatch):
    import app.services.ai_assistant_service as svc_module

    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _GuideMCP)
    with blank_session() as db:
        service = AIAssistantChatService(db)
        cfg = service.cfg.get()
        cfg.api_key_ciphertext = "fake-key"
        cfg.provider, cfg.model, cfg.is_enabled = "gemini", "gemini-3.5-flash", True
        db.commit()
        yield svc_module, service, cfg, db


def _label_effort(db, effort: str) -> None:
    version = AIPromptVersion(
        name="agent_system", version=1, template=ai_prompt_registry.PROMPT_KEYS["agent_system"].fallback()
    )
    db.add(version)
    db.flush()
    db.add(AIPromptLabel(name="agent_system", label="production", version_id=version.id, reasoning_effort=effort))
    db.commit()


def _run_agent_loop(service, cfg):
    return service._run_agent_loop(
        config=cfg, history=[], user_message="give me the test data", standalone_query="give me the test data",
        selected_tools=[{"tool_name": "crm_test_tool"}], sources=[], turn_cache=None,
        user_id="95709c37-0fb4-5c00-8686-536c019e6fb7",
    )


def _run_record_answer(service, cfg):
    return service._render_record_answer(
        config=cfg, history=[], user_message="what next?",
        record_ctx={"entity_type": "complaint", "current_state": {"status": "open"}},
        user_id="95709c37-0fb4-5c00-8686-536c019e6fb7",
    )


def _echoed_turn(call: dict) -> dict:
    turns = [m for m in call["messages"] if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(turns) == 1
    return turns[0]


@pytest.mark.parametrize("run", [_run_agent_loop, _run_record_answer], ids=["agent_loop", "record_answer"])
def test_a_tool_loop_echoes_the_native_continuation_into_the_next_round(svc, monkeypatch, run):
    svc_module, service, cfg, _db = svc
    provider = _RecordingProvider("user_guides_read" if run is _run_record_answer else "crm_test_tool")
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    text, _calls, _usage = run(service, cfg)
    assert len(provider.calls) == 2
    assert _echoed_turn(provider.calls[1])["continuation"] == _NATIVE
    assert "final answer" in text


@pytest.mark.parametrize("run", [_run_agent_loop, _run_record_answer], ids=["agent_loop", "record_answer"])
def test_a_tool_loop_sends_the_label_effort_on_every_call(svc, monkeypatch, run):
    svc_module, service, cfg, db = svc
    _label_effort(db, "low")
    provider = _RecordingProvider("user_guides_read" if run is _run_record_answer else "crm_test_tool")
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    run(service, cfg)
    assert [c.get("reasoning_effort") for c in provider.calls] == ["low", "low"]


@pytest.mark.parametrize("run", [_run_agent_loop, _run_record_answer], ids=["agent_loop", "record_answer"])
def test_a_tool_loop_without_a_label_effort_sends_none(svc, monkeypatch, run):
    svc_module, service, cfg, _db = svc
    provider = _RecordingProvider("user_guides_read" if run is _run_record_answer else "crm_test_tool")
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    run(service, cfg)
    assert len(provider.calls) == 2
    assert all("reasoning_effort" not in c for c in provider.calls)
