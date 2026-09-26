"""Phase 2 RED tests - issue #1262 (Samantha case), slice 1, finding F2.

Turns T7/T8/T9: the MCP server answers `crm_outstanding_report` with `isError: true`
and a text block ("Error executing tool crm_outstanding_report: {\"code\":
\"INVALID_UUID\", ...}"). Nobody reads `isError`, so the raw tool-error text is
printed to WhatsApp verbatim.

AC-S1-1: `MCPRuntimeClient.call_tool` raises on `isError`, and the fetch step's error
arm engages (never the raw text as a reply).
AC-S1-2: `_outstanding_report_output` never treats a bare (non-envelope) string as a
result - `has_result` is False.
AC-S1-3: any lane text containing "Error executing tool" is replaced by the neutral
fetch-failure line when the turn composes its reply.
AC-S1-4: the in-app AI assistant's own tool loop keeps seeing the error text (it must
not silently swallow it) - pinned so the coder's S1 change to `call_tool` does not
regress it.

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 1. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session

TOOL_ERROR_TEXT = 'Error executing tool crm_outstanding_report: {"code": "INVALID_UUID", "message": "not a uuid"}'

# Captured at COLLECTION time, before `tests/chatbot/conftest.py`'s autouse
# `_no_real_mcp_calls` fixture replaces `MCPRuntimeClient.call_tool` with a guard that
# raises `AssertionError` for anything not itself stubbed. This IS the method under
# test, so the test below restores this original onto the class (its own
# `monkeypatch.setattr`, applied AFTER the autouse fixture's, per that fixture's own
# docstring) rather than asserting against the guard's unrelated raise.
_ORIGINAL_CALL_TOOL = MCPRuntimeClient.call_tool


@pytest.fixture
def db_session() -> Session:
    with blank_session() as session:
        yield session


def test_mcp_is_error_takes_the_error_arm(monkeypatch):
    """AC-S1-1. Two halves, same behaviour: (a) `MCPRuntimeClient.call_tool` must raise
    when the JSON-RPC result carries `isError: true` (red today - it just joins the
    text and returns it), and (b) once it does raise, `run_fetch`'s own error handling
    already exists and takes the error arm rather than leaking the raw text into the
    fetch item's `response` (this half is a guard: it is already correct plumbing,
    kept here so a coder fixing (a) does not accidentally break it too).

    Restores the real `call_tool` onto the class first - `tests/chatbot/conftest.py`'s
    autouse `_no_real_mcp_calls` fixture replaced it with a guard that raises for an
    unrelated reason (no real MCP calls from this test tree), which would make this
    test pass without ever exercising the `isError` check.
    """
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", _ORIGINAL_CALL_TOOL)

    client = MCPRuntimeClient("http://mcp.example", timeout_seconds=5)
    client._rpc = lambda method, params=None: {  # type: ignore[method-assign]
        "content": [{"type": "text", "text": TOOL_ERROR_TEXT}],
        "isError": True,
    }

    with pytest.raises(Exception):
        client.call_tool("crm_outstanding_report", {"customer_ids": ["not-a-uuid"]})

    # (b) guard: once call_tool raises, run_fetch's existing except-handler already
    # takes the error arm and never carries the raw text into a `response` key.
    from app.services.chatbot.lanes import business
    from app.services.chatbot.lanes.business.services import FetchServices

    def raising_mcp_call(name, args):
        raise RuntimeError(TOOL_ERROR_TEXT)

    payload = {
        "_exit_kind": "continue",
        "gate": {
            "compatible_entities": [
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}
            ]
        },
        "ctx": {"parse": {"output": {"domain_hint": "master_products"}}},
    }
    fragment = business.run_fetch(payload, services=FetchServices(mcp_call=raising_mcp_call), dry_run=False)

    assert fragment.get("kind") == "error" or fragment.get("_fetch_arm") == "error"
    fetch_item = fragment.get("fetch") or {}
    assert "response" not in fetch_item, (
        f"the error arm must never carry a `response` a composer could print verbatim: {fetch_item!r}"
    )


def test_t8_outstanding_photo_reply_has_no_tool_error_text():
    """AC-S1-2. T8's photo (and T7/T9's) ran the outstanding report as a "narrowing"
    refinement; the MCP client (pre-fix) returned the bare error string rather than the
    `{response, has_result}` envelope, and `_outstanding_report_output`'s own fallback
    branch treats any non-empty string as an answered result. Red: `has_result` comes
    back True for a bare tool-error string.
    """
    from app.services.chatbot.lanes.business.fetch import _outstanding_report_output

    out = _outstanding_report_output(TOOL_ERROR_TEXT, {"entities": [], "semantic_input": {}})

    assert out["has_result"] is False, (
        f"a bare non-envelope string must never be treated as a result: {out!r}"
    )


def test_t7_incoming_photo_reply_has_no_tool_error_text():
    """AC-S1-3 (T7's own turn). Compose must never print "Error executing tool" text
    verbatim, whatever carried it - here the incoming domain's own envelope leaks the
    outstanding hijack's tool-error text onto `lane_text` (T7's actual failure, per the
    explainer section 1). Red: `compose()`'s `lane_text` branch (turn/compose.py) prints
    the envelope's `lane_text` unconditionally, ahead of any error check.
    """
    from app.services.chatbot.turn.compose import compose
    from app.services.chatbot.turn.policy import Policy
    from app.services.chatbot.turn.state import Focus, Profile, State

    from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row

    policy = Policy.from_rows(
        domains=[_domain_row("incoming", narrowing={"product": "narrow_to_code"})],
        kinds=[],
        tier_order=TIER_ORDER_FIXTURE,
    )
    envelope = {
        "domain": "incoming",
        "denied": False,
        "entities": ["M210-GM"],
        "figures": [],
        "files": [],
        "miss": [],
        "has_result": False,
        "lane_text": TOOL_ERROR_TEXT,
    }
    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=7)

    answer = compose([envelope], state, policy, ctx=None)

    assert "Error executing tool" not in answer.text, answer.text


def test_t9_unresolved_code_reply_has_no_tool_error_text():
    """AC-S1-3 (T9's own turn). Same compose-level guard as T7's test, for the turn the
    explainer names separately (T9, "X4: M488-75-PVD-GM" hijacked the same way) - kept
    as its own test because it traces to its own AC/turn pairing in the captain's list,
    not because the code path differs.
    """
    from app.services.chatbot.turn.compose import compose
    from app.services.chatbot.turn.policy import Policy
    from app.services.chatbot.turn.state import Focus, Profile, State

    from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row

    policy = Policy.from_rows(
        domains=[_domain_row("order", narrowing={"customer": "must_narrow_one"})],
        kinds=[],
        tier_order=TIER_ORDER_FIXTURE,
    )
    envelope = {
        "domain": "order",
        "denied": False,
        "entities": ["M488-75-PVD-GM"],
        "figures": [],
        "files": [],
        "miss": [],
        "has_result": False,
        "lane_text": TOOL_ERROR_TEXT,
    }
    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=9)

    answer = compose([envelope], state, policy, ctx=None)

    assert "Error executing tool" not in answer.text, answer.text


def test_ai_assistant_tool_loop_still_sees_the_error_text_after_a_raise(db_session, monkeypatch):
    """AC-S1-4 (pinning, not a red test): the in-app AI assistant's own read-tool loop
    already wraps `client.call_tool(...)` in `try/except Exception` and feeds the
    exception's own text back to the model as the tool result - so once S1 makes
    `call_tool` raise on `isError`, this loop keeps seeing the error text exactly as it
    does today for a network failure. Modelled on
    `tests/test_ai_assistant_turn_cache.py::test_agent_loop_dedups_identical_tool_calls_via_cache`.
    """
    import app.services.ai_assistant_service as svc_module
    from app.services.ai_assistant_service import AIAssistantChatService

    class _RaisingMCPClient:
        def __init__(self, *_a, **_k):
            pass

        def list_tools_with_schema(self):
            return {
                "crm_outstanding_report": {
                    "description": "outstanding report",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            }

        def call_tool(self, tool_name, args):  # noqa: ANN001
            raise RuntimeError(TOOL_ERROR_TEXT)

    class _ScriptedProviderCapturingMessages:
        def __init__(self, *_a, **_k):
            self._n = 0
            self.final_messages: list | None = None

        def chat(self, messages, tools=None, **_k):  # noqa: ANN001
            self._n += 1
            if self._n == 1 and tools:
                return ChatResult(
                    content="",
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    tool_calls=[{"id": "c1", "name": "crm_outstanding_report", "arguments": {}}],
                )
            self.final_messages = messages
            return ChatResult(
                content="final answer",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                tool_calls=[],
            )

    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _RaisingMCPClient)
    provider = _ScriptedProviderCapturingMessages()
    monkeypatch.setattr(svc_module, "get_provider", lambda *_a, **_k: provider)

    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()

    text, _tool_calls, _usage = svc._run_agent_loop(
        config=cfg,
        history=[],
        user_message="what is outstanding for Cheng Huat Sentul",
        standalone_query="what is outstanding for Cheng Huat Sentul",
        selected_tools=[{"tool_name": "crm_outstanding_report"}],
        sources=[],
        turn_cache=None,
    )

    assert text == "final answer"
    assert provider.final_messages is not None, "the loop never reached its second LLM call"
    tool_messages = [m for m in provider.final_messages if m.get("role") == "tool"]
    assert tool_messages, "no tool-result message was fed back to the model"
    assert any("tool_call_failed" in m["content"] for m in tool_messages), (
        "expected the caught exception's own text to reach the model, got: "
        f"{[m['content'] for m in tool_messages]!r}"
    )


# --------------------------------------------------------------------------- #
# Phase 3 fix-round findings (26 Sep, reviewer pass on the coder's S1 change)
# --------------------------------------------------------------------------- #


def test_bare_string_outstanding_result_never_rides_on_response():
    """AC-S1-2's own fix (landed) cleared `has_result` for a bare, non-envelope
    string, but `_outstanding_report_output` (fetch.py) still puts the SAME bare
    string onto `response` unconditionally (`text = result if isinstance(result,
    str) else ...`, then `"response": text` with no gate at all). `turn/compose.py`
    only strips a lane_text containing the literal substring "Error executing tool"
    (AC-S1-3's own narrow fix) - any OTHER bare/unrendered string still rides through
    to `lane_text` and prints verbatim, because compose has no way to know it was
    never a real rendered report.

    Red: `out.get("response")` is still the garbage string, not empty/None; and the
    composed miss-branch reply still contains it.
    """
    from app.services.chatbot.lanes.business.fetch import _outstanding_report_output
    from app.services.chatbot.turn.compose import compose
    from app.services.chatbot.turn.policy import Policy
    from app.services.chatbot.turn.state import Focus, Profile, State

    from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row

    garbage = "some unrendered probe payload, not a phrase any downstream guard names by string"
    out = _outstanding_report_output(garbage, {"entities": [], "semantic_input": {}})

    assert out["has_result"] is False
    assert not out.get("response"), (
        f"a bare, non-envelope string must never ride on `response`: {out!r}"
    )

    # The miss-branch reply must not contain it either, whatever carried it.
    policy = Policy.from_rows(
        domains=[_domain_row("order", narrowing={"customer": "must_narrow_one"})],
        kinds=[], tier_order=TIER_ORDER_FIXTURE,
    )
    envelope = {
        "domain": "order", "denied": False, "entities": [], "figures": [], "files": [],
        "miss": [], "has_result": out["has_result"], "lane_text": out.get("response"),
    }
    state = State(focus=Focus(), pending=None, profile=Profile())
    answer = compose([envelope], state, policy, ctx=None)

    assert garbage not in answer.text, answer.text


def test_miss_suggest_probe_tool_error_does_not_fail_the_turn():
    """The DYM probe (miss_suggest.py ~1425) already degrades a tool-call failure to
    a bare did-you-mean offer (`except Exception: probe = {"error": "probe failed"}`)
    - now that `call_tool` genuinely raises `MCPToolCallError` (S1), the SIBLING
    probe (~1385, the incoming-domain "no product with this exact code, here is its
    family" path) has no such guard at all: `services.mcp_probe(...)` is called
    UNWRAPPED, by design per the module's own docstring ("sibling-probe ... carries
    no onError, which is why their calls above are deliberately unwrapped") - a
    faithful n8n port, but a probe failure now genuinely raises and must not take
    the whole turn down with it.

    Red: `run_miss_lane` raises `MCPToolCallError` straight out, instead of
    degrading the way the dym probe already does.
    """
    from app.services.ai_assistant_service import MCPToolCallError
    from app.services.chatbot.lanes.business import miss_suggest as miss_mod
    from app.services.chatbot.lanes.business.services import AnswerServices

    product_code = "SRTWC6022"

    parser = {
        "domain_hint": "incoming",
        "intent_hint": "check_incoming",
        "message_type": "business_query",
        "entities": [{"raw": product_code, "hint": "product", "current_message": True, "confident": True}],
        "routing": {"suggested_team": None, "suggested_agent": None},
        "access_levels": [],
    }
    resolved = {
        "resolutions": [], "unresolved_tokens": [product_code], "tokens": [product_code], "intersection": [],
    }
    gate = {
        "gate_debug": {"domain": "incoming"},
        "require_specific": False,
        "compatible_entities": [{"entity_type": "product", "code": product_code}],
    }
    build_result = {"has_result": False}

    def _raising_probe(name, args):
        raise MCPToolCallError("Error executing tool crm_incoming_stock_list: probe failed")

    services = AnswerServices(mcp_probe=_raising_probe, family_fetch=lambda query: {"data": []})

    not_found = {"result_type": "incoming", "items": [], "has_result": False}

    # No pytest.raises here on purpose: the assertion IS that this does not raise.
    offer = miss_mod.run_miss_lane(
        not_found,
        parser=parser,
        resolved=resolved,
        gate=gate,
        services=services,
        build_result=build_result,
        contact_id="zzt-s1-probe-fail",
        space_id=None,
        execution_id="zzt-s1-turn",
        dry_run=True,
    )
    assert isinstance(offer, dict)


def test_promo_dym_probe_tool_error_does_not_fail_the_turn(monkeypatch):
    """The PROMO did-you-mean probe (`miss_suggest.run_miss_lane` ~1416, `if-promo-
    dym` TRUE, `mode: each` - one `services.mcp_probe` call per candidate,
    `promo_dym_plan`'s own row) already has a `try/except` in the checked-out code
    (review round, SF2), but the reviewer found REMOVING that try/except still left
    every existing test green - nothing exercises this branch with a probe that
    actually raises, so a regression here would go unnoticed. `dym_transform` is
    stubbed directly (a 561-line planner - `_dym_plan` - is not this test's
    subject) to force the `probe_predicate == "row_present"` / `probe_needed: True`
    branch with two promo candidates, `promo_dym_plan`'s own required shape
    (`dym_candidate_codes` + `dym_probe_entities`, paired by code).
    """
    from app.services.ai_assistant_service import MCPToolCallError
    from app.services.chatbot.lanes.business import miss_suggest as miss_mod
    from app.services.chatbot.lanes.business.services import AnswerServices

    plan = {
        "probe_needed": True,
        "probe_predicate": "row_present",
        "probe_tool": "crm_marketing_promotions_list",
        "dym_candidate_codes": ["PROMO-A", "PROMO-B"],
        "dym_probe_entities": [
            {"canonical_code": "PROMO-A", "entity_type": "promotion"},
            {"canonical_code": "PROMO-B", "entity_type": "promotion"},
        ],
    }
    monkeypatch.setattr(miss_mod, "dym_transform", lambda *a, **k: plan)

    def _raising_probe(name, args):
        raise MCPToolCallError("Error executing tool crm_marketing_promotions_list: probe failed")

    services = AnswerServices(mcp_probe=_raising_probe, family_fetch=lambda query: {"data": []})
    parser = {
        "domain_hint": "promotion", "intent_hint": "check_promotion", "message_type": "business_query",
        "entities": [], "routing": {"suggested_team": None, "suggested_agent": None}, "access_levels": [],
    }
    resolved = {"resolutions": [], "unresolved_tokens": [], "tokens": []}
    gate = {"gate_debug": {"domain": "promotion"}}
    not_found = {"result_type": "promotion", "items": [], "has_result": False}

    # No pytest.raises here on purpose: the assertion IS that this does not raise.
    offer = miss_mod.run_miss_lane(
        not_found,
        parser=parser,
        resolved=resolved,
        gate=gate,
        services=services,
        contact_id="zzt-s1-promo-probe-fail",
        space_id=None,
        execution_id="zzt-s1-promo-turn",
        dry_run=True,
    )
    assert isinstance(offer, dict)
