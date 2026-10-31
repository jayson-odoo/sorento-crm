"""AGENTIC-IDEATE console pass round, AC-RC-10: a bot question round-trips through the real console path.

Own file because the console harness brings an autouse permission fixture that must not apply to the
real-RBAC idea tests. Turn 1 runs the real engine through `POST /console/turn` (parser and the ideate tool
seam faked, Jev faked), turn 2 sends back the `session_vars` turn 1 returned, as the console page does.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from tests.chatbot.agent.test_router import jev_answer
from tests.chatbot.agent.test_router_console import (  # noqa: F401 - fixtures and helpers
    _post,
    eligible,
    jev as console_jev,
    seeded_contact_with_a_prior_turn,
    stub_console_seams,
)
from tests.chatbot.test_console_turn_endpoint import _ACTOR, _permissions, client  # noqa: F401

ASK_REPLY = "Zzt localised ask-back: what would you like changed?"


def _fake_ideate_tool(monkeypatch, result):
    from app.services.chatbot.lanes import ideate as ideate_mod

    calls = []

    def _call(**kwargs):
        calls.append(kwargs)
        return dict(result)

    monkeypatch.setattr(ideate_mod, "call_ideation_tool", _call)
    return calls


def _ideate_parser(monkeypatch):
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_engine import _parser_output

    monkeypatch.setattr(
        parser_mod, "parse",
        lambda config, user_block: _parser_output(
            message_type="business_query", intent_hint="submit_idea", domain_hint="ideate"
        ),
    )


def _round_trip(client, eligible, console_jev, monkeypatch, result):
    """Turn 1 runs the real bot (parser and the ideate tool seam faked), turn 2 sends back the session_vars
    turn 1 returned, exactly as the console page does. Returns (turn 1 body, turn 2 body, tool calls)."""
    _ideate_parser(monkeypatch)
    calls = _fake_ideate_tool(monkeypatch, result)
    console_jev.answer = jev_answer("chat", 0.95)
    first = _post(client, eligible, "I want to submit an idea")
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1["route"]["side"] == "chat", body1["route"]
    assert len(console_jev.calls) == 1
    assert body1["session_vars"] is not None, "turn 1 returned no session_vars"
    second = _post(client, eligible, "the tap handle is too stiff", session_vars=body1["session_vars"])
    assert second.status_code == 200, second.text
    return body1, second.json(), calls


def test_AC_RC_10_a_bot_required_ask_round_trips_through_the_console(
    client, eligible, console_jev, stub_console_seams, monkeypatch
):
    result = {"status": "ask_idea", "reply_text": ASK_REPLY, "link": None, "session_vars": {"ideation": None}}
    body1, body2, calls = _round_trip(client, eligible, console_jev, monkeypatch, result)
    assert ASK_REPLY in body1["reply_text"] + " ".join(body1["send_messages"])
    assert ((body1["session_vars"].get("focus") or {}).get("required_ask") or {}).get("ask") == "ideation"
    assert body2["route"]["reason"] == "open_question", body2["route"]
    assert body2["route"]["side"] == "chat"
    assert len(console_jev.calls) == 1  # no Jev call for the answering turn
    # turn 2 reached the ideation tool as the answer to the open question
    assert len(calls) == 2, calls
    assert calls[1].get("ask_reply") is True, calls[1]
    assert calls[1]["message_text"] == "the tap handle is too stiff", calls[1]


def test_AC_RC_10_a_held_similar_list_round_trips_through_the_console(
    client, eligible, console_jev, stub_console_seams, monkeypatch
):
    held = {
        "status": "similar_offered",
        "message_text": "price tag should show promo price in red",
        "title": "Promo price in red",
        "similar": [{"idea_id": str(uuid.uuid4()), "idea_number": "IDEA-0151", "title": "A"}],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_test": False,
    }
    result = {"status": "similar_offered", "reply_text": "Similar ideas: 1. A", "link": None,
              "session_vars": {"ideation": held}}
    body1, body2, calls = _round_trip(client, eligible, console_jev, monkeypatch, result)
    assert (body1["session_vars"].get("ideation") or {}).get("status") == "similar_offered", body1["session_vars"]
    assert body2["route"]["reason"] == "open_question", body2["route"]
    assert len(console_jev.calls) == 1
    # turn 2 reached the ideation tool with the user's message
    assert len(calls) == 2, calls
    assert calls[1]["message_text"] == "the tap handle is too stiff", calls[1]
