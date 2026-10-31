"""AGENTIC-REASONING-VIS: both console routes (`POST /console/turn` and `GET /console/thread`) return each round's reasoning beside its tool calls. Kept apart:
the console harness brings an autouse permission patch."""
from __future__ import annotations

from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent._turns import seed_turn
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures and helpers
    VIEW,
    _GRANTS,
    _permissions,
    client,
)

TURN = "/api/v1/system/chatbot/console/turn"
THREAD = "/api/v1/system/chatbot/console/thread"
STOCK = "crm_inventory_stock_balance_list"

TRACE = [
    {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 10, "completion_tokens": 2, "tool_calls": 1},
    {"kind": "agent_reasoning", "round": 1, "text": "First find the stock balance."},
    {"kind": "agent_tool", "name": STOCK, "status": "ok", "ms": 5, "detail": "Stock balance: 1 row"},
    {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 20, "completion_tokens": 3, "tool_calls": 1},
    {"kind": "agent_reasoning", "round": 2, "text": "Answer with the figure."},
    {"kind": "agent_round", "kind_of_call": "final", "prompt_tokens": 5, "completion_tokens": 1, "tool_calls": 1},
    {"kind": "agent_reasoning", "kind_of_call": "final", "round": 2, "text": "Wrap up with what was read."},
]

EXPECTED_REASONING = [
    {"round": 1, "text": "First find the stock balance.", "final": False},
    {"round": 2, "text": "Answer with the figure.", "final": False},
    {"round": 2, "text": "Wrap up with what was read.", "final": True},
]


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


def test_the_thread_read_returns_each_rounds_reasoning(client, session_factory):
    contact, _conv, _row = _world(session_factory)
    turn = client.get(THREAD, params={"contact_respond_id": contact["respond_id"], "run_id": "ZZT-run-1"}).json()["turns"][0]
    assert turn["steps"]["reasoning"] == EXPECTED_REASONING
    assert [(c["name"], c["round"]) for c in turn["steps"]["tool_calls"]] == [(STOCK, 1)]
    # Never the reply.
    assert "stock balance" not in turn["reply_text"].lower()


def test_the_turn_response_returns_the_reasoning_of_the_stored_row(client, session_factory, monkeypatch):
    from app.services.chatbot import console_service
    from app.services.chatbot.agent.loop import AgentTurnResult

    contact, conv, row = _world(session_factory)

    def fake(db, **kw):
        return AgentTurnResult(
            turn_id=row.id, conversation_id=str(conv.id), reply_text="a", status="answered", limit_hit=None, rounds=2,
            usage={"prompt_tokens": 30, "completion_tokens": 5, "cached_tokens": 0, "calls": 2},
            tool_calls=[{"name": STOCK, "status": "ok", "ms": 5}],
        )

    monkeypatch.setattr(console_service, "run_agent_turn", fake)
    body = client.post(
        TURN, json={"contact_respond_id": contact["respond_id"], "text": "q", "run_id": "ZZT-run-1", "force_agent": True}
    ).json()
    assert body["agent"]["steps"]["reasoning"] == EXPECTED_REASONING
    assert "First find" not in body["reply_text"]


def test_the_reasoning_is_refused_without_the_console_permission(client, session_factory):
    contact, _conv, _row = _world(session_factory)
    _GRANTS.discard(VIEW)
    try:
        response = client.get(THREAD, params={"contact_respond_id": contact["respond_id"], "run_id": "ZZT-run-1"})
    finally:
        _GRANTS.add(VIEW)
    assert response.status_code == 403
    assert "First find" not in response.text
