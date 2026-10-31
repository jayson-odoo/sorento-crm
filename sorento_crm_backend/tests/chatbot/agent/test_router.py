"""AGENTIC-P2-ROUTE: the router's decision table (UAC R1-R10, V2, K4, S5).

Red tests, written before `app/services/chatbot/router.py` and `jev_client.py` exist. The Jev
call is always a monkeypatched `jev_client.classify`; no test touches the network. Postgres
only, through the blank schema; every test seeds its own contact chain.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.chatbot_agent import AgentAction
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user

MYT = ZoneInfo("Asia/Kuala_Lumpur")
JEV_KEY = "ZZT-jev-secret-key-9876"
JEV_MODEL = "jev-1.14.0"
INSTRUCTIONS = "Pick the side that should answer this message."
CRITERIA = {"chat": "single lookups the bot intents answer", "agent": "several reads combined, why, analysis"}

OPEN_QUESTION_VARS = {
    "focus": {"customers": []},
    "open_question": {
        "kind": "customer_pick",
        "options": [
            {"position": 1, "label": "Customer A", "entity_type": "customer"},
            {"position": 2, "label": "Customer B", "entity_type": "customer"},
        ],
        "expects": "pick",
        "team": None,
        "asked_at_turn": 5,
        "payload": {},
    },
    "ideation": None,
    "access_levels": [],
    "contains_flyer": False,
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _fresh_prompt_cache():
    from app.services import ai_prompt_registry

    ai_prompt_registry._CACHE.clear()
    yield
    ai_prompt_registry._CACHE.clear()


# ------------------------------------------------------------------ seeding helpers


def jev_answer(choice="agent", confidence=0.9, input_tokens=700, output_tokens=0, model=JEV_MODEL):
    from app.services.chatbot.jev_client import JevAnswer

    other = "chat" if choice == "agent" else "agent"
    return JevAnswer(
        choice=choice,
        confidence=confidence,
        probabilities={choice: confidence, other: round(1 - confidence, 4)},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )


class FakeJev:
    """A stand-in for `jev_client.classify` that records every call."""

    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, api_key, **kwargs):
        self.calls.append({"api_key": api_key, **kwargs})
        if self.error is not None:
            raise self.error
        return self.answer if self.answer is not None else jev_answer()


@pytest.fixture()
def jev(monkeypatch):
    from app.services.chatbot import jev_client

    fake = FakeJev()
    monkeypatch.setattr(jev_client, "classify", fake)
    return fake


def set_jev_key(db, key=JEV_KEY):
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    AIAssistantConfigService(db).update(
        AIAssistantConfigUpdate(
            provider="gemini", model="gemini-2.5-flash", temperature=0, system_prompt="",
            enabled_tools=[], rag_enabled=True, is_enabled=True, typesafe_api_key=key,
        ),
        user_id=None,
    )
    db.commit()


def publish_router_prompt(db, *, model=JEV_MODEL, content=None):
    body = content if content is not None else {"instructions": INSTRUCTIONS, "criteria": CRITERIA}
    version = AIPromptVersion(
        name="chatbot_router", version=1, template=json.dumps(body), variables=[],
    )
    db.add(version)
    db.flush()
    db.add(
        AIPromptLabel(
            name="chatbot_router", label="production", version_id=version.id,
            provider="typesafe", model=model,
        )
    )
    db.commit()


def arm(db):
    """Key and production prompt both present: the router may reach Jev."""
    set_jev_key(db)
    publish_router_prompt(db)


def set_settings(db, **columns):
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=str(uuid.uuid4()), name="ZZT router co")
        db.add(row)
    for key, value in columns.items():
        setattr(row, key, value)
    db.commit()


def seed_agent_turn(db, respond_id, *, created_at, ingress="agent", text_="q", reply="a", answered_by=None):
    row = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=respond_id,
        ingress=ingress,
        is_test=True,
        status="done",
        envelope={"text": text_},
        response={"reply_text": reply, "status": "answered"},
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def route(db, respond_id, text_="why did sales drop in Selangor", *, session_vars=None, has_media=False):
    from app.services.chatbot.router import decide_route

    return decide_route(
        db, contact_respond_id=respond_id, text=text_, session_vars=session_vars, has_media=has_media,
    )


# ------------------------------------------------------------------ R1: eligibility


def test_R1_unknown_contact_goes_to_chat_without_a_jev_call(db, jev):
    decision = route(db, unique_code("nobody"))
    assert (decision.side, decision.reason) == ("chat", "not_eligible:contact_not_found")
    assert jev.calls == []


def test_R1_ai_replies_off(db, jev):
    contact = seed_contact(db, chatbot_allowed=False, agent_enabled=True)
    seed_user(db, contact_pk=contact["pk"])
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "not_eligible:ai_replies_off")
    assert jev.calls == []


def test_R1_switch_off(db, jev):
    contact = seed_contact(db, agent_enabled=False)
    seed_user(db, contact_pk=contact["pk"])
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "not_eligible:switch_off")
    assert jev.calls == []


def test_R1_no_linked_user_is_no_longer_refused(db, jev):
    contact = seed_contact(db)
    decision = route(db, contact["respond_id"])
    assert not decision.reason.startswith("not_eligible")


def test_R1_not_eligible_wins_over_media_and_a_pending_action(db, jev):
    contact = seed_contact(db, agent_enabled=False)
    decision = route(db, contact["respond_id"], has_media=True)
    assert decision.reason == "not_eligible:switch_off"


# ------------------------------------------------------------------ R2: media


def test_R2_media_goes_to_chat_without_a_jev_call(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], has_media=True)
    assert (decision.side, decision.reason) == ("chat", "media")
    assert jev.calls == []


# ------------------------------------------------------------------ R3: pending action


def seed_proposal(db, contact, *, created_at=None, status="proposed"):
    kwargs = {"created_at": created_at} if created_at is not None else {}
    db.add(
        AgentAction(
            id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
            contact_respond_id=contact["respond_id"], user_id=contact["user_id"], status=status,
            steps=[{"tool": "crm_customer_ask_update", "summary": "Mark SRT-1 done", "status": "proposed"}],
            **kwargs,
        )
    )
    db.commit()


def test_R3_a_pending_proposal_goes_to_the_agent_without_a_jev_call(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    seed_proposal(db, contact)
    decision = route(db, contact["respond_id"], "yes")
    assert (decision.side, decision.reason) == ("agent", "pending_action")
    assert jev.calls == []


def test_R3_an_expired_proposal_does_not_count(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    seed_proposal(db, contact, created_at=datetime.now(timezone.utc) - timedelta(minutes=30))
    decision = route(db, contact["respond_id"], "yes")
    assert decision.reason == "classified"
    assert len(jev.calls) == 1


def test_R3_a_decided_proposal_does_not_count(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    seed_proposal(db, contact, status="executed")
    decision = route(db, contact["respond_id"], "yes")
    assert decision.reason == "classified"


def test_R3_media_beats_a_pending_proposal(db, jev):
    contact = seed_agent_contact(db)
    seed_proposal(db, contact)
    decision = route(db, contact["respond_id"], has_media=True)
    assert decision.reason == "media"


# ------------------------------------------------------------------ R4: open question


def test_R4_an_open_question_in_the_sent_session_vars_goes_to_chat(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], "1", session_vars=OPEN_QUESTION_VARS)
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


def test_R4_empty_session_vars_means_reset_so_no_open_question(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
        {"sv": json.dumps(OPEN_QUESTION_VARS), "id": contact["pk"]},
    )
    db.commit()
    decision = route(db, contact["respond_id"], "why", session_vars={})
    assert decision.reason == "classified"


def test_R4_null_session_vars_reads_the_stored_row(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
        {"sv": json.dumps(OPEN_QUESTION_VARS), "id": contact["pk"]},
    )
    db.commit()
    decision = route(db, contact["respond_id"], "1", session_vars=None)
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


def test_R4_a_pending_proposal_beats_an_open_question(db, jev):
    contact = seed_agent_contact(db)
    seed_proposal(db, contact)
    decision = route(db, contact["respond_id"], "yes", session_vars=OPEN_QUESTION_VARS)
    assert decision.reason == "pending_action"


# ------------------------------------------------------------------ R5: daily cap


def myt_midnight():
    return datetime.now(MYT).replace(hour=0, minute=0, second=0, microsecond=0)


def test_R5_cap_reached_goes_to_chat_without_a_jev_call(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=2)
    for _ in range(2):
        seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "daily_cap")
    assert jev.calls == []


def test_R5_one_under_the_cap_still_routes(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=2)
    seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"


def test_R5_the_day_is_the_myt_business_day(db, jev):
    """Yesterday 23:59 MYT is not today's; a turn just after MYT midnight is."""
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=1)
    seed_agent_turn(db, contact["respond_id"], created_at=myt_midnight() - timedelta(minutes=1))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"

    seed_agent_turn(db, contact["respond_id"], created_at=myt_midnight() + timedelta(seconds=1))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "daily_cap"


def test_R5_only_agent_turns_of_this_contact_count(db, jev):
    contact = seed_agent_contact(db)
    other = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=1)
    now = datetime.now(timezone.utc)
    seed_agent_turn(db, contact["respond_id"], created_at=now, ingress="console")
    seed_agent_turn(db, contact["respond_id"], created_at=now, ingress="webhook")
    seed_agent_turn(db, other["respond_id"], created_at=now)
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"


def test_R5_zero_means_no_cap(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=0)
    for _ in range(5):
        seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"


def test_R5_the_contacts_own_cap_beats_the_global_one(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=50)
    db.execute(
        text("UPDATE respond_contacts SET chatbot_agent_daily_turns = 2 WHERE id = :id"), {"id": contact["pk"]}
    )
    for _ in range(2):
        seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "daily_cap")


def test_R5_a_contact_cap_of_zero_means_no_cap_even_under_a_global_cap(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_agent_daily_turns=1)
    db.execute(
        text("UPDATE respond_contacts SET chatbot_agent_daily_turns = 0 WHERE id = :id"), {"id": contact["pk"]}
    )
    seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"


def test_R5_null_contact_cap_uses_the_global_default_of_50(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    for _ in range(49):
        seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "classified"
    seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "daily_cap"


def test_R5_daily_cap_beats_a_missing_key(db, jev):
    contact = seed_agent_contact(db)
    set_settings(db, chatbot_agent_daily_turns=1)
    seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
    db.commit()
    assert route(db, contact["respond_id"]).reason == "daily_cap"


# ------------------------------------------------------------------ R6: key and prompt


def test_R6_no_key_goes_to_chat_with_no_http_call(db, jev):
    contact = seed_agent_contact(db)
    publish_router_prompt(db)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "router_failed:no_key")
    assert jev.calls == []


def test_R6_the_key_is_never_read_from_the_environment(db, jev, monkeypatch):
    for name in ("TYPESAFE_API_KEY", "JEV_API_KEY", "TYPESAFE_AI_API_KEY"):
        monkeypatch.setenv(name, "ZZT-env-jev-key")
    contact = seed_agent_contact(db)
    publish_router_prompt(db)
    decision = route(db, contact["respond_id"])
    assert decision.reason == "router_failed:no_key"
    assert jev.calls == []


def test_R6_no_production_prompt_goes_to_chat(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "router_failed:no_prompt")
    assert jev.calls == []


# ------------------------------------------------------------------ R7: Jev failures


@pytest.mark.parametrize("kind", ["timeout", "http_500", "http_401", "rate_limited", "malformed"])
def test_R7_a_jev_failure_goes_to_chat_with_its_kind(db, jev, kind):
    from app.services.chatbot.jev_client import JevError

    contact = seed_agent_contact(db)
    arm(db)
    jev.error = JevError(kind)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", f"router_failed:{kind}")
    assert len(jev.calls) == 1


def test_R7_the_call_carries_the_1_5_second_timeout(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    route(db, contact["respond_id"])
    assert jev.calls[0]["timeout_s"] == 1.5


def test_R7_jev_error_exposes_its_kind():
    from app.services.chatbot.jev_client import JevError

    assert JevError("timeout").kind == "timeout"


# ------------------------------------------------------------------ R8 / R9: threshold and choice


def test_R8_confidence_below_the_min_score_goes_to_chat_with_the_score_kept(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    jev.answer = jev_answer("agent", 0.65)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "low_confidence")
    assert decision.score == pytest.approx(0.65)


def test_R8_the_threshold_is_the_setting_not_a_constant(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    set_settings(db, chatbot_router_min_score=0.9)
    jev.answer = jev_answer("agent", 0.85)
    assert route(db, contact["respond_id"]).reason == "low_confidence"
    set_settings(db, chatbot_router_min_score=0.6)
    assert route(db, contact["respond_id"]).reason == "classified"


def test_R8_confidence_exactly_at_the_min_score_passes(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    jev.answer = jev_answer("agent", 0.7)
    assert route(db, contact["respond_id"]).reason == "classified"


@pytest.mark.parametrize("choice", ["agent", "chat"])
def test_R9_the_side_is_jevs_choice_with_score_model_ms_and_tokens(db, jev, choice):
    contact = seed_agent_contact(db)
    arm(db)
    jev.answer = jev_answer(choice, 0.93, input_tokens=812)
    decision = route(db, contact["respond_id"])
    assert decision.side == choice
    assert decision.reason == "classified"
    assert decision.score == pytest.approx(0.93)
    assert decision.model == JEV_MODEL
    assert isinstance(decision.ms, int) and decision.ms >= 0
    assert decision.input_tokens == 812


def test_R9_state_rule_decisions_carry_no_score_model_or_tokens(db, jev):
    contact = seed_contact(db, agent_enabled=False)
    decision = route(db, contact["respond_id"])
    assert decision.score is None and decision.model is None and decision.input_tokens is None


# ------------------------------------------------------------------ R10: the request


def test_R10_the_request_carries_message_recent_exchanges_and_the_prompt(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    long_reply = "r" * 500
    seed_agent_turn(db, contact["respond_id"], created_at=base, ingress="agent", text_="old agent q", reply="a0")
    seed_agent_turn(
        db, contact["respond_id"], created_at=base + timedelta(minutes=1), ingress="agent",
        text_="agent q1", reply="agent a1",
    )
    seed_agent_turn(
        db, contact["respond_id"], created_at=base + timedelta(minutes=2), ingress="console",
        text_="bot q2", reply=long_reply,
    )
    seed_agent_turn(
        db, contact["respond_id"], created_at=base + timedelta(minutes=3), ingress="agent",
        text_="agent q3", reply="agent a3",
    )
    db.commit()

    route(db, contact["respond_id"], "compare Johor and Penang")

    call = jev.calls[0]
    assert call["api_key"] == JEV_KEY
    assert call["model"] == JEV_MODEL
    assert call["instructions"] == INSTRUCTIONS
    assert call["criteria"] == CRITERIA
    state = call["state"]
    assert state["latest_message"] == "compare Johor and Penang"
    recent = state["recent_exchanges"]
    assert len(recent) == 3
    assert [r["answered_by"] for r in recent] in (
        ["agent", "bot", "agent"],  # oldest first
        ["agent", "bot", "agent"][::-1],  # newest first
    )
    assert all(r["answered_by"] in {"bot", "agent"} for r in recent)
    bot_rows = [r for r in recent if r["answered_by"] == "bot"]
    assert len(bot_rows) == 1
    assert len(bot_rows[0]["reply"]) <= 300
    assert all("old agent q" not in json.dumps(r) for r in recent)
    assert state["last_answered_by"] == "agent"


def test_R10_a_contact_with_no_history_sends_an_empty_exchange_list(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    route(db, contact["respond_id"], "hello")
    state = jev.calls[0]["state"]
    assert state["recent_exchanges"] == []
    assert state["last_answered_by"] in (None, "")


# ------------------------------------------------------------------ V2: usage rows


def test_V2_a_classified_call_writes_one_usage_row(db, jev):
    from app.models.ai_assistant import AIAssistantUsageLog

    contact = seed_agent_contact(db)
    arm(db)
    jev.answer = jev_answer("agent", 0.9, input_tokens=640, output_tokens=3)
    route(db, contact["respond_id"])
    db.commit()
    rows = db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").all()
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "typesafe"
    assert row.model == JEV_MODEL
    assert row.prompt_tokens == 640
    assert row.completion_tokens == 3
    assert row.response_time_ms >= 0
    assert row.contact_id == contact["pk"]


def test_V2_a_low_confidence_call_is_still_billed(db, jev):
    from app.models.ai_assistant import AIAssistantUsageLog

    contact = seed_agent_contact(db)
    arm(db)
    jev.answer = jev_answer("agent", 0.55)
    route(db, contact["respond_id"])
    db.commit()
    assert db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").count() == 1


@pytest.mark.parametrize(
    "setup",
    ["unknown", "switch_off", "media", "open_question", "daily_cap", "no_key"],
)
def test_V2_state_rule_decisions_write_no_usage_row(db, jev, setup):
    from app.models.ai_assistant import AIAssistantUsageLog

    if setup == "unknown":
        respond_id, kwargs = unique_code("nobody"), {}
    elif setup == "switch_off":
        contact = seed_contact(db, agent_enabled=False)
        respond_id, kwargs = contact["respond_id"], {}
    else:
        contact = seed_agent_contact(db)
        respond_id, kwargs = contact["respond_id"], {}
        if setup != "no_key":
            arm(db)
        else:
            publish_router_prompt(db)
        if setup == "media":
            kwargs["has_media"] = True
        if setup == "open_question":
            kwargs["session_vars"] = OPEN_QUESTION_VARS
        if setup == "daily_cap":
            set_settings(db, chatbot_agent_daily_turns=1)
            seed_agent_turn(db, respond_id, created_at=datetime.now(timezone.utc))
    db.commit()
    route(db, respond_id, **kwargs)
    db.commit()
    assert db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == "chatbot_router").count() == 0


def test_V2_the_jev_price_row_is_in_the_seed_list():
    from app.services.analytics_connector.prices import SEED_PRICES

    inp, _cached, out, _note = SEED_PRICES[JEV_MODEL]
    assert float(inp) == pytest.approx(0.042)
    assert float(out) == 0.0


# ------------------------------------------------------------------ K4: eligibility parity


@pytest.mark.parametrize(
    "reason",
    ["contact_not_found", "ai_replies_off", "switch_off"],
)
def test_K4_agent_eligibility_and_build_context_refuse_with_the_same_reason(db, reason):
    from app.services.chatbot.agent.access import AgentRefused, agent_eligibility, build_context

    if reason == "contact_not_found":
        respond_id = unique_code("nobody")
    elif reason == "ai_replies_off":
        respond_id = seed_contact(db, chatbot_allowed=False, agent_enabled=False)["respond_id"]
    else:
        respond_id = seed_contact(db, agent_enabled=False)["respond_id"]

    assert agent_eligibility(db, respond_id) == reason
    with pytest.raises(AgentRefused) as exc:
        build_context(db, respond_id)
    assert exc.value.reason == reason


def test_K4_an_eligible_contact_has_no_refusal(db):
    from app.services.chatbot.agent.access import agent_eligibility, build_context

    contact = seed_agent_contact(db)
    assert agent_eligibility(db, contact["respond_id"]) is None
    assert build_context(db, contact["respond_id"]).user_id == contact["user_id"]


def test_K4_an_inactive_linked_user_is_eligible_as_a_contact(db):
    from app.services.chatbot.agent.access import agent_eligibility

    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"], status="INACTIVE")
    assert agent_eligibility(db, contact["respond_id"]) is None


# ------------------------------------------------------------------ S5: WhatsApp is not routed


def test_S5_engine_run_turn_never_calls_the_router_or_jev(monkeypatch):
    """The WhatsApp entry (`engine.run_turn`) must not reach `decide_route` or `classify`."""
    import inspect

    from app.services.chatbot import engine, jev_client, router

    calls = []
    monkeypatch.setattr(router, "decide_route", lambda *a, **k: calls.append("route"))
    monkeypatch.setattr(jev_client, "classify", lambda *a, **k: calls.append("classify"))

    source = inspect.getsource(engine)
    assert "decide_route" not in source
    assert "jev_client" not in source
    assert calls == []


@pytest.mark.parametrize(
    "module",
    [
        "app.services.chatbot.inbox_queue",
        "app.api.v1.external.chat",
        "app.tasks.chat_turns",
    ],
)
def test_S5_the_other_entries_do_not_import_the_router(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    assert "decide_route" not in source
    assert "jev_client" not in source
