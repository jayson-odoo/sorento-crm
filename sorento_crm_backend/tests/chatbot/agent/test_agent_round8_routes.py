"""AGENTIC-P1 round 8: the steps on both console routes. Kept apart: the console harness brings an
autouse permission patch."""
from __future__ import annotations

from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent._turns import seed_turn
from tests.chatbot.agent.test_agent_round8 import TRACE
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures and helpers
    VIEW,
    _GRANTS,
    _permissions,
    client,
)

TURN = "/api/v1/system/chatbot/agent/turn"
CONVERSATION = "/api/v1/system/chatbot/agent/conversation"

EXPECTED = {
    "rounds": 2,
    "prompt_tokens": 350,
    "completion_tokens": 35,
    "cached_tokens": 100,
    "tool_calls": [
        # Slice 6 V3: an old turn's call has no plain-words detail; the response model sends "".
        {"name": "crm_report_ask", "status": "ok", "ms": 120, "detail": ""},
        {"name": "crm_resolve", "status": "empty", "ms": 3, "detail": ""},
    ],
}


def _world(session_factory):
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash

    db = session_factory()
    contact = seed_agent_contact(db)
    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx))
    row = seed_turn(db, conv, minute=1, text="q", reply="a")
    row.trace = TRACE
    db.commit()
    return contact, conv, row


def test_get_conversation_turns_carry_steps(client, session_factory):
    contact, conv, row = _world(session_factory)
    turn = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]}).json()["turns"][0]
    assert turn["steps"] == EXPECTED


def test_a_turn_without_a_trace_has_empty_steps(client, session_factory):
    contact, conv, row = _world(session_factory)
    db = session_factory()
    from app.models.chatbot_turn import ChatbotTurn

    db.query(ChatbotTurn).filter(ChatbotTurn.id == row.id).update({ChatbotTurn.trace: None})
    db.commit()
    turn = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]}).json()["turns"][0]
    assert turn["steps"]["rounds"] == 0 and turn["steps"]["tool_calls"] == []


def test_the_turn_response_carries_the_steps_of_the_stored_row(client, session_factory, monkeypatch):
    import app.api.v1.system.chatbot as route_mod
    from app.services.chatbot.agent.loop import AgentTurnResult

    contact, conv, row = _world(session_factory)

    def fake(db, **kw):
        return AgentTurnResult(
            turn_id=row.id, conversation_id=str(conv.id), reply_text="a", status="answered", limit_hit=None, rounds=2,
            usage={"prompt_tokens": 350, "completion_tokens": 35, "cached_tokens": 100, "calls": 3},
            tool_calls=[{"name": "crm_report_ask", "status": "ok", "ms": 120}],
        )

    monkeypatch.setattr(route_mod, "run_agent_turn", fake)
    body = client.post(TURN, json={"contact_respond_id": contact["respond_id"], "text": "q"}).json()
    assert body["steps"] == EXPECTED
