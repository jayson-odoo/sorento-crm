"""AGENTIC-P2 slice 1 (plan section 4): `POST /api/v1/system/chatbot/console/auto-turn`.

Same auth harness as the agent routes (`system.chat_history.view`, `check_user_has_permission`
monkeypatched). The console turn and `run_agent_turn` are replaced with recorders; Jev is replaced
at `jev_client.choose` (and the router's own binding of it, if any). Contacts, users and the
linked-user chain are real rows on the blank schema.

Assumptions flagged in the report: the request needs only `contact_respond_id` and `text` (no
`run_id`); a Jev stub installed at `jev_client.choose` is what `router.decide` calls by default.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent._seed import seed_agent_contact, seed_contact
from tests.chatbot.agent.test_agent_routes import _result
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures + helpers
    VIEW,
    _GRANTS,
    _permissions,
    client,
)
from tests.chatbot.test_router import FakeJev

URL = "/api/v1/system/chatbot/console/auto-turn"
KEY = "ZZT-jev-env-key-0002"


@pytest.fixture(autouse=True)
def _env_key(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    monkeypatch.delenv("JEV_BASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _router_on(session_factory):
    """J3: routing is off by default; these tests are about the routed paths."""
    import uuid

    from app.models.user import SystemSetting

    db = session_factory()
    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT router on", chatbot_router_enabled=True))
    db.commit()


@pytest.fixture()
def jev(monkeypatch):
    from app.services.chatbot import jev_client, router

    fake = FakeJev(0.9)
    monkeypatch.setattr(jev_client, "choose", fake)
    monkeypatch.setattr(router, "choose", fake, raising=False)
    return fake


@pytest.fixture()
def turns(monkeypatch):
    """Recorders for both sides. `turns.bot` and `turns.agent` are the call logs."""
    import app.api.v1.system.chatbot as route_mod
    import app.services.chatbot.agent.loop as loop_mod
    from app.services.chatbot import console_service
    from app.services.chatbot.console_service import ConsoleTurnResult

    class Box:
        bot: list[dict] = []
        agent: list[dict] = []
        agent_exc: Exception | None = None

    box = Box()
    box.bot, box.agent = [], []

    def fake_bot(db, **kw):
        box.bot.append(kw)
        return ConsoleTurnResult(
            turn_id="33333333-3333-3333-3333-333333333333", branch_kind="business_query",
            reply_text="BOT-REPLY", quick_replies=[], send_messages=[], session_vars={}, trace_summary={},
        )

    def fake_agent(db, **kw):
        box.agent.append(kw)
        if box.agent_exc is not None:
            raise box.agent_exc
        return _result(reply_text="AGENT-REPLY")

    monkeypatch.setattr(console_service, "run_console_turn", fake_bot)
    monkeypatch.setattr(loop_mod, "run_agent_turn", fake_agent)
    monkeypatch.setattr(route_mod, "run_agent_turn", fake_agent, raising=False)
    return box


def _contact(session_factory):
    db = session_factory()
    contact = seed_agent_contact(db)
    db.commit()
    return contact


def _post(client, contact, text_="compare Penang and Johor sales this quarter"):
    return client.post(URL, json={"contact_respond_id": contact["respond_id"], "text": text_})


def test_an_agent_verdict_runs_the_agent_and_returns_its_turn(client, session_factory, jev, turns):
    contact = _contact(session_factory)
    resp = _post(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["route"] == "agent"
    assert body["route"]["reason"] == "jev"
    assert body["route"]["score"] == pytest.approx(0.9)
    assert body["route"]["provider"] == "jev"
    assert body["route"]["tokens_in"] == 120
    assert isinstance(body["route"]["ms"], int)
    assert body["turn"]["reply_text"] == "AGENT-REPLY"
    assert body["turn"]["conversation_id"] == "22222222-2222-2222-2222-222222222222"
    assert turns.bot == []
    assert turns.agent[0]["contact_respond_id"] == contact["respond_id"]
    assert turns.agent[0]["text"] == "compare Penang and Johor sales this quarter"
    assert len(jev.calls) == 1


def test_a_chat_verdict_runs_the_console_turn_and_returns_it(client, session_factory, jev, turns):
    contact = _contact(session_factory)
    jev.p_agent = 0.1
    resp = _post(client, contact, "stock of SRTWT7445?")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["route"] == "chat"
    assert body["turn"]["reply_text"] == "BOT-REPLY"
    assert body["turn"]["branch_kind"] == "business_query"
    assert turns.agent == []
    assert turns.bot[0]["contact_respond_id"] == contact["respond_id"]
    assert turns.bot[0]["text"] == "stock of SRTWT7445?"


def test_low_confidence_goes_to_the_bot_and_says_why(client, session_factory, jev, turns):
    contact = _contact(session_factory)
    jev.p_agent = 0.6
    body = _post(client, contact).json()
    assert body["route"]["route"] == "chat" and body["route"]["reason"] == "low_confidence"
    assert body["turn"]["reply_text"] == "BOT-REPLY"
    assert turns.agent == []


def test_a_jev_failure_goes_to_the_bot_and_says_so(client, session_factory, jev, turns):
    from app.services.chatbot import jev_client

    contact = _contact(session_factory)
    jev.exc = jev_client.JevError("down")
    body = _post(client, contact).json()
    assert body["route"]["route"] == "chat" and body["route"]["reason"] == "router_failed"
    assert body["turn"]["reply_text"] == "BOT-REPLY"
    assert turns.agent == []


def test_a_pending_proposal_runs_the_agent_without_jev(client, session_factory, jev, turns):
    from tests.chatbot.test_router import _propose

    db = session_factory()
    contact = seed_agent_contact(db)
    _propose(db, contact)
    db.commit()
    jev.p_agent = 0.0
    body = _post(client, contact, "yes").json()
    assert body["route"]["route"] == "agent" and body["route"]["reason"] == "pending_action"
    assert jev.calls == []
    assert len(turns.agent) == 1


@pytest.mark.parametrize("kind", ["switch_off", "ai_replies_off", "no_linked_user"])
def test_a_contact_that_cannot_use_the_agent_never_meets_the_router(client, session_factory, jev, turns, kind):
    from tests.chatbot.agent._seed import seed_user

    db = session_factory()
    if kind == "switch_off":
        contact = seed_contact(db, agent_enabled=False)
        seed_user(db, contact_pk=contact["pk"])
    elif kind == "ai_replies_off":
        contact = seed_contact(db, chatbot_allowed=False)
        seed_user(db, contact_pk=contact["pk"])
    else:
        contact = seed_contact(db)
    db.commit()
    resp = _post(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["route"] == "chat"
    assert body["turn"]["reply_text"] == "BOT-REPLY"
    assert jev.calls == []
    assert turns.agent == []
    assert len(turns.bot) == 1


def test_an_agent_failure_is_not_re_run_on_the_bot(client, session_factory, jev, turns):
    from app.services.chatbot.agent.loop import AgentBusy

    contact = _contact(session_factory)
    turns.agent_exc = AgentBusy()
    resp = _post(client, contact)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {"code": "agent_busy"}
    assert turns.bot == []


def test_the_key_is_not_in_the_response(client, session_factory, jev, turns):
    contact = _contact(session_factory)
    assert KEY not in _post(client, contact).text


def test_without_the_view_permission_is_403_and_nothing_runs(client, session_factory, jev, turns):
    contact = _contact(session_factory)
    _GRANTS.discard(VIEW)
    resp = _post(client, contact)
    assert resp.status_code == 403
    assert jev.calls == [] and turns.bot == [] and turns.agent == []


@pytest.mark.parametrize(
    "body",
    [
        {"contact_respond_id": "ZZT-C1", "text": ""},
        {"contact_respond_id": "ZZT-C1", "text": "x" * 4001},
        {"contact_respond_id": "ZZT-C1"},
        {"text": "x"},
    ],
)
def test_the_body_is_validated(client, jev, turns, body):
    assert client.post(URL, json=body).status_code == 422
    assert jev.calls == [] and turns.bot == [] and turns.agent == []
