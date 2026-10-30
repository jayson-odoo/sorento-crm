"""AGENTIC-P2 slice 1: `app.services.chatbot.router` (plan "Design" 2 and 3, "Build contract").

State rules decide before any Jev call, in this order: pending agent proposal, open bot question,
media, daily cap. Everything else asks Jev. A fake Jev (the `jev=` parameter) records each call.
Postgres blank schema; every test seeds its own contact chain.

Assumptions the contract leaves open (flagged in the tester report):
- `history` is a list of dicts `{"text", "reply", "answered_by": "agent" | "bot"}`, oldest first.
- `jev=` has the signature of `jev_client.choose` and returns its dict.
- A clear "chat" verdict (P(agent) below 0.5) carries reason `jev`.
- The daily count ignores `chatbot.turns.is_test` (the console writes is_test turns).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact

KEY = "ZZT-jev-env-key-0001"
NOW = datetime(2026, 10, 30, 2, 0, tzinfo=timezone.utc)  # 10:00 in Malaysia (UTC+8)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _env_key(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    monkeypatch.delenv("JEV_BASE_URL", raising=False)


class FakeJev:
    """Stands in for `jev_client.choose`; records every call."""

    def __init__(self, p_agent: float = 0.9, exc: Exception | None = None, tokens: int = 120):
        self.p_agent = p_agent
        self.exc = exc
        self.tokens = tokens
        self.calls: list[dict] = []

    def __call__(self, *args, **kw):
        key = args[0] if args else kw.get("key")
        self.calls.append(dict(kw, key=key))
        if self.exc is not None:
            raise self.exc
        agent = self.p_agent
        return {
            "choice": "agent" if agent >= 0.5 else "chat",
            "confidence": max(agent, 1 - agent),
            "probabilities": {"chat": 1 - agent, "agent": agent},
            "input_tokens": self.tokens,
            "output_tokens": 3,
        }


def _ctx(db, contact):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, contact["respond_id"])


def _decide(db, contact, jev, *, text_="how did Penang do vs last quarter?", history=(), has_media=False, now=NOW):
    from app.services.chatbot import router

    return router.decide(db, _ctx(db, contact), text_, history=list(history), has_media=has_media, now=now, jev=jev)


def _set_vars(db, contact, session_vars):
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
        {"sv": json.dumps(session_vars), "id": contact["pk"]},
    )
    db.flush()


OPEN_QUESTION = {
    "open_question": {
        "kind": "outstanding_detail", "options": [], "expects": None, "team": None,
        "asked_at_turn": 3, "payload": {},
    },
    "focus": {"customers": []}, "ideation": None, "access_levels": [], "contains_flyer": False,
}


def _propose(db, contact):
    from app.services.chatbot.agent import actions

    ctx = _ctx(db, contact)
    return actions.store_proposal(
        db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        steps=[{"summary": "Mark ask done"}],
    )


def _turns(db, respond_id, n, at, *, ingress="agent"):
    from app.models.chatbot_turn import ChatbotTurn

    for _ in range(n):
        db.add(ChatbotTurn(
            id=str(uuid.uuid4()), contact_respond_id=respond_id, ingress=ingress, is_test=True,
            status="done", envelope={"text": "x"}, response={"reply_text": "y"}, created_at=at,
        ))
    db.flush()


def _setting(db, **cols):
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT router co", **cols))
    db.flush()


def _override(db, contact, value):
    db.execute(
        text("UPDATE respond_contacts SET chatbot_agent_daily_turns = :v WHERE id = :id"),
        {"v": value, "id": contact["pk"]},
    )
    db.flush()


def _usage_rows(db):
    from app.models.ai_assistant import AIAssistantUsageLog

    return db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").all()


# ------------------------------------------------------------------ the shape


def test_a_decision_carries_the_contract_fields(db):
    c = seed_agent_contact(db)
    jev = FakeJev(0.9)
    d = _decide(db, c, jev)
    assert d.route == "agent" and d.reason == "jev"
    assert d.score == pytest.approx(0.9)
    assert d.provider == "jev"
    assert d.tokens_in == 120
    assert isinstance(d.ms, int) and d.ms >= 0
    assert len(jev.calls) == 1


# ------------------------------------------------------------------ state rules (no Jev call)


def test_a_pending_proposal_routes_to_agent_without_jev(db):
    c = seed_agent_contact(db)
    _propose(db, c)
    jev = FakeJev(0.0)
    d = _decide(db, c, jev, text_="yes")
    assert (d.route, d.reason) == ("agent", "pending_action")
    assert jev.calls == []
    assert _usage_rows(db) == []


def test_without_a_proposal_the_same_message_asks_jev(db):  # positive control for the rule above
    c = seed_agent_contact(db)
    jev = FakeJev(0.0)
    d = _decide(db, c, jev, text_="yes")
    assert (d.route, d.reason) == ("chat", "jev")
    assert len(jev.calls) == 1


def test_an_open_bot_question_routes_to_chat_without_jev(db):
    c = seed_agent_contact(db)
    _set_vars(db, c, OPEN_QUESTION)
    jev = FakeJev(0.99)
    d = _decide(db, c, jev, text_="the second one")
    assert (d.route, d.reason) == ("chat", "open_question")
    assert jev.calls == []


def test_an_empty_session_has_no_open_question(db):  # positive control
    c = seed_agent_contact(db)
    _set_vars(db, c, {"open_question": None, "focus": {"customers": []}})
    jev = FakeJev(0.99)
    d = _decide(db, c, jev, text_="the second one")
    assert (d.route, d.reason) == ("agent", "jev")
    assert len(jev.calls) == 1


def test_media_routes_to_chat_without_jev(db):
    c = seed_agent_contact(db)
    jev = FakeJev(0.99)
    d = _decide(db, c, jev, has_media=True)
    assert (d.route, d.reason) == ("chat", "media")
    assert jev.calls == []


def test_no_media_asks_jev(db):  # positive control
    c = seed_agent_contact(db)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev, has_media=False).reason == "jev"
    assert len(jev.calls) == 1


@pytest.mark.parametrize(
    "pending, question, media, expected",
    [
        (True, True, True, "pending_action"),
        (False, True, True, "open_question"),
        (False, False, True, "media"),
    ],
)
def test_state_rules_apply_in_order_even_at_the_cap(db, pending, question, media, expected):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=1)
    _turns(db, c["respond_id"], 1, NOW)
    if pending:
        _propose(db, c)
    if question:
        _set_vars(db, c, OPEN_QUESTION)
    jev = FakeJev(0.99)
    d = _decide(db, c, jev, has_media=media)
    assert d.reason == expected
    assert jev.calls == []


# ------------------------------------------------------------------ daily cap


def test_the_default_cap_is_50_agent_turns(db):
    c = seed_agent_contact(db)
    _turns(db, c["respond_id"], 49, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"  # 49 used, one left
    _turns(db, c["respond_id"], 1, NOW)
    d = _decide(db, c, jev)
    assert (d.route, d.reason) == ("chat", "daily_cap")
    assert len(jev.calls) == 1  # only the first decision called Jev


def test_the_global_setting_sets_the_cap(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=3)
    _turns(db, c["respond_id"], 2, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"
    _turns(db, c["respond_id"], 1, NOW)
    assert _decide(db, c, jev).reason == "daily_cap"
    assert len(jev.calls) == 1


def test_a_global_cap_of_zero_means_no_cap(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=0)
    _turns(db, c["respond_id"], 120, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"
    assert len(jev.calls) == 1


def test_the_contact_override_beats_a_higher_global_value(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=50)
    _override(db, c, 2)
    _turns(db, c["respond_id"], 2, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "daily_cap"
    assert jev.calls == []


def test_the_contact_override_beats_a_lower_global_value(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=2)
    _override(db, c, 100)
    _turns(db, c["respond_id"], 5, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"
    assert len(jev.calls) == 1


def test_a_contact_override_of_zero_means_no_cap_for_that_contact(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=2)
    _override(db, c, 0)
    _turns(db, c["respond_id"], 5, NOW)
    assert _decide(db, c, FakeJev(0.99)).reason == "jev"


def test_the_day_starts_at_midnight_in_malaysia(db):
    # NOW is 2026-10-30 10:00 MYT. 15:30 UTC on the 29th is 23:30 MYT on the 29th: yesterday.
    c = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=2)
    _turns(db, c["respond_id"], 2, datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc))
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"
    # 16:30 UTC on the 29th is 00:30 MYT on the 30th: today.
    _turns(db, c["respond_id"], 2, datetime(2026, 10, 29, 16, 30, tzinfo=timezone.utc))
    assert _decide(db, c, jev).reason == "daily_cap"
    assert len(jev.calls) == 1


def test_only_agent_turns_of_this_contact_count(db):
    c = seed_agent_contact(db)
    other = seed_agent_contact(db)
    _setting(db, chatbot_agent_daily_turns=2)
    _turns(db, c["respond_id"], 5, NOW, ingress="webhook")
    _turns(db, other["respond_id"], 5, NOW)
    jev = FakeJev(0.99)
    assert _decide(db, c, jev).reason == "jev"
    assert len(jev.calls) == 1
    _turns(db, c["respond_id"], 2, NOW)
    assert _decide(db, c, jev).reason == "daily_cap"


# ------------------------------------------------------------------ Jev verdict


def test_score_at_the_default_threshold_routes_to_agent(db):
    c = seed_agent_contact(db)
    d = _decide(db, c, FakeJev(0.7))
    assert (d.route, d.reason) == ("agent", "jev")


def test_score_below_the_threshold_is_low_confidence_and_goes_to_chat(db):
    c = seed_agent_contact(db)
    d = _decide(db, c, FakeJev(0.6))
    assert (d.route, d.reason) == ("chat", "low_confidence")
    assert d.score == pytest.approx(0.6)


def test_a_clear_chat_verdict_is_chat_with_reason_jev(db):
    c = seed_agent_contact(db)
    d = _decide(db, c, FakeJev(0.1))
    assert (d.route, d.reason) == ("chat", "jev")


def test_the_threshold_is_the_system_setting(db):
    c = seed_agent_contact(db)
    _setting(db, chatbot_router_min_score=0.9)
    assert _decide(db, c, FakeJev(0.8)).reason == "low_confidence"
    assert _decide(db, c, FakeJev(0.9)).route == "agent"


@pytest.mark.parametrize("exc_name", ["JevError", "timeout"])
def test_a_jev_failure_routes_to_chat_as_router_failed(db, exc_name):
    import httpx

    from app.services.chatbot import jev_client

    exc = jev_client.JevError("boom") if exc_name == "JevError" else httpx.ReadTimeout("slow")
    c = seed_agent_contact(db)
    jev = FakeJev(exc=exc)
    d = _decide(db, c, jev)
    assert (d.route, d.reason) == ("chat", "router_failed")
    assert len(jev.calls) == 1


def test_the_jev_request_carries_the_message_the_last_three_exchanges_and_who_answered(db):
    c = seed_agent_contact(db)
    history = [
        {"text": "OLDEST-Q", "reply": "OLDEST-A", "answered_by": "bot"},
        {"text": "SECOND-Q", "reply": "SECOND-A", "answered_by": "bot"},
        {"text": "THIRD-Q", "reply": "THIRD-A", "answered_by": "bot"},
        {"text": "LATEST-Q", "reply": "LATEST-A", "answered_by": "agent"},
    ]
    jev = FakeJev(0.9)
    _decide(db, c, jev, text_="NEW-MESSAGE-TEXT", history=history)
    call = jev.calls[0]
    state = call["state"]
    assert "NEW-MESSAGE-TEXT" in state
    for kept in ("SECOND-Q", "THIRD-Q", "LATEST-Q"):
        assert kept in state
    assert "OLDEST-Q" not in state
    assert "last answered by: agent" in state
    assert set(call["criteria"]) == {"chat", "agent"}
    assert all(isinstance(v, str) and v.strip() for v in call["criteria"].values())
    assert isinstance(call["instructions"], str) and call["instructions"].strip()
    assert call.get("model", "jev-latest") == "jev-latest"
    assert call.get("timeout", 1.5) == 1.5


def test_a_call_logs_one_usage_row(db):
    c = seed_agent_contact(db)
    _decide(db, c, FakeJev(0.9, tokens=120))
    rows = _usage_rows(db)
    assert len(rows) == 1
    assert rows[0].prompt_tokens == 120
    assert rows[0].provider == "jev"
    assert rows[0].contact_id == c["pk"]


# ------------------------------------------------------------------ key resolution


def _set_column_key(db, key):
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    AIAssistantConfigService(db).update(
        AIAssistantConfigUpdate(
            provider="openai", model="gpt-4o-mini", temperature=0, system_prompt="",
            enabled_tools=[], rag_enabled=True, is_enabled=True, jev_api_key=key,
        ),
        user_id=None,
    )


def test_the_column_key_wins_over_the_env_key(db):
    from app.services.chatbot import router

    _set_column_key(db, "ZZT-jev-column-key-9999")
    assert router.jev_key(db) == "ZZT-jev-column-key-9999"
    c = seed_agent_contact(db)
    jev = FakeJev(0.9)
    _decide(db, c, jev)
    assert jev.calls[0]["key"] == "ZZT-jev-column-key-9999"


def test_the_env_key_is_used_when_the_column_is_empty(db):
    from app.services.chatbot import router

    assert router.jev_key(db) == KEY
    c = seed_agent_contact(db)
    jev = FakeJev(0.9)
    _decide(db, c, jev)
    assert jev.calls[0]["key"] == KEY


def test_no_key_anywhere_is_router_failed_without_a_call(db, monkeypatch):
    from app.services.chatbot import router

    monkeypatch.delenv("JEV_API_KEY", raising=False)
    assert not router.jev_key(db)
    c = seed_agent_contact(db)
    jev = FakeJev(0.9)
    d = _decide(db, c, jev)
    assert (d.route, d.reason) == ("chat", "router_failed")
    assert jev.calls == []


def test_a_state_rule_does_not_need_a_key(db, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    c = seed_agent_contact(db)
    d = _decide(db, c, FakeJev(0.9), has_media=True)
    assert d.reason == "media"
