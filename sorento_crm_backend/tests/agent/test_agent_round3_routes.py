"""AGENTIC-P1 round 3, H3: the conversation routes (red first).

Kept apart from test_agent_round3.py because the console harness imported here brings an
autouse permission patch that would leak into the other tests.
"""
from __future__ import annotations

import pytest

from tests.agent._seed import seed_agent_contact
from tests.agent._turns import seed_turn

STOCK = "crm_inventory_stock_balance_list"

# ------------------------------------------------------------------ H3 routes

from tests.chatbot.test_console_turn_endpoint import (  # noqa: E402,F401
    VIEW,
    _ACTOR,
    _GRANTS,
    _permissions,
    client,
)

TURN = "/api/v1/system/chatbot/agent/turn"
CONVERSATION = "/api/v1/system/chatbot/agent/conversation"
NEW = "/api/v1/system/chatbot/agent/conversation/new"


@pytest.mark.parametrize("method, url", [("get", CONVERSATION), ("post", NEW)])
def test_conversation_routes_refuse_like_the_turn_route(client, method, url):
    if method == "get":
        resp = client.get(url, params={"contact_respond_id": "ZZT-NOBODY"})
    else:
        resp = client.post(url, json={"contact_respond_id": "ZZT-NOBODY"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "agent_refused", "reason": "contact_not_found"}


def test_turn_busy_is_a_409_agent_busy(client, monkeypatch):
    import app.api.v1.system.chatbot as route_mod
    from app.services.agent.loop import AgentBusy

    def fake(db, **kw):
        raise AgentBusy()

    monkeypatch.setattr(route_mod, "run_agent_turn", fake)
    resp = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "agent_busy"


def test_turn_passes_the_console_user_as_operator(client, monkeypatch):
    import app.api.v1.system.chatbot as route_mod
    from app.services.agent.loop import AgentTurnResult

    seen = {}

    def fake(db, **kw):
        seen.update(kw)
        return AgentTurnResult("t", "c", "ok", "answered", None, 1, {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "calls": 1}, [])

    monkeypatch.setattr(route_mod, "run_agent_turn", fake)
    assert client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"}).status_code == 200
    assert seen["operator_user_id"] == _ACTOR["id"]


def test_get_conversation_is_read_only_and_null_when_none(client, session_factory):
    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    resp = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"conversation_id": None, "turns": []}
    from app.models.chatbot_agent import AgentConversation

    assert db.query(AgentConversation).filter_by(contact_respond_id=contact["respond_id"]).count() == 0


def test_get_conversation_returns_rounds_limit_and_tool_chips(client, session_factory):
    from app.services.agent import memory
    from app.services.agent.access import build_context, grants_hash

    db = session_factory()
    contact = seed_agent_contact(db)
    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx))
    row = seed_turn(db, conv, minute=1, text="q", reply="a", digest=[{"name": STOCK, "args": {}, "status": "ok"}])
    row.response = {**row.response, "rounds": 3, "limit_hit": "rounds"}
    db.commit()

    body = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]}).json()
    assert body["conversation_id"] == str(conv.id)
    turn = body["turns"][0]
    assert turn["rounds"] == 3
    assert turn["limit_hit"] == "rounds"
    assert turn["tool_calls"] == [{"name": STOCK, "status": "ok"}]


def test_new_conversation_with_a_valid_contact_works(client, session_factory):
    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    resp = client.post(NEW, json={"contact_respond_id": contact["respond_id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["conversation_id"]


def test_turns_are_rate_limited_per_operator(client, monkeypatch):
    import app.api.v1.system.chatbot as route_mod
    from app.services import rate_limit

    seen = {}

    def fake_hit(bucket, ident, *, limit, window_seconds):
        seen.update(bucket=bucket, ident=ident, limit=limit, window=window_seconds)
        return rate_limit.RateResult(allowed=False, retry_after_seconds=120)

    monkeypatch.setattr(rate_limit, "hit", fake_hit)
    ran = []
    monkeypatch.setattr(route_mod, "run_agent_turn", lambda db, **kw: ran.append(kw))
    resp = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"})
    assert resp.status_code == 429
    assert "too many" in resp.text.lower()
    assert seen["ident"] == _ACTOR["id"] and seen["limit"] == 30 and seen["window"] == 600
    assert ran == []
