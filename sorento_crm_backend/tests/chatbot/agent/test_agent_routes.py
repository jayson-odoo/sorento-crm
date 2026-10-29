"""AGENTIC-P1 card section 8: the console's agent endpoints.

Auth harness is the console turn tests': `check_user_has_permission` is monkeypatched and the
caller is stubbed through `get_current_user`. All three routes sit on the same
`system.chat_history.view` slug as `/console/turn`.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent._turns import seed_turn
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures + helpers
    VIEW,
    _GRANTS,
    _permissions,
    client,
)

TURN = "/api/v1/system/chatbot/agent/turn"
CONVERSATION = "/api/v1/system/chatbot/agent/conversation"
NEW = "/api/v1/system/chatbot/agent/conversation/new"


def _result(**over):
    from app.services.chatbot.agent.loop import AgentTurnResult

    fields = dict(
        turn_id="11111111-1111-1111-1111-111111111111",
        conversation_id="22222222-2222-2222-2222-222222222222",
        reply_text="There are 12 units.",
        status="answered",
        limit_hit=None,
        rounds=2,
        usage={"prompt_tokens": 250, "completion_tokens": 30, "cached_tokens": 100, "calls": 2},
        tool_calls=[{"name": "crm_inventory_stock_balance_list", "status": "ok", "ms": 14}],
    )
    fields.update(over)
    return AgentTurnResult(**fields)


@pytest.fixture()
def patch_run(monkeypatch):
    """Replace `run_agent_turn` wherever the route may have bound it. Returns the call log."""
    import app.api.v1.system.chatbot as route_mod
    import app.services.chatbot.agent.loop as loop_mod

    calls: list[dict] = []
    box: dict = {"result": _result(), "exc": None}

    def fake(db, **kw):
        calls.append(kw)
        if box["exc"] is not None:
            raise box["exc"]
        return box["result"]

    monkeypatch.setattr(loop_mod, "run_agent_turn", fake)
    monkeypatch.setattr(route_mod, "run_agent_turn", fake, raising=False)
    fake.calls = calls
    fake.box = box
    return fake


def test_turn_returns_the_result_fields(client, patch_run):
    resp = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "stock of SRTWT7445?"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reply_text"] == "There are 12 units."
    assert body["turn_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["conversation_id"] == "22222222-2222-2222-2222-222222222222"
    assert body["status"] == "answered"
    assert body["limit_hit"] is None
    assert body["rounds"] == 2
    assert body["usage"] == {"prompt_tokens": 250, "completion_tokens": 30, "cached_tokens": 100, "calls": 2}
    assert body["tool_calls"] == [{"name": "crm_inventory_stock_balance_list", "status": "ok", "ms": 14}]
    assert patch_run.calls[0]["contact_respond_id"] == "ZZT-C1"
    assert patch_run.calls[0]["text"] == "stock of SRTWT7445?"


def test_turn_reports_a_limit_hit(client, patch_run):
    patch_run.box["result"] = _result(status="limited", limit_hit="rounds")
    body = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"}).json()
    assert body["status"] == "limited" and body["limit_hit"] == "rounds"


@pytest.mark.parametrize("reason", ["contact_not_found", "ai_replies_off", "switch_off", "no_linked_user"])
def test_a_refusal_is_a_409_with_the_reason(client, patch_run, reason):
    from app.services.chatbot.agent.access import AgentRefused

    patch_run.box["exc"] = AgentRefused(reason)
    resp = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"})

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {"code": "agent_refused", "reason": reason}


def test_turn_without_the_view_permission_is_403(client, patch_run):
    _GRANTS.discard(VIEW)
    resp = client.post(TURN, json={"contact_respond_id": "ZZT-C1", "text": "x"})
    assert resp.status_code == 403
    assert patch_run.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"contact_respond_id": "ZZT-C1", "text": ""},
        {"contact_respond_id": "ZZT-C1", "text": "x" * 4001},
        {"contact_respond_id": "ZZT-C1"},
        {"text": "x"},
    ],
)
def test_turn_validates_the_body(client, patch_run, body):
    assert client.post(TURN, json=body).status_code == 422
    assert patch_run.calls == []


def _agent_contact_with_conversation(session_factory):
    """A switched-on contact with a linked user, and the conversation a turn would have made
    for them (round 3: the conversation routes build the agent context like the turn does)."""
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash
    from tests.chatbot.agent._seed import seed_agent_contact

    db = session_factory()
    contact = seed_agent_contact(db)
    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(
        db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx)
    )
    return db, contact, conv


def test_get_conversation_lists_the_current_conversations_turns(client, session_factory):
    db, contact, conv = _agent_contact_with_conversation(session_factory)
    t1 = seed_turn(db, conv, minute=1, text="first", reply="reply one")
    t2 = seed_turn(db, conv, minute=2, text="second", reply="reply two")
    db.commit()

    resp = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conversation_id"] == str(conv.id)
    assert [t["turn_id"] for t in body["turns"]] == [t1.id, t2.id]
    first = body["turns"][0]
    assert first["text"] == "first"
    assert first["reply_text"] == "reply one"
    assert first["status"] == "done"
    assert first["created_at"]


def test_get_conversation_for_a_new_contact_is_empty(client, session_factory):
    from tests.chatbot.agent._seed import seed_agent_contact

    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    resp = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conversation_id"] is None  # round 3: reading never creates a conversation
    assert body["turns"] == []


def test_get_conversation_without_the_view_permission_is_403(client):
    _GRANTS.discard(VIEW)
    assert client.get(CONVERSATION, params={"contact_respond_id": "ZZT-ROUTE-1"}).status_code == 403


def test_get_conversation_needs_the_contact_id(client):
    assert client.get(CONVERSATION).status_code == 422


def test_new_conversation_returns_a_fresh_id_and_empties_the_next_read(client, session_factory):
    db, contact, conv = _agent_contact_with_conversation(session_factory)
    seed_turn(db, conv, minute=1, text="old", reply="old reply")
    db.commit()

    resp = client.post(NEW, json={"contact_respond_id": contact["respond_id"]})

    assert resp.status_code == 200, resp.text
    new_id = resp.json()["conversation_id"]
    assert new_id and new_id != str(conv.id)
    after = client.get(CONVERSATION, params={"contact_respond_id": contact["respond_id"]}).json()
    assert after["conversation_id"] == new_id
    assert after["turns"] == []


def test_new_conversation_without_the_view_permission_is_403(client):
    _GRANTS.discard(VIEW)
    assert client.post(NEW, json={"contact_respond_id": "ZZT-ROUTE-2"}).status_code == 403
