"""AGENTIC-P2-ROUTE: the console runs the side the router picks (UAC S1-S4, V1, V2).

Red tests, written before the console wiring exists. `POST /console/turn` for an eligible
contact; `jev_client.classify` and `run_agent_turn` are monkeypatched, the bot side runs the
real engine with the parser stubbed (same seams as `test_console_turn_endpoint.py`).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import console_service
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.agent.test_router import (  # noqa: F401 - helpers
    FakeJev,
    arm,
    jev_answer,
    seed_proposal,
)
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures
    CONSOLE_TURN_URL,
    NOT_SUPPORTED_OUTPUT,
    NOT_SUPPORTED_REPLY,
    _ACTOR,
    _permissions,
    _run_id,
    client,
    seeded_contact_with_a_prior_turn,
    stub_console_seams,
)
from tests.chatbot.test_engine import CONTACT_ID

AGENT_REPLY = "Selangor fell because two dealers paused orders."


@pytest.fixture()
def eligible(seeded_contact_with_a_prior_turn, system_settings_row):  # noqa: F811
    """The prior-turn contact, switched on and linked to an active user, with the Jev key and
    router prompt in place."""
    db = seeded_contact_with_a_prior_turn
    pk = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).scalar()
    db.execute(
        text("UPDATE respond_contacts SET chatbot_allowed = true, chatbot_agent_enabled = true WHERE id = :i"),
        {"i": pk},
    )
    user_id = seed_user(db, contact_pk=pk)
    db.commit()
    arm(db)
    return {"db": db, "pk": pk, "user_id": user_id, "respond_id": str(CONTACT_ID)}


@pytest.fixture()
def jev(monkeypatch):
    from app.services.chatbot import jev_client

    fake = FakeJev()
    monkeypatch.setattr(jev_client, "classify", fake)
    return fake


@pytest.fixture()
def agent_calls(monkeypatch):
    """Replace `run_agent_turn` wherever the console may have bound it."""
    from app.services.chatbot.agent import loop
    from app.services.chatbot.agent.loop import AgentTurnResult

    calls: list[dict] = []

    def fake(db, **kwargs):
        calls.append(kwargs)
        if fake.error is not None:
            raise fake.error
        return AgentTurnResult(
            "agent-turn-1", "conv-1", AGENT_REPLY, "answered", None, 2,
            {"prompt_tokens": 10, "completion_tokens": 5, "cached_tokens": 0, "calls": 1}, [],
        )

    fake.error = None
    monkeypatch.setattr(loop, "run_agent_turn", fake)
    monkeypatch.setattr(console_service, "run_agent_turn", fake, raising=False)
    fake.calls = calls
    return fake


@pytest.fixture()
def bot_parser(monkeypatch):
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)


def _post(client, eligible, text_="why did Selangor sales drop", **extra):
    body = {"contact_respond_id": eligible["respond_id"], "text": text_, "run_id": _run_id()}
    body.update(extra)
    return client.post(CONSOLE_TURN_URL, json=body)


def _bot_reply_in(body):
    return NOT_SUPPORTED_REPLY in body["reply_text"] or any(NOT_SUPPORTED_REPLY in m for m in body["send_messages"])


# ------------------------------------------------------------------ S2: agent side


def test_S2_agent_choice_runs_the_agent_with_the_operator_and_text(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    jev.answer = jev_answer("agent", 0.92)
    resp = _post(client, eligible, "why did Selangor sales drop")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(agent_calls.calls) == 1
    call = agent_calls.calls[0]
    assert call["contact_respond_id"] == eligible["respond_id"]
    assert call["text"] == "why did Selangor sales drop"
    assert call["operator_user_id"] == _ACTOR["id"]
    assert body["route"]["side"] == "agent"
    assert body["route"]["reason"] == "classified"
    assert body["route"]["score"] == pytest.approx(0.92)
    assert body["route"]["model"] == "jev-1.14.0"
    assert body["reply_text"] == AGENT_REPLY
    assert body["agent"]["status"] == "answered"
    assert body["agent"]["pending_action"] is None
    assert not _bot_reply_in(body)


def test_S2_a_pending_proposal_reaches_the_agent_without_a_jev_call(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    seed_proposal(eligible["db"], {"respond_id": eligible["respond_id"], "user_id": eligible["user_id"]})
    resp = _post(client, eligible, "yes")
    assert resp.status_code == 200, resp.text
    assert resp.json()["route"]["reason"] == "pending_action"
    assert jev.calls == []
    assert len(agent_calls.calls) == 1


# ------------------------------------------------------------------ S1: chat side


def test_S1_chat_choice_runs_the_engine_as_today(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    jev.answer = jev_answer("chat", 0.95)
    resp = _post(client, eligible, "can I submit a goods receive here")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["side"] == "chat"
    assert body["route"]["reason"] == "classified"
    assert body["branch_kind"] == "not_supported"
    assert _bot_reply_in(body)
    assert agent_calls.calls == []
    row = eligible["db"].query(ChatbotTurn).filter(ChatbotTurn.id == body["turn_id"]).one()
    assert row.ingress == "console"


def test_S1_a_not_eligible_contact_still_gets_the_bot_with_a_route_record(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    eligible["db"].execute(
        text("UPDATE respond_contacts SET chatbot_agent_enabled = false WHERE id = :i"), {"i": eligible["pk"]}
    )
    eligible["db"].commit()
    resp = _post(client, eligible, "can I submit a goods receive here")
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert body["route"]["side"] == "chat"
    assert body["route"]["reason"] == "not_eligible:switch_off"
    assert jev.calls == [] and agent_calls.calls == []
    assert _bot_reply_in(body)


def test_R7_a_jev_failure_still_answers_from_the_bot(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    from app.services.chatbot.jev_client import JevError

    jev.error = JevError("timeout")
    resp = _post(client, eligible, "can I submit a goods receive here")
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert body["route"]["reason"] == "router_failed:timeout"
    assert _bot_reply_in(body)
    assert agent_calls.calls == []


def test_R4_an_open_question_in_session_vars_keeps_the_turn_on_the_bot(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    from tests.chatbot.agent.test_router import OPEN_QUESTION_VARS

    resp = _post(client, eligible, "1", session_vars=OPEN_QUESTION_VARS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["route"]["reason"] == "open_question"
    assert jev.calls == [] and agent_calls.calls == []


# ------------------------------------------------------------------ media: no Jev call


def test_R2_a_media_turn_makes_no_jev_call(client, eligible, jev, agent_calls, monkeypatch):
    seen = []

    def fake_media(db, **kwargs):
        seen.append(kwargs)
        return console_service.ConsoleTurnResult(
            turn_id=None, reply_text="", quick_replies=[], send_messages=[], trace_summary={},
            media_status="pending",
        )

    monkeypatch.setattr(console_service, "_run_console_media_turn", fake_media)
    resp = _post(
        client, eligible, "look at this",
        media={"kind": "image", "filename": "a.png", "mime": "image/png", "content_base64": "aGk="},
    )
    assert resp.status_code == 200, resp.text
    assert len(seen) == 1
    assert jev.calls == [] and agent_calls.calls == []


# ------------------------------------------------------------------ S3: busy / failed


def test_S3_a_busy_agent_says_so_and_the_bot_does_not_run(
    client, eligible, jev, agent_calls, stub_console_seams, monkeypatch,
):
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.agent.loop import AgentBusy

    engine_calls = []
    monkeypatch.setattr(console_service, "run_turn", lambda *a, **k: engine_calls.append(1), raising=False)
    monkeypatch.setattr(engine_mod, "run_turn", lambda *a, **k: engine_calls.append(1))
    agent_calls.error = AgentBusy()
    jev.answer = jev_answer("agent", 0.9)
    resp = _post(client, eligible, "why did Selangor sales drop")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["side"] == "agent"
    assert body["reply_text"] == console_service.AGENT_BUSY_REPLY
    assert "busy" not in body["reply_text"].lower()  # NO-SORRY-COPY owner rule
    assert engine_calls == []


def test_S3_a_failing_agent_says_so_and_the_bot_does_not_run(
    client, eligible, jev, agent_calls, stub_console_seams, monkeypatch,
):
    from app.services.chatbot import engine as engine_mod

    engine_calls = []
    monkeypatch.setattr(console_service, "run_turn", lambda *a, **k: engine_calls.append(1), raising=False)
    monkeypatch.setattr(engine_mod, "run_turn", lambda *a, **k: engine_calls.append(1))
    agent_calls.error = RuntimeError("boom")
    jev.answer = jev_answer("agent", 0.9)
    resp = _post(client, eligible, "why did Selangor sales drop")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"]["side"] == "agent"
    assert body["reply_text"]
    assert engine_calls == []


# ------------------------------------------------------------------ S4: operator rate limit


def test_S4_routed_agent_turns_hit_the_operator_agent_rate_limit(
    client, eligible, jev, agent_calls, stub_console_seams, monkeypatch,
):
    from app.services import rate_limit

    seen = {}

    def fake_hit(bucket, ident, *, limit, window_seconds):
        if bucket == "agent_turn":
            seen.update(bucket=bucket, ident=ident, limit=limit, window=window_seconds)
            return rate_limit.RateResult(allowed=False, retry_after_seconds=120)
        return rate_limit.RateResult(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(rate_limit, "hit", fake_hit)
    jev.answer = jev_answer("agent", 0.9)
    resp = _post(client, eligible, "why did Selangor sales drop")
    assert resp.status_code == 429
    assert seen["ident"] == _ACTOR["id"] and seen["limit"] == 30 and seen["window"] == 600
    assert agent_calls.calls == []


def test_S4_chat_routed_turns_do_not_spend_the_agent_limit(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser, monkeypatch,
):
    from app.services import rate_limit

    buckets = []

    def fake_hit(bucket, ident, *, limit, window_seconds):
        buckets.append(bucket)
        return rate_limit.RateResult(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(rate_limit, "hit", fake_hit)
    jev.answer = jev_answer("chat", 0.95)
    resp = _post(client, eligible, "can I submit a goods receive here")
    assert resp.status_code == 200, resp.text
    assert "agent_turn" not in buckets


# ------------------------------------------------------------------ V1 / V2


def test_V1_the_route_is_in_the_response_and_the_turn_trace(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    jev.answer = jev_answer("chat", 0.88)
    resp = _post(client, eligible, "can I submit a goods receive here")
    body = resp.json()
    assert set(body["route"]) >= {"side", "reason", "score", "model", "ms"}
    row = eligible["db"].query(ChatbotTurn).filter(ChatbotTurn.id == body["turn_id"]).one()
    stages = [s for s in (row.trace or []) if s.get("stage") == "route"]
    assert stages, "the turn trace holds a route record"
    assert "classified" in str(stages[0]) and "chat" in str(stages[0])


def test_V2_the_usage_row_is_tied_to_the_chat_turn(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    from app.models.ai_assistant import AIAssistantUsageLog

    jev.answer = jev_answer("chat", 0.95, input_tokens=555)
    body = _post(client, eligible, "can I submit a goods receive here").json()
    rows = eligible["db"].query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").all()
    assert len(rows) == 1
    assert rows[0].chatbot_turn_id == body["turn_id"]
    assert rows[0].provider == "typesafe" and rows[0].prompt_tokens == 555


def test_V2_the_usage_row_is_tied_to_the_agent_turn(
    client, eligible, jev, agent_calls, stub_console_seams, bot_parser,
):
    from app.models.ai_assistant import AIAssistantUsageLog

    jev.answer = jev_answer("agent", 0.95, input_tokens=555)
    body = _post(client, eligible, "why did Selangor sales drop").json()
    rows = eligible["db"].query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").all()
    assert len(rows) == 1
    assert rows[0].chatbot_turn_id == body["agent"]["turn_id"] == "agent-turn-1"
