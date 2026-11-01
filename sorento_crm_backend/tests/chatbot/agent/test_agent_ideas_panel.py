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


def _idea_turn(db, w, *, panel: bool, is_test: bool = True):
    """One agent turn whose model asks for an idea create. Returns (the create's tool result, the key the
    turn ran under). `panel=True` runs under the staff principal, as `panel_service` does."""
    from app.services.chatbot import principal as staff_principal
    from app.services.chatbot.agent.loop import run_agent_turn

    seen: dict = {}

    def after_create(messages, tools):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        seen["tool"] = json.loads(tool_msgs[-1]["content"]) if tool_msgs else None
        return answer_("Done.")

    prov = Prov([round_of(tc(CREATE, dict(FIELDS), "c1")), after_create])
    if panel:
        principal = staff_principal.StaffPrincipal(user_id=w.user_id, conversation_id=str(uuid.uuid4()))
        key = principal.key
        with staff_principal.acting_as(principal):
            run_agent_turn(db, contact_respond_id=key, text=USER_TEXT, provider=prov, mcp_call=_no_mcp, catalog={})
    else:
        key = w.respond_id
        run_agent_turn(
            db, contact_respond_id=key, text=USER_TEXT, provider=prov, mcp_call=_no_mcp, catalog={}, is_test=is_test
        )
    return seen.get("tool"), key


def test_a_panel_turn_refuses_an_idea_create_with_the_ideas_link_and_proposes_nothing(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)

    tool, key = _idea_turn(db, w, panel=True)

    assert tool is not None, "the model never saw a result for crm_idea_create"
    assert tool["status"] != "proposed", tool
    assert tool["status"] in {"denied", "invalid", "error"}, tool
    assert "/ideas" in tool["message"], tool
    assert actions.pending_action(db, key) is None, "no card may wait for a yes"
    assert posts(ss, SIMILAR_PATH) == [] and posts(ss, CREATE_PATH) == [], "no ideation call"
    assert [c for c in ss.calls if c["method"] != "GET"] == [], ss.calls


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
