"""AGENTIC-UNIFY round 9, second pass (AC-12): ideas keep the /ideas link on a panel turn.

`run_agent_turn` defaults to `is_test=True`, which a console turn reads as "make a test idea". A panel turn
runs the same loop as a staff principal, so a user holding `ideation.board.view` with a linked contact would
get a proposed test idea. The agent must refuse the create with the /ideas link and propose nothing. The
controls beside it (a console turn, a live turn) must keep proposing, so the refusal cannot pass by nothing
ever being proposed. Same harness as `test_agent_ideas_live.py`.
"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.chatbot.agent.test_agent_writes import answer_, round_of, tc
from tests.chatbot.agent.test_agent_writes_ideas import (  # noqa: F401 - fixtures and helpers
    CREATE, CREATE_PATH, FIELDS, SIMILAR_PATH, _fresh_token_cache, _listeners, db, make_world, posts, ss,
)
from tests.chatbot.agent.test_agent_writes_round1 import Prov, _no_mcp

USER_TEXT = "I have an idea: the stock list is too long to scroll on my phone, can we shorten it"


def _turn(db, w, *, panel: bool, is_test: bool = True, call=(CREATE, None), final="Done."):
    """One agent turn whose model calls `call` once and then answers `final`. Returns (the tool result the
    model was given back, the turn result, the key the turn ran under). `panel=True` runs under the staff
    principal, as `panel_service` does."""
    from app.services.chatbot import principal as staff_principal
    from app.services.chatbot.agent.loop import run_agent_turn

    name, args = call
    seen: dict = {}

    def after_call(messages, tools):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        seen["tool"] = json.loads(tool_msgs[-1]["content"]) if tool_msgs else None
        return answer_(final)

    prov = Prov([round_of(tc(name, dict(FIELDS) if args is None else args, "c1")), after_call])
    if panel:
        principal = staff_principal.StaffPrincipal(user_id=w.user_id, conversation_id=str(uuid.uuid4()))
        key = principal.key
        with staff_principal.acting_as(principal):
            result = run_agent_turn(
                db, contact_respond_id=key, text=USER_TEXT, provider=prov, mcp_call=_no_mcp, catalog={}
            )
    else:
        key = w.respond_id
        result = run_agent_turn(
            db, contact_respond_id=key, text=USER_TEXT, provider=prov, mcp_call=_no_mcp, catalog={}, is_test=is_test
        )
    return seen.get("tool"), result, key


def _idea_turn(db, w, *, panel: bool, is_test: bool = True):
    tool, _, key = _turn(db, w, panel=panel, is_test=is_test)
    return tool, key


def test_a_panel_turn_refuses_an_idea_create_and_the_reply_carries_the_ideas_link(db, ss):
    w = make_world(db)

    tool, result, _ = _turn(db, w, panel=True)

    assert "/ideas" in result.reply_text, result.reply_text


def test_the_refusal_is_not_a_denial_and_says_nothing_was_created(db, ss):
    w = make_world(db)

    tool, _, _ = _turn(db, w, panel=True)

    assert tool is not None, "the model never saw a result for crm_idea_create"
    assert tool["status"] != "denied", "denied tells the model the user lacks access, which is false here"
    assert tool["status"] != "proposed", tool
    assert "/ideas" in tool["message"], tool
    assert "not created" in tool["message"].lower() or "nothing was created" in tool["message"].lower() or (
        "no idea" in tool["message"].lower()
    ), tool


def test_a_refused_idea_on_the_panel_proposes_no_step_no_card_and_calls_no_ideation(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)

    tool, result, key = _turn(db, w, panel=True)

    assert tool is not None and tool["status"] != "proposed", tool
    assert result.pending_action is None, result.pending_action
    assert actions.pending_action(db, key) is None, "no card may wait for a yes"
    assert posts(ss, SIMILAR_PATH) == [] and posts(ss, CREATE_PATH) == [], "no ideation call"
    assert [c for c in ss.calls if c["method"] != "GET"] == [], ss.calls


def test_a_model_that_already_says_the_link_does_not_get_the_sentence_twice(db, ss):
    w = make_world(db)

    _, result, _ = _turn(db, w, panel=True, final="You can add it on the board at /ideas.")

    assert result.reply_text.count("/ideas") == 1, result.reply_text


def test_control_another_tools_denial_on_a_panel_turn_adds_no_ideas_sentence(db, ss):
    w = make_world(db)  # holds ideation.board.view only: an opportunity create is outside this user's access

    tool, result, _ = _turn(
        db, w, panel=True, call=("crm_opportunity_create", {"title": "Zzt deal"}), final="That is not open to you."
    )

    assert tool is not None and tool["status"] == "denied", tool
    assert "/ideas" not in result.reply_text, result.reply_text


def test_control_a_console_turn_still_proposes_a_test_idea(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)

    tool, key = _idea_turn(db, w, panel=False, is_test=True)

    assert tool is not None and tool["status"] == "proposed", tool
    assert actions.pending_action(db, key) is not None


def test_control_a_live_turn_still_proposes_a_real_idea(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)

    tool, key = _idea_turn(db, w, panel=False, is_test=False)

    assert tool is not None and tool["status"] == "proposed", tool
    step = actions.pending_action(db, key)
    assert step is not None
