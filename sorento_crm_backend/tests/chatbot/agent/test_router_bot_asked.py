"""AGENTIC-IDEATE R3a (AC-R3a-1 to AC-R3a-5): a reply to the bot's own question stays on the bot.

The Jev call is always the monkeypatched `jev` fixture; no network. Postgres via the blank schema;
every test seeds its own contact chain.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user
from tests.chatbot.agent.test_router import (  # noqa: F401
    _fresh_prompt_cache,
    arm,
    db,
    jev,
    route,
    seed_proposal,
)

HELD = {
    "status": "similar_offered",
    "message_text": "price tag should show promo price in red",
    "title": "Promo price in red",
    "similar": [
        {"idea_id": "11111111-1111-4111-8111-111111111111", "idea_number": "IDEA-0151", "title": "A"},
        {"idea_id": "22222222-2222-4222-8222-222222222222", "idea_number": "IDEA-0097", "title": "B"},
    ],
    "is_test": False,
}

REQUIRED_ASK = {"slot": "warehouse", "question": "Which warehouse?", "options": []}


def held(*, age_hours=0.0, **over):
    pointer = copy.deepcopy(HELD)
    pointer["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    pointer.update(over)
    return pointer


def vars_with(**keys):
    base = {"focus": {}, "open_question": None, "ideation": None, "access_levels": [], "contains_flyer": False}
    base.update(keys)
    return base


def test_AC_R3a_1_a_required_ask_in_focus_keeps_the_reply_on_the_bot(db, jev):
    contact = seed_agent_contact(db)  # no key and no prompt: the rule must fire before either is read
    decision = route(db, contact["respond_id"], "kuching", session_vars=vars_with(focus={"required_ask": REQUIRED_ASK}))
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


@pytest.mark.parametrize("is_test", [True, False])
def test_AC_R3a_2_a_fresh_held_list_keeps_the_reply_on_the_bot(db, jev, is_test):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], "2", session_vars=vars_with(ideation=held(is_test=is_test)))
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


@pytest.mark.parametrize(
    "ideation",
    [
        held(age_hours=24),
        held(age_hours=48),
        held(similar="not a list"),
        held(message_text=""),
        {**held(), "updated_at": "not a date"},
        {"status": "similar_offered"},
    ],
    ids=["24h", "48h", "similar_not_list", "no_message_text", "bad_date", "bare_status"],
)
def test_AC_R3a_3_an_old_or_malformed_held_list_is_not_held(db, jev, ideation):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], "2", session_vars=vars_with(ideation=ideation))
    assert decision.reason == "classified"
    assert len(jev.calls) == 1


def test_AC_R3a_4_empty_session_vars_hold_nothing_even_over_a_stored_held_list(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
        {"sv": json.dumps(vars_with(ideation=held())), "id": contact["pk"]},
    )
    db.commit()
    decision = route(db, contact["respond_id"], "2", session_vars={})
    assert decision.reason == "classified"


def test_AC_R3a_4_none_reads_the_stored_row(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
        {"sv": json.dumps(vars_with(ideation=held())), "id": contact["pk"]},
    )
    db.commit()
    decision = route(db, contact["respond_id"], "2", session_vars=None)
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


def test_AC_R3a_4_the_legacy_variables_shape_is_read_too(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], "2", session_vars={"variables": {"ideation": held()}})
    assert (decision.side, decision.reason) == ("chat", "open_question")
    assert jev.calls == []


def test_AC_R3a_4_the_legacy_shape_carries_a_required_ask_too(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(
        db, contact["respond_id"], "kuching", session_vars={"variables": {"focus": {"required_ask": REQUIRED_ASK}}}
    )
    assert (decision.side, decision.reason) == ("chat", "open_question")


@pytest.mark.parametrize("setup, side, reason", [
    ("ineligible", "chat", "not_eligible:switch_off"),
    ("media", "chat", "media"),
    ("pending", "agent", "pending_action"),
])
def test_AC_R3a_5_earlier_rules_still_win(db, jev, setup, side, reason):
    kwargs = {}
    if setup == "ineligible":
        contact = seed_contact(db, agent_enabled=False)
        seed_user(db, contact_pk=contact["pk"])
    else:
        contact = seed_agent_contact(db)
        arm(db)
    if setup == "media":
        kwargs["has_media"] = True
    if setup == "pending":
        seed_proposal(db, contact)
    decision = route(
        db, contact["respond_id"], "2",
        session_vars=vars_with(ideation=held(), focus={"required_ask": REQUIRED_ASK}), **kwargs,
    )
    assert (decision.side, decision.reason) == (side, reason)
    assert jev.calls == []
