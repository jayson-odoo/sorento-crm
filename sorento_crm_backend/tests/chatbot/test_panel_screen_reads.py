"""AGENTIC-UNIFY PR 3, slice 4 (red): what the panel screen may read from the server.

UAC: documentation/plans/chatbot/agentic-unify-panel-acceptance-criteria.md
AC-18 (outcomes are stored panel messages), AC-21 (files), AC-22 (cards read live, outcome lines),
AC-23 (pill, steps and trace only for `system.ai_assistant_settings.view`), AC-26 (old path unchanged).

Plan: documentation/plans/chatbot/PLAN-agentic-unify-panel-31oct.md, "Slice 4: the panel screen".

Fakes sit at the provider boundary only (Jev, the agent's model client, the engine's `run_turn` for a
chat turn, the MCP seam). The routes, router, agent loop, action store and message reads are real, on
Postgres, with every row seeded here. Both routes that return messages are driven:
`GET /ai-assistant/conversations/{id}/messages` and `POST /ai-assistant/chat`.

Contract assumed (tell the captain if any does not fit):
- A Confirm, Cancel or Withdraw through the panel route appends ONE assistant message to the
  action's thread (`panel-<conversation id>`): content = the outcome's `reply_text`,
  `metadata_json.route == "agent"`, `metadata_json.status` = the outcome's status.
- A message read (both routes) rebuilds `agent.pending_action` and `agent.actions` from the action
  store for any stored message that carries `agent` and a `chatbot_turn_id`, whatever the stored copy says.
- For a reader without `system.ai_assistant_settings.view`, of `agent` only `pending_action` and
  `actions` stay; `chatbot_turn_id` and `route_decision` go; `route` stays.
- `metadata_json.route_decision` is `RouteDecision.as_response()` and is STORED for everyone.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import event

import app.main  # noqa: F401  isort:skip
from app.models.ai_assistant import AIAssistantConversation, AIAssistantMessage
from app.models.chatbot_agent import AgentAction
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import panel_service
from tests.chatbot.agent.test_router import jev_answer
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_panel_agent_side import (  # noqa: F401  (fixtures and helpers)
    NOTE_SLUG,
    NOTE_TOOL,
    STOCK_SLUG,
    PANEL_ACTIONS,
    CATALOG,
    Provider,
    agent_model,
    as_user,
    audit_listeners,
    jev,
    note_write,
    panel_key,
    round_of,
    stock_then_answer,
    tc,
    answer_,
)
from tests.chatbot.test_panel_live_turn import products  # noqa: F401  (fixture)
from tests.chatbot.test_panel_principal import (  # noqa: F401
    AGENT,
    USE,
    Staff,
    _scope_listeners,
    grants,
    run_panel,
    seed_staff,
    staff,
    world,
)

SETTINGS_VIEW = "system.ai_assistant_settings.view"
CHAT_URL = "/api/v1/system/ai-assistant/chat"
MESSAGES = "/api/v1/system/ai-assistant/conversations/{}/messages"
LONG_AGO = datetime.utcnow() - timedelta(days=2)

# Values that must never reach a reader without the settings slug. Each is unique so an absence check
# over the raw JSON cannot match something legitimate.
M_TOOL = "ZZT-TOOL-MARK-1f3a"
M_STEP = "ZZT-STEP-MARK-77b2"
M_USAGE = 918273645
M_REPLY = "ZZT-AGENT-REPLY-TEXT-MARK-5c9d"
M_REASON = "ZZT-ROUTE-REASON-MARK-a41e"
M_MODEL = "zzt-jev-model-mark-3d7"


# --------------------------------------------------------------------------- #
# Seeds and helpers
# --------------------------------------------------------------------------- #


def _full_agent_dict(turn_id: str, *, pending: dict | None, actions: list | None) -> dict[str, Any]:
    """An agent turn as `agent_view` stores it, every trace field carrying a marker."""
    return {
        "turn_id": turn_id,
        "conversation_id": str(uuid.uuid4()),
        "reply_text": M_REPLY,
        "status": "done",
        "limit_hit": False,
        "rounds": 3,
        "usage": {"total_tokens": M_USAGE},
        "tool_calls": [{"name": M_TOOL, "status": "ok"}],
        "steps": [{"kind": "tool", "name": M_STEP}],
        "pending_action": pending,
        "actions": actions if actions is not None else [],
    }


def _pending_dict(action_id: str, turn_id: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "turn_id": turn_id,
        "lines": ["ZZT write a note"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }


def seed_proposing_message(
    session_factory,
    staff_: Staff,
    *,
    status: str = "proposed",
    steps: list[dict] | None = None,
    stored_pending: bool = True,
    stored_actions: list | None = None,
    route_decision: dict | None = None,
) -> tuple[str, str, str]:
    """A user message, the agent reply that proposed a change, and the real `agent_actions` row it
    points at. The stored copy claims what the turn said at the time. Returns (action_id, turn_id, message_id)."""
    db = session_factory()
    action_id, turn_id = str(uuid.uuid4()), str(uuid.uuid4())
    step_rows = steps or [{"tool": NOTE_TOOL, "args": {}, "before": {}, "shown": {}, "summary": "ZZT write a note", "status": "proposed"}]
    if stored_actions is None and stored_pending:
        stored_actions = [{"id": action_id, "status": "proposed", "steps": [{"summary": "ZZT write a note", "status": "proposed"}]}]
    db.add(AgentAction(
        id=action_id, conversation_id=str(uuid.uuid4()), turn_id=turn_id,
        contact_respond_id=panel_key(staff_), user_id=staff_.user_id, status=status,
        steps=step_rows,
    ))
    db.add(AIAssistantMessage(conversation_id=staff_.conv_id, role="user", content="ZZT please note it", created_at=LONG_AGO))
    message = AIAssistantMessage(
        conversation_id=staff_.conv_id, role="assistant", content="ZZT I can write that note. Confirm?", created_at=LONG_AGO + timedelta(seconds=1),
        metadata_json={
            "chatbot_turn_id": turn_id,
            "route": "agent",
            "status": "done",
            "attachments": [],
            "suggestions": [],
            **({"route_decision": route_decision} if route_decision else {}),
            "agent": _full_agent_dict(
                turn_id,
                pending=_pending_dict(action_id, turn_id) if stored_pending else None,
                actions=stored_actions,
            ),
        },
    )
    db.add(message)
    db.commit()
    return action_id, turn_id, str(message.id)


def seed_parked_withdrawable(session_factory, staff_: Staff, monkeypatch) -> tuple[str, str, str]:
    """An executed action holding one parked (withdrawable) step, and the message that proposed it."""
    import app.api.v1.sla.form_actions as form_actions

    monkeypatch.setattr(form_actions, "cancel_form_action", lambda action_id, current_user, db: None)
    due = (datetime.utcnow() + timedelta(seconds=60)).isoformat()
    step = {
        "tool": NOTE_TOOL, "args": {}, "before": {}, "shown": {}, "summary": "ZZT parked", "status": "done",
        "after": {"deferred": True, "commit_at": due, "window_seconds": 60, "pending_action_id": str(uuid.uuid4())},
    }
    return seed_proposing_message(
        session_factory, staff_, status="executed", steps=[step], stored_pending=False,
        stored_actions=[{"id": "stale", "status": "executed", "steps": [{"summary": "ZZT parked", "status": "done"}]}],
    )


def stored_messages(session_factory, conv_id: str) -> list[AIAssistantMessage]:
    db = session_factory()
    db.expire_all()
    return (
        db.query(AIAssistantMessage)
        .filter(AIAssistantMessage.conversation_id == conv_id)
        .order_by(AIAssistantMessage.created_at.asc(), AIAssistantMessage.id.asc())
        .all()
    )


def read_thread(client, conv_id: str) -> list[dict[str, Any]]:
    resp = client.get(MESSAGES.format(conv_id))
    assert resp.status_code == 200, resp.text
    return resp.json()


def message_of(rows: list[dict[str, Any]], message_id: str) -> dict[str, Any]:
    found = [r for r in rows if r["id"] == message_id]
    assert len(found) == 1, f"message {message_id} not in {[r['id'] for r in rows]}"
    return found[0]


@pytest.fixture()
def http(session_factory, monkeypatch, staff, grants, as_user, world, jev):
    """A client for the staff member who holds the rollout slug, the engine on the test database,
    Jev answering chat by default. The test edits `grants` for who may see the trace."""
    monkeypatch.setattr(AIAssistantChatService, "ensure_enabled", lambda self: None)
    monkeypatch.setattr(panel_service, "SessionLocal", session_factory)
    grants.add(AGENT)
    jev.answer = jev_answer("chat", 0.95)
    return as_user(staff.user_id)


def fake_chat_turn(monkeypatch, actions: list[dict] | None = None) -> engine_mod.TurnResult:
    fake = engine_mod.TurnResult(
        turn_id=str(uuid.uuid4()), is_test=False, branch_kind="business_query", status="done",
        reply={"text": "ZZT chat reply", "quick_replies": ""},
        actions=actions if actions is not None else [{"kind": "send_message", "reply": {"text": "ZZT chat reply"}, "dry_run": False}],
    )
    monkeypatch.setattr(engine_mod, "run_turn", lambda *a, **k: fake)
    monkeypatch.setattr(panel_service, "run_turn", lambda *a, **k: fake)
    return fake


def post_chat(client, staff_: Staff, text: str = "why did stock fall in the main warehouse"):
    resp = client.post(CHAT_URL, json={"conversation_id": staff_.conv_id, "message": text})
    assert resp.status_code == 200, resp.text
    return resp


# --------------------------------------------------------------------------- #
# 1 (AC-21): a chat turn's file keeps its type
# --------------------------------------------------------------------------- #

FILE = {
    "url": "https://files.example.invalid/zzt-spec.pdf",
    "filename": "zzt-spec.pdf",
    "mimeType": "application/pdf",
    "attachmentType": "specification",
}


def test_a_chat_turns_stored_file_keeps_mime_type_and_attachment_type(session_factory, monkeypatch, staff, http):
    fake_chat_turn(monkeypatch, actions=[
        {"kind": "send_message", "reply": {"text": "ZZT here is the file"}, "dry_run": False},
        {"kind": "send_attachments", "attachments_src": [dict(FILE)], "reply": {"text": ""}, "dry_run": False},
    ])

    resp = post_chat(http, staff)

    stored = [m for m in stored_messages(session_factory, staff.conv_id) if m.role == "assistant"]
    assert len(stored) == 1
    assert stored[0].metadata_json["attachments"] == [FILE], "mimeType / attachmentType were dropped on store"
    returned = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    assert returned["metadata_json"]["attachments"] == [FILE]


# --------------------------------------------------------------------------- #
# 2 (AC-23): the route decision is stored for the pill
# --------------------------------------------------------------------------- #


def _assert_decision(decision: dict[str, Any], side: str) -> None:
    assert decision["side"] == side
    assert decision["reason"]
    assert decision["score"] == pytest.approx(0.95, abs=0.01)
    assert decision["model"] == "jev-1.14.0"


def test_a_chat_turn_stores_the_route_decision_for_a_trace_viewer(session_factory, monkeypatch, staff, grants, http, world):
    grants.add(SETTINGS_VIEW)
    fake_chat_turn(monkeypatch)

    resp = post_chat(http, staff)

    stored = [m for m in stored_messages(session_factory, staff.conv_id) if m.role == "assistant"][0]
    _assert_decision(stored.metadata_json["route_decision"], "chat")
    returned = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    _assert_decision(returned["metadata_json"]["route_decision"], "chat")


def test_an_agent_turn_stores_the_route_decision_for_a_trace_viewer(
    session_factory, monkeypatch, staff, grants, http, world, jev, agent_model
):
    grants.update({SETTINGS_VIEW, STOCK_SLUG})
    jev.answer = jev_answer("agent", 0.95)
    agent_model.set(stock_then_answer("ZZT stock is fine."))

    resp = post_chat(http, staff)

    stored = [m for m in stored_messages(session_factory, staff.conv_id) if m.role == "assistant"][0]
    assert stored.metadata_json["route"] == "agent"
    _assert_decision(stored.metadata_json["route_decision"], "agent")
    returned = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    _assert_decision(returned["metadata_json"]["route_decision"], "agent")


# --------------------------------------------------------------------------- #
# 3, 4 (AC-22): a card is read live, whatever the stored copy says
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("holder", [True, False], ids=["trace-holder", "no-trace-slug"])
def test_a_proposal_still_waiting_reads_as_waiting(session_factory, staff, grants, http, holder):
    """Positive control for the tests below: the live read keeps a waiting card."""
    grants.add(NOTE_SLUG)
    if holder:
        grants.add(SETTINGS_VIEW)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)

    agent = message_of(read_thread(http, staff.conv_id), message_id)["metadata_json"]["agent"]

    assert agent["pending_action"] is not None and agent["pending_action"]["id"] == action_id
    assert any(a["id"] == action_id and a["status"] == "proposed" for a in agent["actions"]), agent["actions"]


@pytest.mark.parametrize("holder", [True, False], ids=["trace-holder", "no-trace-slug"])
def test_after_a_confirm_the_thread_reads_the_action_as_executed_and_nothing_pending(
    session_factory, staff, grants, http, note_write, holder
):
    grants.add(NOTE_SLUG)
    if holder:
        grants.add(SETTINGS_VIEW)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    assert http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={}).status_code == 200

    agent = message_of(read_thread(http, staff.conv_id), message_id)["metadata_json"]["agent"]

    assert agent["pending_action"] is None, "Confirm is still offered after it was used"
    decided = [a for a in agent["actions"] if a["id"] == action_id]
    assert len(decided) == 1 and decided[0]["status"] == "executed", agent["actions"]
    # the stored row is not what changed the answer: it still says the card is waiting
    stored = next(m for m in stored_messages(session_factory, staff.conv_id) if str(m.id) == message_id)
    assert stored.metadata_json["agent"]["pending_action"]["id"] == action_id


@pytest.mark.parametrize("holder", [True, False], ids=["trace-holder", "no-trace-slug"])
def test_after_a_cancel_the_thread_reads_the_action_as_cancelled_and_nothing_pending(
    session_factory, staff, grants, http, note_write, holder
):
    grants.add(NOTE_SLUG)
    if holder:
        grants.add(SETTINGS_VIEW)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    assert http.post(f"{PANEL_ACTIONS}/{action_id}/cancel", json={}).status_code == 200

    agent = message_of(read_thread(http, staff.conv_id), message_id)["metadata_json"]["agent"]

    assert agent["pending_action"] is None
    decided = [a for a in agent["actions"] if a["id"] == action_id]
    assert len(decided) == 1 and decided[0]["status"] == "cancelled", agent["actions"]
    stored = next(m for m in stored_messages(session_factory, staff.conv_id) if str(m.id) == message_id)
    assert stored.metadata_json["agent"]["pending_action"]["id"] == action_id


def test_after_a_withdraw_the_step_reads_as_withdrawn(session_factory, monkeypatch, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_parked_withdrawable(session_factory, staff, monkeypatch)
    before = message_of(read_thread(http, staff.conv_id), message_id)["metadata_json"]["agent"]
    # control: before the withdraw the live read shows the parked step as done, not the stale stored copy
    assert [a["id"] for a in before["actions"]] == [action_id], before["actions"]
    assert before["actions"][0]["steps"][0]["status"] == "done"

    assert http.post(f"{PANEL_ACTIONS}/{action_id}/steps/0/withdraw", json={}).status_code == 200

    after = message_of(read_thread(http, staff.conv_id), message_id)["metadata_json"]["agent"]
    assert [a["id"] for a in after["actions"]] == [action_id]
    assert after["actions"][0]["steps"][0]["status"] == "withdrawn"


def test_the_post_chat_route_also_reads_cards_live(session_factory, monkeypatch, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    assert http.post(f"{PANEL_ACTIONS}/{action_id}/cancel", json={}).status_code == 200
    fake_chat_turn(monkeypatch)

    messages = post_chat(http, staff).json()["messages"]

    agent = message_of(messages, message_id)["metadata_json"]["agent"]
    assert agent["pending_action"] is None
    assert [a["status"] for a in agent["actions"] if a["id"] == action_id] == ["cancelled"]


# --------------------------------------------------------------------------- #
# 5 (AC-18, AC-22): a decision writes its outcome into the thread
# --------------------------------------------------------------------------- #


def _assert_one_outcome(session_factory, staff_: Staff, before_count: int, proposing_id: str, body: dict[str, Any]) -> None:
    rows = stored_messages(session_factory, staff_.conv_id)
    assert len(rows) == before_count + 1, f"expected one appended message, thread went {before_count} -> {len(rows)}"
    outcome = rows[-1]
    assert str(outcome.id) != proposing_id and outcome.role == "assistant"
    assert outcome.content == body["reply_text"] and outcome.content
    assert outcome.metadata_json["route"] == "agent"
    assert outcome.metadata_json["status"] == body["status"]
    order = [str(r.id) for r in rows]
    assert order.index(proposing_id) < order.index(str(outcome.id)), "the outcome is not after the proposing reply"


def test_confirm_appends_its_outcome_as_an_agent_message_after_the_proposal(session_factory, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    before = len(stored_messages(session_factory, staff.conv_id))

    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})

    assert resp.status_code == 200, resp.text
    _assert_one_outcome(session_factory, staff, before, message_id, resp.json())
    assert resp.json()["status"] == "executed"


def test_cancel_appends_its_outcome_as_an_agent_message_after_the_proposal(session_factory, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    before = len(stored_messages(session_factory, staff.conv_id))

    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/cancel", json={})

    assert resp.status_code == 200, resp.text
    _assert_one_outcome(session_factory, staff, before, message_id, resp.json())
    assert resp.json()["status"] == "cancelled"


def test_withdraw_appends_its_outcome_as_an_agent_message_after_the_proposal(
    session_factory, monkeypatch, staff, grants, http, note_write
):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_parked_withdrawable(session_factory, staff, monkeypatch)
    before = len(stored_messages(session_factory, staff.conv_id))

    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/steps/0/withdraw", json={})

    assert resp.status_code == 200, resp.text
    _assert_one_outcome(session_factory, staff, before, message_id, resp.json())


# --------------------------------------------------------------------------- #
# 6 (AC-22): a refused decision writes nothing
# --------------------------------------------------------------------------- #


def test_a_second_confirm_is_refused_and_appends_nothing(session_factory, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    first = http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})
    assert first.status_code == 200
    after_first = len(stored_messages(session_factory, staff.conv_id))
    assert after_first == 3, "control: the first Confirm appended its one outcome (seed 2 + 1)"

    second = http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})

    assert second.status_code == 409
    assert len(stored_messages(session_factory, staff.conv_id)) == after_first, "a refused decision wrote a message"


def test_another_users_action_is_a_404_and_appends_nothing_to_either_thread(session_factory, staff, grants, http, note_write):
    grants.add(NOTE_SLUG)
    action_id, _turn, _message_id = seed_proposing_message(session_factory, staff)
    # control: the owner can decide a different proposal and it appends, so a missing append below is not a dead route
    control_id, _t, _m = seed_proposing_message(session_factory, staff)
    owner_before = len(stored_messages(session_factory, staff.conv_id))
    assert http.post(f"{PANEL_ACTIONS}/{control_id}/cancel", json={}).status_code == 200
    owner_mid = len(stored_messages(session_factory, staff.conv_id))
    assert owner_mid == owner_before + 1
    intruder = seed_staff(session_factory)
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": intruder.user_id, "name": "ZZT"}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": intruder.user_id, "name": "ZZT"}
    grants.add(USE)

    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})

    assert resp.status_code == 404, resp.text
    assert len(stored_messages(session_factory, staff.conv_id)) == owner_mid
    assert stored_messages(session_factory, intruder.conv_id) == []


# --------------------------------------------------------------------------- #
# 7 (AC-22): a deleted thread still decides, silently
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("verb", ["confirm", "cancel"])
def test_a_deleted_thread_still_decides_and_appends_nothing(session_factory, staff, grants, http, note_write, verb):
    grants.add(NOTE_SLUG)
    action_id, _turn, _message_id = seed_proposing_message(session_factory, staff)
    # control: with the thread alive the same call appends (so the empty thread below is the deletion's doing)
    control_id, _t, _m = seed_proposing_message(session_factory, staff)
    n = len(stored_messages(session_factory, staff.conv_id))
    assert http.post(f"{PANEL_ACTIONS}/{control_id}/cancel", json={}).status_code == 200
    assert len(stored_messages(session_factory, staff.conv_id)) == n + 1
    db = session_factory()
    db.query(AIAssistantConversation).filter(AIAssistantConversation.id == staff.conv_id).delete()
    db.commit()

    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/{verb}", json={})

    assert resp.status_code == 200, resp.text
    db = session_factory()
    db.expire_all()
    assert db.get(AgentAction, action_id).status == ("executed" if verb == "confirm" else "cancelled")
    assert stored_messages(session_factory, staff.conv_id) == []


# --------------------------------------------------------------------------- #
# 8 (AC-18): a later turn does not quote the outcome as a bot reply
# --------------------------------------------------------------------------- #


def test_a_later_turn_neither_crashes_on_nor_quotes_an_outcome_message(
    session_factory, monkeypatch, staff, grants, http, note_write, jev, agent_model
):
    grants.add(NOTE_SLUG)
    marker = f"ZZT-BOT-REPLY-{uuid.uuid4().hex[:8]}"
    db = session_factory()
    db.add_all([
        AIAssistantMessage(conversation_id=staff.conv_id, role="user", content="ZZT first question", created_at=LONG_AGO - timedelta(hours=1)),
        AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content=f"ZZT bot answer {marker}", created_at=LONG_AGO - timedelta(minutes=59)),
    ])
    db.commit()
    action_id, _turn, message_id = seed_proposing_message(session_factory, staff)
    resp = http.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})
    assert resp.status_code == 200
    outcome_text = resp.json()["reply_text"]
    assert any(m.content == outcome_text for m in stored_messages(session_factory, staff.conv_id)), (
        "precondition: the Confirm wrote its outcome into the thread"
    )

    before, after = panel_service._quoted_bot_replies(session_factory(), staff.conv_id)
    assert marker in before + after, "control: an earlier bot reply is quoted"
    assert outcome_text not in before + after, "the outcome was quoted as a bot reply"

    # Jev sees the thread: the outcome is not an exchange of its own and the proposing reply is.
    jev.answer = jev_answer("agent", 0.95)
    agent_model.set([answer_("ZZT ok.")])
    result = run_panel(session_factory, monkeypatch, staff, "and what else")
    assert result.route == "agent"
    state = jev.calls[-1]["state"]
    replies = [e["reply"] for e in state["recent_exchanges"]]
    assert not any(outcome_text[:30] in r for r in replies), replies
    assert any("I can write that note" in r for r in replies), replies
    quoted = json.dumps(agent_model.provider.seen[0]["messages"])
    assert outcome_text not in quoted.replace("\\n", "\n"), "the agent was handed its own outcome as a bot reply"


# --------------------------------------------------------------------------- #
# 9 (AC-23): the strip, on both routes
# --------------------------------------------------------------------------- #

TRACE_KEYS = ("steps", "tool_calls", "usage", "rounds", "limit_hit", "reply_text")


def _seed_trace_message(session_factory, staff_: Staff) -> str:
    decision = {"side": "agent", "reason": M_REASON, "score": 0.91, "model": M_MODEL, "ms": 5, "error": None}
    _action, _turn, message_id = seed_proposing_message(session_factory, staff_, route_decision=decision)
    return message_id


def _messages_by_route(route: str, http, staff_: Staff, monkeypatch) -> list[dict[str, Any]]:
    if route == "get":
        return read_thread(http, staff_.conv_id)
    fake_chat_turn(monkeypatch)
    return post_chat(http, staff_).json()["messages"]


@pytest.mark.parametrize("route", ["get", "post"])
def test_a_trace_holder_reads_the_full_agent_turn(session_factory, monkeypatch, staff, grants, http, route):
    """Positive control for the strip: the same message, with the slug, still carries every field."""
    grants.add(SETTINGS_VIEW)
    message_id = _seed_trace_message(session_factory, staff)

    meta = message_of(_messages_by_route(route, http, staff, monkeypatch), message_id)["metadata_json"]

    for key in TRACE_KEYS:
        assert key in meta["agent"], f"the holder lost agent.{key}"
    assert meta["route_decision"]["reason"] == M_REASON and meta["route_decision"]["model"] == M_MODEL
    assert meta["chatbot_turn_id"]
    assert meta["route"] == "agent"


@pytest.mark.parametrize("route", ["get", "post"])
def test_a_reader_without_the_settings_slug_gets_only_the_card_and_the_route(
    session_factory, monkeypatch, staff, grants, http, route
):
    grants.add(NOTE_SLUG)
    message_id = _seed_trace_message(session_factory, staff)

    rows = _messages_by_route(route, http, staff, monkeypatch)

    meta = message_of(rows, message_id)["metadata_json"]
    assert set(meta["agent"]) == {"pending_action", "actions"}, sorted(meta["agent"])
    assert meta["agent"]["pending_action"] is not None, "the card itself must survive the strip"
    assert "route_decision" not in meta and "chatbot_turn_id" not in meta
    assert meta["route"] == "agent"
    raw = json.dumps(rows)
    for marker in (M_TOOL, M_STEP, str(M_USAGE), M_REPLY, M_REASON, M_MODEL):
        assert marker not in raw, f"{marker} reached a reader without {SETTINGS_VIEW}"
    for key in ("tool_calls", "usage", "rounds", "limit_hit", "reply_text", "route_decision", "chatbot_turn_id"):
        assert f'"{key}"' not in raw, f"{key} reached a reader without {SETTINGS_VIEW}"


# --------------------------------------------------------------------------- #
# 10 (AC-26): a message from the old path comes back untouched
# --------------------------------------------------------------------------- #

OLD_META = {
    "pending_confirmation": {"tool": "zzt_tool", "args": {"a": 1}},
    "trace_id": "ZZT-trace-old",
    "agent": {"steps": ["ZZT old"], "usage": {"total_tokens": 7}},  # not a brain reply: no route key
    "attachments": [{"filename": "old.pdf", "url": "https://files.example.invalid/old.pdf"}],
    "suggestions": ["Alpha"],
}


@pytest.mark.parametrize("holder", [True, False], ids=["trace-holder", "no-trace-slug"])
def test_an_old_path_message_is_returned_byte_identical_on_get(session_factory, staff, grants, http, holder):
    if holder:
        grants.add(SETTINGS_VIEW)
    db = session_factory()
    old = AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content="ZZT old reply", metadata_json=OLD_META, created_at=LONG_AGO)
    db.add(old)
    db.commit()
    # a brain reply in the same thread, so the strip and the live read are active around the old message
    seed_proposing_message(session_factory, staff)

    rows = read_thread(http, staff.conv_id)

    got = message_of(rows, str(old.id))["metadata_json"]
    assert json.dumps(got, sort_keys=True) == json.dumps(OLD_META, sort_keys=True)


def test_an_old_path_message_is_returned_byte_identical_on_post(session_factory, monkeypatch, staff, grants, http):
    db = session_factory()
    old = AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content="ZZT old reply", metadata_json=OLD_META, created_at=LONG_AGO)
    db.add(old)
    db.commit()
    seed_proposing_message(session_factory, staff)
    fake_chat_turn(monkeypatch)

    messages = post_chat(http, staff).json()["messages"]

    got = message_of(messages, str(old.id))["metadata_json"]
    assert json.dumps(got, sort_keys=True) == json.dumps(OLD_META, sort_keys=True)


# --------------------------------------------------------------------------- #
# 11: one query for the thread's actions, not one per message
# --------------------------------------------------------------------------- #


def _action_selects_for_thread(session_factory, staff_: Staff, http, turns: int) -> tuple[int, list[dict[str, Any]]]:
    """Seed `turns` agent replies that each proposed something, read the thread, and count the
    statements that read `agent_actions`."""
    ids = [seed_proposing_message(session_factory, staff_, status="cancelled", stored_pending=False)[2] for _ in range(turns)]
    seen: list[str] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        if "agent_actions" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    bind = session_factory().get_bind()
    event.listen(bind, "before_cursor_execute", spy)
    try:
        rows = read_thread(http, staff_.conv_id)
    finally:
        event.remove(bind, "before_cursor_execute", spy)
    live = [message_of(rows, i)["metadata_json"]["agent"]["actions"] for i in ids]
    assert all(len(a) == 1 and a[0]["status"] == "cancelled" for a in live), "the thread did not read its cards live"
    return len(seen), rows


def test_a_thread_of_many_agent_turns_reads_its_actions_in_a_fixed_number_of_queries(session_factory, staff, grants, http):
    one, _ = _action_selects_for_thread(session_factory, staff, http, 1)
    many_staff = seed_staff(session_factory)
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": many_staff.user_id, "name": "ZZT"}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": many_staff.user_id, "name": "ZZT"}
    many, _ = _action_selects_for_thread(session_factory, many_staff, http, 5)

    assert one >= 1, "the read never asked the action store"
    assert many == one, f"{one} statement(s) for 1 agent turn but {many} for 5: a query per message"
    assert many <= 3
