"""AGENTIC-P1 eval engine: posts each case turn to the console agent route, not the chat turn route."""

import json

import httpx

from scripts.chatbot_eval.engine import AgentTurnEngine, load_engine
from tests.chatbot_eval.test_runner import mk_case


def make_case():
    c = mk_case(text="final q")
    c.contact = {"respond_id": "9001"}
    return c


def engine_with(handler, token="tok-1"):
    eng = AgentTurnEngine("http://fake.invalid", "unused-key", 5, token=token)
    eng.transport = httpx.MockTransport(handler)
    return eng


def test_turn_posts_contact_and_text_with_bearer_token():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "turn_id": "t1",
                "reply_text": "Stock is 12.",
                "route": {"side": "agent", "reason": "forced"},
                "agent": {
                    "turn_id": "t1",
                    "conversation_id": "c1",
                    "reply_text": "Stock is 12.",
                    "status": "answered",
                    "limit_hit": None,
                    "rounds": 2,
                    "usage": {"prompt_tokens": 900, "completion_tokens": 40, "cached_tokens": 100, "calls": 2},
                    "tool_calls": [{"name": "crm_inventory_stock_balance_list", "status": "ok", "ms": 80}],
                },
            },
        )

    out = engine_with(handler).turn(make_case(), "final q", None, "run-1")
    assert seen["url"] == "http://fake.invalid/api/v1/system/chatbot/console/turn"
    assert seen["auth"] == "Bearer tok-1"
    assert seen["body"] == {
        "contact_respond_id": "9001", "text": "final q", "run_id": "run-1", "force_agent": True,
    }
    assert out.reply_text == "Stock is 12."
    assert out.branch_kind == "agent:answered"
    assert out.dry_run is True
    assert out.tokens == {"prompt": 900, "cached": 100, "output": 40}
    assert out.lane_notes == ["rounds=2", "tool crm_inventory_stock_balance_list ok"]
    assert out.tool_errors == []


def test_denied_and_failed_tool_calls_are_tool_errors():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "turn_id": "t1", "reply_text": "x",
                "agent": {
                    "turn_id": "t1", "conversation_id": "c1", "reply_text": "x", "status": "limited",
                    "limit_hit": "rounds", "rounds": 8, "usage": {},
                    "tool_calls": [
                        {"name": "crm_report_ask", "status": "denied", "ms": 1},
                        {"name": "crm_lookup_resolve", "status": "ok", "ms": 5},
                        {"name": "crm_procurement_grn_summary", "status": "timeout", "ms": 10000},
                    ],
                },
            },
        )

    out = engine_with(handler).turn(make_case(), "final q", None, "r")
    assert out.branch_kind == "agent:limited"
    assert out.tool_errors == ["crm_report_ask: denied", "crm_procurement_grn_summary: timeout"]
    assert "limit=rounds" in out.lane_notes


def test_refused_turn_is_an_http_error_outcome():
    def handler(request):
        return httpx.Response(409, json={"detail": {"code": "agent_refused", "reason": "switch_off"}})

    out = engine_with(handler).turn(make_case(), "final q", None, "r")
    assert out.reply_text == ""
    assert out.tool_errors == ["http 409 switch_off"]


def test_a_refusal_answered_as_reply_text_is_a_tool_error_with_that_text():
    """The console answers a refused contact with 200 and reply text and no agent block."""

    def handler(request):
        return httpx.Response(200, json={"turn_id": None, "reply_text": "The agent is off for this contact.", "route": {"side": "agent", "reason": "forced"}})

    out = engine_with(handler).turn(make_case(), "final q", None, "r")
    assert out.reply_text == "The agent is off for this contact."
    assert out.tool_errors == ["no agent turn"]


def test_reset_contact_starts_a_new_conversation():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"conversation_id": "c2"})

    engine_with(handler).reset_contact(make_case())
    assert seen["url"] == "http://fake.invalid/api/v1/system/chatbot/agent/conversation/new"
    assert seen["body"] == {"contact_respond_id": "9001"}


def test_token_comes_from_env_when_not_passed(monkeypatch):
    monkeypatch.setenv("EVAL_AGENT_TOKEN", "env-tok")
    eng = AgentTurnEngine("http://fake.invalid", "unused-key", 5)
    assert eng.token == "env-tok"


def test_load_engine_by_spec():
    eng = load_engine("scripts.chatbot_eval.engine:AgentTurnEngine", base_url="http://x", api_key="k", timeout=1)
    assert isinstance(eng, AgentTurnEngine)
