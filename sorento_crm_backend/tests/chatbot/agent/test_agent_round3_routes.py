"""AGENTIC-P1 round 3, H3: the conversation routes (red first). The read is now `GET /console/thread`;
`POST /agent/conversation/new` stays.

Kept apart from test_agent_round3.py because the console harness imported here brings an
autouse permission patch that would leak into the other tests.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent._turns import seed_turn

STOCK = "crm_inventory_stock_balance_list"

# ------------------------------------------------------------------ H3 routes

from tests.chatbot.test_console_turn_endpoint import (  # noqa: E402,F401
    VIEW,
    _ACTOR,
    _GRANTS,
    _permissions,
    client,
)

TURN = "/api/v1/system/chatbot/console/turn"
BODY = {"contact_respond_id": "ZZT-C1", "text": "x", "run_id": "ZZT-run-1", "force_agent": True}
THREAD = "/api/v1/system/chatbot/console/thread"
NEW = "/api/v1/system/chatbot/agent/conversation/new"


def test_new_conversation_refuses_a_contact_that_does_not_exist(client):
    resp = client.post(NEW, json={"contact_respond_id": "ZZT-NOBODY"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "agent_refused", "reason": "contact_not_found"}


def test_the_thread_read_for_a_contact_that_does_not_exist_is_empty_not_a_refusal(client):
    """Meaning changed from the old conversation read (409 contact_not_found): the thread still serves the
    contact's bot turns, so an agent refusal is an empty agent side, not an error."""
    resp = client.get(THREAD, params={"contact_respond_id": "ZZT-NOBODY", "run_id": "ZZT-run-1"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["turns"] == [] and resp.json()["pending_action"] is None


def test_turn_busy_is_a_200_with_the_busy_reply(client, monkeypatch):
    """Meaning changed: busy was a 409 agent_busy; the console says so in the reply text."""
    from app.services.chatbot import console_service
    from app.services.chatbot.agent.loop import AgentBusy

    def fake(db, **kw):
        raise AgentBusy()

    monkeypatch.setattr(console_service, "run_agent_turn", fake)
    resp = client.post(TURN, json=BODY)
    assert resp.status_code == 200
    assert resp.json()["reply_text"] == console_service.AGENT_BUSY_REPLY


def test_turn_passes_the_console_user_as_operator(client, monkeypatch):
    from app.services.chatbot import console_service
    from app.services.chatbot.agent.loop import AgentTurnResult

    seen = {}

    def fake(db, **kw):
        seen.update(kw)
        return AgentTurnResult("t", "c", "ok", "answered", None, 1, {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "calls": 1}, [])

    monkeypatch.setattr(console_service, "run_agent_turn", fake)
    assert client.post(TURN, json=BODY).status_code == 200
    assert seen["operator_user_id"] == _ACTOR["id"]


def test_the_thread_read_is_read_only_and_empty_when_none(client, session_factory):
    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    resp = client.get(THREAD, params={"contact_respond_id": contact["respond_id"], "run_id": "ZZT-run-1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"turns": [], "pending_action": None}
    from app.models.chatbot_agent import AgentConversation

    assert db.query(AgentConversation).filter_by(contact_respond_id=contact["respond_id"]).count() == 0


def test_the_thread_read_returns_rounds_limit_and_tool_chips(client, session_factory):
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash

    db = session_factory()
    contact = seed_agent_contact(db)
    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx))
    row = seed_turn(db, conv, minute=1, text="q", reply="a")
    row.response = {**row.response, "rounds": 3, "limit_hit": "rounds"}
    row.trace = [
        {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 1, "completion_tokens": 1},
        {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 1, "completion_tokens": 1},
        {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 1, "completion_tokens": 1},
        {"kind": "agent_tool", "name": STOCK, "status": "ok", "ms": 4},
    ]
    db.commit()

    body = client.get(THREAD, params={"contact_respond_id": contact["respond_id"], "run_id": "ZZT-run-1"}).json()
    turn = body["turns"][0]
    assert turn["turn_id"] == row.id
    assert turn["limit_hit"] == "rounds"
    assert turn["steps"]["rounds"] == 3
    assert [(c["name"], c["status"]) for c in turn["steps"]["tool_calls"]] == [(STOCK, "ok")]


def test_new_conversation_with_a_valid_contact_works(client, session_factory):
    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    resp = client.post(NEW, json={"contact_respond_id": contact["respond_id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["conversation_id"]


def test_turns_are_rate_limited_per_operator(client, monkeypatch):
    from app.services.chatbot import console_service
    from app.services import rate_limit

    seen = {}

    def fake_hit(bucket, ident, *, limit, window_seconds):
        seen.update(bucket=bucket, ident=ident, limit=limit, window=window_seconds)
        return rate_limit.RateResult(allowed=False, retry_after_seconds=120)

    monkeypatch.setattr(rate_limit, "hit", fake_hit)
    ran = []
    monkeypatch.setattr(console_service, "run_agent_turn", lambda db, **kw: ran.append(kw))
    resp = client.post(TURN, json=BODY)
    assert resp.status_code == 429
    assert "too many" in resp.text.lower()
    assert seen["ident"] == _ACTOR["id"] and seen["limit"] == 30 and seen["window"] == 600
    assert ran == []
