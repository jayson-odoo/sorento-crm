"""AGENTIC-P1 round 8: the steps on both console routes (`POST /console/turn` and `GET /console/thread`). Kept apart: the console harness brings an
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

TURN = "/api/v1/system/chatbot/console/turn"
THREAD = "/api/v1/system/chatbot/console/thread"

EXPECTED = {
    "rounds": 2,
    "prompt_tokens": 350,
    "completion_tokens": 35,
    "cached_tokens": 100,
    "tool_calls": [
        # Slice 6 V3: an old turn's call has no plain-words detail; the response model sends "".
        {"name": "crm_report_ask", "status": "ok", "ms": 120, "detail": "", "round": 1},
        {"name": "crm_resolve", "status": "empty", "ms": 3, "detail": "", "round": 1},
    ],
    "reasoning": [],
}


def _read(client, contact):
    resp = client.get(THREAD, params={"contact_respond_id": contact["respond_id"], "run_id": "ZZT-run-1"})
    assert resp.status_code == 200, resp.text
    return resp.json()


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


def test_the_thread_turns_carry_steps(client, session_factory):
    contact, conv, row = _world(session_factory)
    turn = _read(client, contact)["turns"][0]
    assert turn["steps"] == EXPECTED


def test_a_turn_without_a_trace_has_empty_steps(client, session_factory):
    contact, conv, row = _world(session_factory)
    db = session_factory()
    from app.models.chatbot_turn import ChatbotTurn

    db.query(ChatbotTurn).filter(ChatbotTurn.id == row.id).update({ChatbotTurn.trace: None})
    db.commit()
    turn = _read(client, contact)["turns"][0]
    assert turn["steps"]["rounds"] == 0 and turn["steps"]["tool_calls"] == []


def test_the_turn_response_carries_the_steps_of_the_stored_row(client, session_factory, monkeypatch):
    from app.services.chatbot import console_service
    from app.services.chatbot.agent.loop import AgentTurnResult

    contact, conv, row = _world(session_factory)

    def fake(db, **kw):
        return AgentTurnResult(
            turn_id=row.id, conversation_id=str(conv.id), reply_text="a", status="answered", limit_hit=None, rounds=2,
            usage={"prompt_tokens": 350, "completion_tokens": 35, "cached_tokens": 100, "calls": 3},
            tool_calls=[{"name": "crm_report_ask", "status": "ok", "ms": 120}],
        )

    monkeypatch.setattr(console_service, "run_agent_turn", fake)
    body = client.post(
        TURN, json={"contact_respond_id": contact["respond_id"], "text": "q", "run_id": "ZZT-run-1", "force_agent": True}
    ).json()
    assert body["agent"]["steps"] == EXPECTED
