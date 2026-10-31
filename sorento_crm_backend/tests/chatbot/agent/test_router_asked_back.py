"""AGENTIC-IDEATE R3b: a reply to the agent's own question stays with the agent (AC-R3b-3 to AC-R3b-9).

The Jev call is always the monkeypatched `jev` fixture; no network. Postgres via the blank
schema; every test seeds its own contact chain. New names are reached at call time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.chatbot_turn import ChatbotTurn
from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user
from tests.chatbot.agent.test_router import (  # noqa: F401
    OPEN_QUESTION_VARS,
    _fresh_prompt_cache,
    arm,
    db,
    jev,
    jev_answer,
    publish_router_prompt,
    route,
    seed_agent_turn,
    seed_proposal,
    set_jev_key,
    set_settings,
)

FLOOR = 0.7  # default chatbot_router_min_score


def seed_flagged(db, respond_id, *, minutes_ago=5, asked_back=True, ingress="agent", flag=True):
    response = {"reply_text": "What is the idea?", "status": "answered"}
    if flag:
        response["asked_back"] = asked_back
    row = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=respond_id,
        ingress=ingress,
        is_test=True,
        status="done",
        envelope={"text": "I want to submit an idea"},
        response=response,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    db.add(row)
    db.commit()
    return row


def armed_flagged(db, **kw):
    contact = seed_agent_contact(db)
    arm(db)
    seed_flagged(db, contact["respond_id"], **kw)
    return contact


def test_AC_R3b_window_constant_is_sixty():
    from app.services.chatbot import router

    assert router.ASKED_BACK_MINUTES == 60


@pytest.mark.parametrize("confidence", [0.3, 0.9])
def test_AC_R3b_3_jev_agent_at_any_confidence_is_agent_asked(db, jev, confidence):
    contact = armed_flagged(db)
    jev.answer = jev_answer("agent", confidence)
    decision = route(db, contact["respond_id"], "stock list too long on my phone")
    assert (decision.side, decision.reason) == ("agent", "agent_asked")
    assert decision.score == pytest.approx(confidence)
    assert decision.model == "jev-1.14.0"
    assert isinstance(decision.ms, int) and decision.ms >= 0
    assert len(jev.calls) == 1


def test_AC_R3b_4_jev_chat_under_the_floor_is_agent_asked(db, jev):
    contact = armed_flagged(db)
    jev.answer = jev_answer("chat", 0.4)
    decision = route(db, contact["respond_id"], "stock list too long on my phone")
    assert (decision.side, decision.reason) == ("agent", "agent_asked")


@pytest.mark.parametrize("confidence", [FLOOR, 0.98])
def test_AC_R3b_5_jev_chat_at_or_above_the_floor_wins(db, jev, confidence):
    contact = armed_flagged(db)
    jev.answer = jev_answer("chat", confidence)
    decision = route(db, contact["respond_id"], "SRTWB888 stock")
    assert (decision.side, decision.reason) == ("chat", "classified")


@pytest.mark.parametrize(
    "case, positive",
    [
        ("newer_bot_turn", False),
        ("sixty_minutes_old", False),
        ("sixty_one_minutes_old", False),
        ("fifty_nine_minutes_old", True),
        ("no_flag", False),
        ("asked_back_false", False),
        ("other_contact", False),
    ],
)
def test_AC_R3b_6_the_flag_is_ignored_when_stale_superseded_or_not_ours(db, jev, case, positive):
    contact = seed_agent_contact(db)
    arm(db)
    rid = contact["respond_id"]
    if case == "newer_bot_turn":
        seed_flagged(db, rid, minutes_ago=10)
        seed_flagged(db, rid, minutes_ago=2, ingress="console", flag=False)
    elif case == "sixty_minutes_old":
        seed_flagged(db, rid, minutes_ago=60)
    elif case == "sixty_one_minutes_old":
        seed_flagged(db, rid, minutes_ago=61)
    elif case == "fifty_nine_minutes_old":
        seed_flagged(db, rid, minutes_ago=59)
    elif case == "no_flag":
        seed_flagged(db, rid, flag=False)
    elif case == "asked_back_false":
        seed_flagged(db, rid, asked_back=False)
    else:
        other = seed_agent_contact(db)
        seed_flagged(db, other["respond_id"])
    jev.answer = jev_answer("chat", 0.4)
    decision = route(db, rid, "stock list too long on my phone")
    if positive:
        assert (decision.side, decision.reason) == ("agent", "agent_asked")
    else:
        assert (decision.side, decision.reason) == ("chat", "low_confidence")


@pytest.mark.parametrize(
    "setup, side, reason",
    [
        ("ineligible", "chat", "not_eligible:switch_off"),
        ("media", "chat", "media"),
        ("pending", "agent", "pending_action"),
        ("open_question", "chat", "open_question"),
        ("daily_cap", "chat", "daily_cap"),
        ("text_length", "chat", "text_length"),
        ("no_key", "chat", "router_failed:no_key"),
        ("no_prompt", "chat", "router_failed:no_prompt"),
    ],
)
def test_AC_R3b_7_earlier_rules_still_win_with_the_flag_set(db, jev, setup, side, reason):
    kwargs = {}
    if setup == "ineligible":
        contact = seed_contact(db, agent_enabled=False)
        seed_user(db, contact_pk=contact["pk"])
        arm(db)
    else:
        contact = seed_agent_contact(db)
        if setup == "no_key":
            publish_router_prompt(db)
        elif setup == "no_prompt":
            set_jev_key(db)
        else:
            arm(db)
    seed_flagged(db, contact["respond_id"], minutes_ago=5)
    if setup == "media":
        kwargs["has_media"] = True
    elif setup == "pending":
        seed_proposal(db, contact)
    elif setup == "open_question":
        kwargs["session_vars"] = OPEN_QUESTION_VARS
    elif setup == "daily_cap":
        set_settings(db, chatbot_agent_daily_turns=1)
        db.commit()
    elif setup == "text_length":
        kwargs["text_"] = "x" * 4001
    decision = route(db, contact["respond_id"], **kwargs)
    assert (decision.side, decision.reason) == (side, reason)
    assert jev.calls == []


@pytest.mark.parametrize("kind", ["timeout", "http_500", "http_401", "rate_limited", "malformed"])
def test_AC_R3b_8_a_jev_failure_still_goes_to_chat_with_today_reason(db, jev, kind):
    from app.services.chatbot.jev_client import JevError

    contact = armed_flagged(db)
    jev.error = JevError(kind)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", f"router_failed:{kind}")


def test_AC_R3b_8_a_malformed_choice_goes_to_chat(db, jev):
    contact = armed_flagged(db)
    jev.answer = jev_answer("maybe", 0.9)
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "router_failed:malformed")


@pytest.mark.parametrize("session_vars", [{}, None])
def test_AC_R3b_9_the_flag_is_read_whatever_session_vars_the_console_sends(db, jev, session_vars):
    contact = armed_flagged(db)
    jev.answer = jev_answer("chat", 0.4)
    decision = route(db, contact["respond_id"], "stock list too long on my phone", session_vars=session_vars)
    assert (decision.side, decision.reason) == ("agent", "agent_asked")
