"""AGENTIC-UNIFY PR 1, the panel side: AC-1, AC-19/AC-20 (panel half), AC-21, AC-24.

UAC: documentation/plans/chatbot/agentic-unify-pr1-acceptance-criteria.md.

The panel is `AIAssistantChatService`. Offline: the LLM provider and the MCP client are scripted,
the database is the blank Postgres schema, permissions and record rows are real.
"""
from __future__ import annotations

import inspect
import json
import re

import httpx
import pytest

from app.schemas.ai_assistant import AIAssistantAuthContext, PageEntityRef, PageSnapshotPayload
from app.services import ai_assistant_service as svc_module
from app.services.ai_assistant_service import (
    AIAssistantChatService,
    MCPRuntimeClient,
    MCPToolCallError,
    _TurnToolCache,
)
from app.services.entity_resolver import ResolutionResult
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.test_ai_assistant_record_context_preroute import _Spy, _USAGE, _parse
from tests.test_staff_read_identity import RECORD_KINDS, _record_row, env, grant, mk_user  # noqa: F401

STAFF_ID = "95709c37-0fb4-5c00-8686-536c019e6fb7"


# --- AC-1 -----------------------------------------------------------------------------------------
def test_ac1_building_staff_without_an_id_raises_value_error():
    with pytest.raises(ValueError):
        MCPRuntimeClient("http://mcp:8765/mcp", staff=True)
    with pytest.raises(ValueError):
        MCPRuntimeClient("http://mcp:8765/mcp", staff=True, staff_user_id="")
    with pytest.raises(ValueError):
        MCPRuntimeClient("http://mcp:8765/mcp", staff=True, staff_user_id=None)


def test_ac1_a_staff_client_with_an_id_sends_both_headers(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": {"tools": []}})

    real = httpx.Client
    monkeypatch.setattr(
        svc_module.httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)})
    )
    monkeypatch.setattr("app.services.mcp_auth_token.current_token", lambda db=None: "x" * 40)
    MCPRuntimeClient("http://mcp:8765/mcp", staff=True, staff_user_id=STAFF_ID).list_tools()
    assert seen[0].headers["x-mcp-scope"] == "staff"
    assert seen[0].headers["x-mcp-staff-user"] == STAFF_ID


def test_ac1_every_panel_client_construction_carries_the_staff_id():
    """Source pin, including `list_mcp_tools` and the `_render_record_answer` client."""
    src = inspect.getsource(svc_module)
    calls = re.findall(r"MCPRuntimeClient\((.*?)\)\n", src, flags=re.S)
    assert len(calls) >= 5
    for args in calls:
        assert "staff=True" in args, args
        assert "staff_user_id=" in args, f"AC-1: a panel client without the staff id: {args.strip()[:120]}"


@pytest.fixture
def db_session():
    with blank_session() as session:
        yield session


class _RecordingMCP:
    instances: list["_RecordingMCP"] = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        _RecordingMCP.instances.append(self)

    def list_tools_with_schema(self):
        return {"crm_test_tool": {"description": "t", "inputSchema": {"type": "object", "properties": {}}}}

    def list_tools(self):
        return ["crm_test_tool"]

    def call_tool(self, name, args):
        self.calls.append((name, args))
        return '{"ok": true}'


class _Provider:
    def __init__(self, *_a, **_k):
        self.messages_seen: list[list[dict]] = []
        self._n = 0

    def chat(self, messages, tools=None, **_k):
        self.messages_seen.append([dict(m) for m in messages])
        self._n += 1
        if self._n == 1 and tools:
            return ChatResult(
                content="", prompt_tokens=1, completion_tokens=1, total_tokens=2,
                tool_calls=[{"id": "c1", "name": "crm_test_tool", "arguments": {}}],
            )
        return ChatResult(content="final answer", prompt_tokens=1, completion_tokens=1, total_tokens=2, tool_calls=[])


def _loop_service(db_session, monkeypatch, mcp_cls, provider):
    monkeypatch.setattr(svc_module, "MCPRuntimeClient", mcp_cls)
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)
    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()
    return svc, cfg


def _run_loop(svc, cfg, user_id=STAFF_ID):
    return svc._run_agent_loop(
        config=cfg, history=[], user_message="what is in stock", standalone_query="what is in stock",
        selected_tools=[{"tool_name": "crm_test_tool"}], sources=[], user_id=user_id,
        turn_cache=_TurnToolCache(user_id=user_id, conversation_id="c1", turn_id="t1"),
    )


def test_ac1_the_agent_loop_builds_its_client_as_the_staff_member(db_session, monkeypatch):
    _RecordingMCP.instances.clear()
    svc, cfg = _loop_service(db_session, monkeypatch, _RecordingMCP, _Provider())
    _run_loop(svc, cfg)
    assert _RecordingMCP.instances
    for inst in _RecordingMCP.instances:
        assert inst.kwargs.get("staff") is True
        assert inst.kwargs.get("staff_user_id") == STAFF_ID, "AC-1: the real staff id, every client"


# --- AC-21 ----------------------------------------------------------------------------------------
class _RefusingMCP(_RecordingMCP):
    """A CRM 403 as the MCP server delivers it: ordinary tool text, `isError` false, shaped by
    `http_error_body` (sorento_crm_mcp/http_client.py), with an `error` key stamped on it."""

    BODY = {
        "detail": {"code": "permission_denied", "message": "Permission required: inventory.stock.view"},
        "error": "GET /api/v1/inventory/stock/balance returned HTTP 403: permission_denied",
        "http_error": "GET /api/v1/inventory/stock/balance returned HTTP 403: permission_denied",
        "status_code": 403,
        "path": "/api/v1/inventory/stock/balance",
        "method": "GET",
    }

    def call_tool(self, name, args):
        self.calls.append((name, args))
        return json.dumps(self.BODY)


def test_ac21_a_403_from_a_tool_still_answers_and_the_model_sees_a_failed_result(db_session, monkeypatch):
    """Regression (passes today): a refused tool is a failed tool result, never a 500. Blinding
    `_tool_output_is_error` (which reads the `error` key) turns the `ok` assertion red."""
    provider = _Provider()
    svc, cfg = _loop_service(db_session, monkeypatch, _RefusingMCP, provider)
    text, tool_calls, _usage = _run_loop(svc, cfg)
    assert text == "final answer"
    assert [c.ok for c in tool_calls if c.tool_name == "crm_test_tool"] == [False]
    tool_msgs = [m for m in provider.messages_seen[1] if m.get("role") == "tool"]
    assert tool_msgs, "the model must receive the refusal as a tool result"
    assert '"status_code": 403' in tool_msgs[-1]["content"]


# --- AC-26 ----------------------------------------------------------------------------------------
@pytest.fixture
def no_http(monkeypatch):
    """No token configured; any HTTP call the panel client makes is recorded."""
    seen: list[httpx.Request] = []
    monkeypatch.setattr("app.services.mcp_auth_token.current_token", lambda db=None: None)

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": {"tools": [], "content": []}})

    real = httpx.Client
    monkeypatch.setattr(
        svc_module.httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)})
    )
    return seen


def test_ac26_a_staff_client_with_no_token_makes_no_call_and_raises_the_tool_error(no_http):
    client = MCPRuntimeClient("http://mcp:8765/mcp", staff=True, staff_user_id=STAFF_ID)
    with pytest.raises(MCPToolCallError):
        client.call_tool("crm_x", {})
    with pytest.raises(MCPToolCallError):
        client.list_tools()
    assert no_http == [], "AC-26: nothing may go out without the bearer"


def test_ac26_a_non_staff_client_with_no_token_is_unchanged(no_http):
    MCPRuntimeClient("http://mcp:8765/mcp").call_tool("crm_x", {})
    assert no_http, "the chatbot lanes keep working with Enforce off"


def test_ac26_a_panel_turn_with_no_token_still_answers(db_session, monkeypatch, no_http):
    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: _Provider())
    text, tool_calls, _usage = _run_loop(svc, cfg)
    assert isinstance(text, str) and text.strip(), "the turn still answers"
    assert no_http == []
    assert tool_calls and all(not c.ok for c in tool_calls)


# --- AC-24 ----------------------------------------------------------------------------------------
def test_ac24_write_permissions_are_pinned():
    """Regression (passes today): the panel's own gate on confirmed writes."""
    perms = AIAssistantChatService._WRITE_TOOL_PERMISSIONS
    assert perms["crm_complaint_close"] == "complaint_management.complaints.close"
    assert perms["crm_purchase_request_approve"] == "procurement.purchase_requests.approve"
    assert perms["crm_purchase_request_reject"] == "procurement.purchase_requests.approve"
    assert perms["crm_ideation_turn"] == "ideation.board.view"
    assert perms["crm_sales_opportunity_log"] == "sales.opportunities.add"
    assert "crm_order_cancel" not in perms, "the UI cancel path is auth-only; chat must not be stricter"


# --- AC-19 / AC-20, panel half -----------------------------------------------------------------------
@pytest.fixture
def panel(db_session, monkeypatch):
    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()
    svc.gov.build_auth_context = lambda user_id: AIAssistantAuthContext(
        user_id=user_id, role_ids=["r1"], permission_slugs=["system.ai_assistant_chat.use"], enabled_modules=[]
    )
    svc._parse_turn = lambda **_k: _parse("unknown")
    svc._rag_select_tools = lambda *, standalone_query, enabled_tools, top_k: ([], [])
    svc._generate_suggestions = lambda **_k: []
    monkeypatch.setattr(
        svc_module, "resolve_references", lambda *_a, **_k: ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0)
    )
    # real UserPermissionService and real RecordContextService: only the model calls are stubbed
    svc._agent = _Spy(("agent answer", [], _USAGE))
    svc._render = _Spy(("rendered answer", [], _USAGE))
    svc._run_agent_loop = svc._agent
    svc._render_record_answer = svc._render
    return svc


def _facts_given(panel):
    """The record facts the turn handed to the model, from whichever route ran."""
    for spy in (panel._render, panel._agent):
        if spy.called:
            return spy.kwargs.get("record_ctx"), spy
    pytest.fail("the turn answered through neither route")


def _ask(panel, user_id, kind, row_id):
    panel._parse_turn = lambda **_k: _parse("record_question", targets_open_record=True)
    answer = panel.respond(
        user_id=user_id, conversation_id=None, message="Why was this one rejected?",
        page_snapshot=PageSnapshotPayload(
            path="/x", search="", title="Record", visible_text="detail",
            entity=PageEntityRef(entity_type=kind, id=row_id),
        ),
    )
    return answer


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac19_panel_gives_no_facts_without_a_view_permission_but_still_answers(db_session, panel, kind):
    row_id = _record_row(db_session, kind)
    user = mk_user(db_session, "nobody")
    answer = _ask(panel, user, kind, row_id)
    assert answer is not None, "no permission, no facts, the turn still answers"
    facts, _spy = _facts_given(panel)
    assert facts is None, f"AC-19 {kind}: a user holding nothing was handed the record facts"


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac19_panel_gives_facts_to_a_view_holder(db_session, panel, kind):
    row_id = _record_row(db_session, kind)
    user = mk_user(db_session, "viewer", perms=RECORD_KINDS[kind][:1])
    _ask(panel, user, kind, row_id)
    facts, spy = _facts_given(panel)
    assert facts is not None, f"AC-19 {kind}: a view holder must get the facts"
    assert spy is panel._render, "a record question takes the record route"
    assert spy.kwargs.get("user_id") == user, (
        "AC-1: the record route must hand the staff id to _render_record_answer, which builds "
        "its MCP client from it"
    )


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac20_panel_view_own_gets_facts_only_for_their_own_record(db_session, panel, kind):
    from tests._own_scope_support import contact

    ca, cb = contact(db_session, "CA"), contact(db_session, "CB")
    mine = _record_row(db_session, kind, contact_id=ca.id)
    theirs = _record_row(db_session, kind, contact_id=cb.id)
    user = mk_user(db_session, "view-own", contact_id=ca.id)
    grant(db_session, user, RECORD_KINDS[kind][1:])

    _ask(panel, user, kind, mine)
    own_facts, _ = _facts_given(panel)
    assert own_facts is not None, f"AC-20 {kind}: own record must give facts"

    panel._agent.called = panel._render.called = False
    _ask(panel, user, kind, theirs)
    foreign_facts, _ = _facts_given(panel)
    assert foreign_facts is None, f"AC-20 {kind}: the client-supplied id named someone else's record"


# --- the settings page's tool list with no MCP token --------------------------------------------------
def test_ac26_the_settings_tool_list_with_no_token_is_503_with_a_detail(env, monkeypatch):
    monkeypatch.setattr("app.services.mcp_auth_token.current_token", lambda db=None: None)
    viewer = mk_user(env.db, "settings-viewer", perms=["system.ai_assistant_settings.view"])
    resp = env.client.get("/api/v1/system/ai-assistant/tools", headers=env.session(viewer))
    assert resp.status_code == 503, f"{resp.status_code} {resp.text[:200]}"
    assert resp.json().get("detail"), "the page shows this where the tool list would be"
