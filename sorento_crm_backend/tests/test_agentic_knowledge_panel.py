"""AGENTIC-KNOWLEDGE P1, the in-app side panel (UAC AC-K16).

The panel's MCP calls reach the backend as the integration's act-as user and
`X-MCP-Staff-User` is log-only, so an MCP tool cannot tell which staff member asks. The
panel therefore answers `crm_knowledge_search` IN PROCESS with `client.staff_user_id` and
never calls `client.call_tool` for it.
"""
from __future__ import annotations

import json

import pytest

from tests._knowledge_seed import (
    query_embed,
    seed_attachment,
    seed_chunk,
    seed_reader,
    seed_type,
    vec_with_similarity,
)
from tests._pg_fixture import blank_session

TOOL = "crm_knowledge_search"
RESULT = {
    "status": "ok",
    "passages": [{"document": "Employee Handbook 2026", "page": 14, "heading": "Leave", "text": "14 days", "similarity": 0.9}],
    "handoff_teams": ["HR"],
}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


class FakeClient:
    """Stands in for MCPRuntimeClient: it knows the staff user, and fails if the MCP is used."""

    def __init__(self, staff_user_id, other_output="mcp-output"):
        self.staff_user_id = staff_user_id
        self.other_output = other_output
        self.mcp_calls: list[tuple[str, dict]] = []

    def call_tool(self, name, args=None):
        self.mcp_calls.append((name, dict(args or {})))
        return self.other_output


def _service(db):
    from app.services.ai_assistant_service import AIAssistantChatService

    return AIAssistantChatService(db)


# ---------------------------------------------------------------- knowledge_tool_output


def test_knowledge_tool_output_is_the_json_of_the_search_for_that_user(db, monkeypatch):
    from app.services import ai_assistant_service, knowledge_service

    seen: list[dict] = []

    def spy(db_, *, user_id, query, top_k=5, embed=None):
        seen.append({"user_id": user_id, "query": query})
        return dict(RESULT)

    monkeypatch.setattr(knowledge_service, "search", spy)

    out = ai_assistant_service.knowledge_tool_output(db, "user-7", {"query": "annual leave after 3 years"})

    assert isinstance(out, str)
    assert json.loads(out) == RESULT
    assert seen == [{"user_id": "user-7", "query": "annual leave after 3 years"}]


def test_knowledge_tool_output_over_real_rows_returns_a_passage_and_refuses_a_stranger(db, monkeypatch):
    """No spy on the search itself: only the query embedding is replaced."""
    from app.services import ai_assistant_service, knowledge_service

    reader = seed_reader(db)
    stranger = seed_reader(db, slugs=("inventory.stock.view",))
    att = seed_attachment(db, seed_type(db, audience="staff"))
    seed_chunk(db, att, vec_with_similarity(1.0), text="Annual leave is 14 days after three years.")
    real_search = knowledge_service.search
    monkeypatch.setattr(
        knowledge_service, "search", lambda db_, **kw: real_search(db_, **{**kw, "embed": query_embed})
    )

    ok = json.loads(ai_assistant_service.knowledge_tool_output(db, reader, {"query": "annual leave"}))
    denied = json.loads(ai_assistant_service.knowledge_tool_output(db, stranger, {"query": "annual leave"}))

    assert ok["status"] == "ok"
    assert [p["text"] for p in ok["passages"]] == ["Annual leave is 14 days after three years."]
    assert denied["status"] == "denied"
    assert denied["passages"] == []


# ---------------------------------------------------------------- _cached_tool_call


def test_the_panel_answers_knowledge_in_process_with_the_staff_user_and_skips_the_mcp(db, monkeypatch):
    from app.services import ai_assistant_service

    calls: list[tuple] = []

    def fake_output(db_, user_id, args):
        calls.append((db_, user_id, dict(args)))
        return json.dumps(RESULT)

    monkeypatch.setattr(ai_assistant_service, "knowledge_tool_output", fake_output)
    service = _service(db)
    client = FakeClient("staff-42")

    out = service._cached_tool_call(None, client, TOOL, {"query": "annual leave"})

    assert json.loads(out) == RESULT
    assert calls == [(service.db, "staff-42", {"query": "annual leave"})]
    assert client.mcp_calls == [], "the MCP cannot see the user, so it must not be used for this tool"


def test_the_same_holds_inside_a_turn_cache(db, monkeypatch):
    from app.services import ai_assistant_service
    from app.services.ai_assistant_service import _TurnToolCache

    users: list[str] = []

    def fake_output(db_, user_id, args):
        users.append(user_id)
        return json.dumps(RESULT)

    monkeypatch.setattr(ai_assistant_service, "knowledge_tool_output", fake_output)
    service = _service(db)
    client = FakeClient("staff-42")
    cache = _TurnToolCache(user_id="staff-42", conversation_id="c1", turn_id="t1")

    out = service._cached_tool_call(cache, client, TOOL, {"query": "annual leave"})

    assert json.loads(out) == RESULT
    assert users == ["staff-42"]
    assert client.mcp_calls == []


def test_other_tools_still_go_through_the_mcp(db, monkeypatch):
    from app.services import ai_assistant_service

    monkeypatch.setattr(
        ai_assistant_service,
        "knowledge_tool_output",
        lambda *a, **k: pytest.fail("knowledge_tool_output is only for crm_knowledge_search"),
    )
    service = _service(db)
    client = FakeClient("staff-42", other_output="guide steps")

    out = service._cached_tool_call(None, client, "user_guides_read", {"query": "create an order"})

    assert out == "guide steps"
    assert client.mcp_calls == [("user_guides_read", {"query": "create an order"})]


# ================================================================ FIX ROUND 1: RS7, what the panel binds and tells the model


class _GuideMcp:
    def __init__(self, *_a, staff_user_id=None, **_k):
        self.staff_user_id = staff_user_id

    def list_tools_with_schema(self):
        return {"user_guides_read": {"description": "g", "inputSchema": {"type": "object", "properties": {}}}}

    def call_tool(self, tool_name, args=None):  # noqa: ANN001
        return '{"result": "ok"}'


class _RecordingProvider:
    def __init__(self):
        self.tools: list[str] = []
        self.system: str = ""

    def chat(self, messages, tools=None, **_k):  # noqa: ANN001
        self.tools = [t["function"]["name"] for t in (tools or [])]
        self.system = "\n".join(str(m.get("content")) for m in messages if m.get("role") == "system")
        from app.services.llm_provider import ChatResult

        return ChatResult(content="final", prompt_tokens=1, completion_tokens=1, total_tokens=2, tool_calls=[])


def _bound(db, monkeypatch, user_id):
    import app.services.ai_assistant_service as svc_module

    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _GuideMcp)
    provider = _RecordingProvider()
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    service = _service(db)
    cfg = service.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider, cfg.model, cfg.is_enabled = "openai", "gpt-4o-mini", True
    db.commit()
    service._run_agent_loop(
        config=cfg, history=[], user_message="what is in the handbook?", standalone_query="handbook",
        selected_tools=[], sources=[], user_id=user_id, turn_cache=None,
    )
    return provider


def test_the_panel_binds_the_knowledge_tool_for_a_user_who_may_open_the_files(db, monkeypatch):
    provider = _bound(db, monkeypatch, seed_reader(db))

    assert TOOL in provider.tools
    assert "user_guides_read" in provider.tools
    assert "KNOWLEDGE PROTOCOL" in provider.system
    assert "USER GUIDE PROTOCOL" in provider.system


def test_the_panel_does_not_bind_the_knowledge_tool_or_its_protocol_without_the_slug(db, monkeypatch):
    provider = _bound(db, monkeypatch, seed_reader(db, slugs=("inventory.stock.view",)))

    assert TOOL not in provider.tools
    assert "user_guides_read" in provider.tools
    assert "KNOWLEDGE PROTOCOL" not in provider.system, "the protocol is added only where the tool is bound"


# ================================================================ FIX ROUND 2: B-new-2, the panel's stored trace

PASSAGE_TEXT = "ZZT SECRET PASSAGE: annual leave is 14 days after three years of service."
HIT_WITH_TEXT = {
    "status": "ok",
    "passages": [{"document": "Employee Handbook 2026", "page": 14, "heading": "Leave", "text": PASSAGE_TEXT, "similarity": 0.91}],
    "handoff_teams": ["HR"],
}


class _KnowledgeTurnProvider:
    """Round 1 asks for the knowledge search, round 2 answers."""

    def __init__(self):
        self.n = 0

    def chat(self, messages, tools=None, **_k):  # noqa: ANN001
        from app.services.llm_provider import ChatResult

        self.n += 1
        if self.n == 1:
            return ChatResult(
                content="", prompt_tokens=1, completion_tokens=1, total_tokens=2,
                tool_calls=[{"id": "k1", "name": TOOL, "arguments": {"query": "annual leave"}}],
            )
        return ChatResult(content="Fourteen days (Employee Handbook 2026, p.14).", prompt_tokens=1, completion_tokens=1, total_tokens=2, tool_calls=[])


def _run_knowledge_turn(db, monkeypatch):
    import copy

    import app.services.ai_assistant_service as svc_module
    from app.services import knowledge_service
    from app.services.ai_trace import TurnTrace

    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _GuideMcp)
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: _KnowledgeTurnProvider())
    monkeypatch.setattr(knowledge_service, "search", lambda db_, **kw: copy.deepcopy(HIT_WITH_TEXT))
    user_id = seed_reader(db)
    service = _service(db)
    cfg = service.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider, cfg.model, cfg.is_enabled = "openai", "gpt-4o-mini", True
    db.commit()
    service._turn_trace = TurnTrace(user_id=user_id, conversation_id=None, session_id=None)
    service._run_agent_loop(
        config=cfg, history=[], user_message="annual leave?", standalone_query="annual leave",
        selected_tools=[], sources=[], user_id=user_id, turn_cache=None,
    )
    return service._turn_trace


def test_the_panel_trace_span_for_a_knowledge_search_keeps_document_and_page_but_not_the_text(db, monkeypatch):
    """Seam: the buffered `TurnTrace._spans` tool span (what `_finalize_trace` flushes to AIAssistantSpan)."""
    trace = _run_knowledge_turn(db, monkeypatch)

    spans = [s for s in trace._spans if s.tool_name == TOOL]
    assert len(spans) == 1
    for field in (spans[0].tool_result, spans[0].output_json, spans[0].input_json, spans[0].tool_args):
        assert PASSAGE_TEXT not in json.dumps(field, default=str)
    stored = json.dumps([spans[0].tool_result, spans[0].output_json], default=str)
    assert "Employee Handbook 2026" in stored
    assert "14" in stored


def test_the_flushed_span_rows_carry_no_passage_text(db, monkeypatch):
    from app.models.ai_assistant import AIAssistantSpan

    trace = _run_knowledge_turn(db, monkeypatch)
    trace_id = trace.flush(db, message_id=None)

    if trace_id is None:
        pytest.skip("the trace cannot be flushed without an assistant message; the in-memory test covers it")
    rows = db.query(AIAssistantSpan).filter(AIAssistantSpan.trace_id == trace_id, AIAssistantSpan.tool_name == TOOL).all()
    assert rows
    for row in rows:
        assert PASSAGE_TEXT not in json.dumps([row.tool_result, row.output_json, row.input_json], default=str)


def test_the_panel_strips_through_tools_trace_safe(db, monkeypatch):
    from app.services.chatbot.agent import tools

    calls: list[str] = []
    real = tools.trace_safe

    def recorder(name, data):
        calls.append(name)
        return real(name, data)

    monkeypatch.setattr(tools, "trace_safe", recorder)

    _run_knowledge_turn(db, monkeypatch)

    assert TOOL in calls


# ================================================================ FIX ROUND 3: the LLM spans carry the tool messages too


class _CapturingProvider(_KnowledgeTurnProvider):
    """Like the two-round provider, and it keeps a copy of what it was sent on each round."""

    def __init__(self):
        super().__init__()
        self.sent: list[list[dict]] = []

    def chat(self, messages, tools=None, **kw):  # noqa: ANN001
        import copy

        self.sent.append(copy.deepcopy(list(messages)))
        return super().chat(messages, tools=tools, **kw)


def test_no_buffered_span_of_a_knowledge_turn_carries_the_passage_text_but_the_model_still_reads_it(db, monkeypatch):
    import copy

    import app.services.ai_assistant_service as svc_module
    from app.services import knowledge_service
    from app.services.ai_trace import TurnTrace

    provider = _CapturingProvider()
    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _GuideMcp)
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    monkeypatch.setattr(knowledge_service, "search", lambda db_, **kw: copy.deepcopy(HIT_WITH_TEXT))
    user_id = seed_reader(db)
    service = _service(db)
    cfg = service.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider, cfg.model, cfg.is_enabled = "openai", "gpt-4o-mini", True
    db.commit()
    service._turn_trace = TurnTrace(user_id=user_id, conversation_id=None, session_id=None)

    service._run_agent_loop(
        config=cfg, history=[], user_message="annual leave?", standalone_query="annual leave",
        selected_tools=[], sources=[], user_id=user_id, turn_cache=None,
    )

    assert len(provider.sent) >= 2
    round_two = json.dumps(provider.sent[1], default=str)
    assert PASSAGE_TEXT in round_two, "the model itself must still read the passage"
    spans = service._turn_trace._spans
    assert any(s.span_kind == "LLM" for s in spans) and any(s.tool_name == TOOL for s in spans)
    for span in spans:
        stored = json.dumps([span.input_json, span.output_json, span.tool_args, span.tool_result], default=str)
        assert PASSAGE_TEXT not in stored, f"span {span.name} stores the passage text"
    llm_inputs = json.dumps([s.input_json for s in spans if s.span_kind == "LLM"], default=str)
    assert "Employee Handbook 2026" in llm_inputs, "document and page stay in the trace"
