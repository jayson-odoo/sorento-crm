"""AGENTIC-KNOWLEDGE P2 W1, slice S3: WhatsApp routing in the inbox drain (UAC AC-W18 .. AC-W22).

Before `engine.run_turn`, `inbox_queue._run_row` asks `router.decide_route`. Side "agent" runs
`run_agent_turn(..., is_test=False)` and posts its reply as one `send_message` action through the
same `_post` / `direct_ingress.send_outcome` the bot uses; the bot is not run for that row. Any
other side, or a router exception, is today's bot path. An agent failure posts a fixed honest line
(no "sorry", no "busy") and never re-runs the bot.

The drain runs for real through the `world` harness of test_inbox_queue_order.py (real Postgres
rows, real Redis, the signed webhook and `/chat/turn` injectors). Only four seams are replaced:
`router.decide_route`, `agent.loop.run_agent_turn`, `engine.run_turn` and
`direct_ingress.send_outcome`. Nothing reaches a network.
"""
from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

import pytest

from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from tests._pg_fixture import blank_session
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    assert_nothing_to_send,
    iq_serial,
    redis_client,
    wait_until,
    world,
)

AGENT_REPLY = "ZZT agent reply: the tile is warranted for ten years."
BOT_REPLY = "ZZT bot reply"


@pytest.fixture()
def seams(world, monkeypatch):
    """Spies on the four seams. Defaults: the router says agent, the agent answers AGENT_REPLY."""
    from app.services.chatbot import router
    from app.services.chatbot.agent import loop

    s = SimpleNamespace(
        route_calls=[],
        agent_calls=[],
        bot_calls=[],
        sent=[],
        decision=router.RouteDecision("agent", "classified", score=0.9),
        route_error=None,
        agent_error=None,
        reply=AGENT_REPLY,
        agent_turn_id=str(uuid.uuid4()),
    )

    def fake_decide_route(db, **kwargs):
        s.route_calls.append(kwargs)
        if s.route_error is not None:
            raise s.route_error
        return s.decision

    def fake_run_agent_turn(db, **kwargs):
        s.agent_calls.append(kwargs)
        if s.agent_error is not None:
            raise s.agent_error
        return loop.AgentTurnResult(
            turn_id=s.agent_turn_id, conversation_id=str(uuid.uuid4()), reply_text=s.reply,
            status="answered", limit_hit=None, rounds=1, usage={}, tool_calls=[],
        )

    def fake_bot_turn(envelope, **kwargs):
        s.bot_calls.append(kwargs)
        return engine_mod.TurnResult(
            turn_id=kwargs.get("queued_turn_id"),
            status="done",
            actions=[{"kind": "send_message", "text": BOT_REPLY}],
            ctx={"contact": {"id": engine_mod._contact_respond_id(envelope)}, "text": {"zzt": True}},
        )

    def fake_send_outcome(factory, **kwargs):
        s.sent.append(kwargs)
        return direct_ingress.SEND_OK

    monkeypatch.setattr(router, "decide_route", fake_decide_route)
    monkeypatch.setattr(loop, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(engine_mod, "run_turn", fake_bot_turn)
    monkeypatch.setattr(direct_ingress, "send_outcome", fake_send_outcome)
    # A module level import in the drain would bind its own name; patch that too when it exists.
    from app.services.chatbot import inbox_queue

    monkeypatch.setattr(inbox_queue, "decide_route", fake_decide_route, raising=False)
    monkeypatch.setattr(inbox_queue, "run_agent_turn", fake_run_agent_turn, raising=False)
    return s


def _drive(world, seams, *, label, expect_sends=1):
    """One covered contact sends one message; wait for the drain to finish its row."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 20, label)
    queued, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(queued)
    wait_until(lambda: len(seams.sent) >= expect_sends, timeout=20)
    wait_until(lambda: (world.row_for(contact, mid) or {}).get("status") in ("done", "failed"), timeout=20)
    time.sleep(0.5)  # a second (double) answer would show up here
    return contact, mid


def _expected_actions(text):
    return engine_mod.split_send_actions([{"kind": "send_message", "text": text}])


# ---------------------------------------------------------------- AC-W18: the agent answers


def test_ac_w18_an_agent_decision_runs_the_agent_and_posts_its_reply_not_the_bot(world, seams):
    contact, mid = _drive(world, seams, label="agent1")

    assert len(seams.agent_calls) == 1
    assert seams.bot_calls == [], "engine.run_turn must not run for an agent row"
    assert len(seams.sent) == 1
    sent = seams.sent[0]
    assert sent["contact_id"] == contact
    assert sent["actions"] == _expected_actions(AGENT_REPLY)
    assert sent["actions"][0]["kind"] == "send_message"
    assert world.row_for(contact, mid)["status"] == "done"


def test_ac_w18_the_router_is_asked_with_the_rows_own_text_and_contact(world, seams):
    contact, _ = _drive(world, seams, label="agent2")

    assert len(seams.route_calls) == 1
    call = seams.route_calls[0]
    assert call["contact_respond_id"] == contact
    assert "agent2" in call["text"], "the text of the message the row carries"
    assert call["has_media"] is False


def test_ac_w18_the_agent_is_run_for_this_contact_with_the_rows_text(world, seams):
    contact, _ = _drive(world, seams, label="agent3")

    call = seams.agent_calls[0]
    assert call["contact_respond_id"] == contact
    assert "agent3" in call["text"]


def test_ac_w18_the_inbox_row_trace_names_the_agent_turn(world, seams):
    contact, mid = _drive(world, seams, label="agent4")

    row = world.row_for(contact, mid)

    assert seams.agent_turn_id in json.dumps(row["trace"], default=str)


def test_ac_w18_a_long_marked_reply_is_split_as_the_bots_is(world, seams):
    seams.reply = "(1/2)\nzzt part one\n\n(2/2)\nzzt part two"
    expected = _expected_actions(seams.reply)
    assert len(expected) == 2, "the fixture text must be a complete marked run"

    _drive(world, seams, label="agent5")

    assert seams.sent[0]["actions"] == expected
    assert seams.bot_calls == []


# ---------------------------------------------------------------- AC-W19: any other decision is the bot


@pytest.mark.parametrize(
    "reason",
    [
        "not_eligible:switch_off",
        "not_eligible:ai_replies_off",
        "media",
        "open_question",
        "daily_cap",
        "text_length",
        "low_confidence",
        "router_failed:no_key",
        "classified",
    ],
)
def test_ac_w19_a_chat_decision_runs_todays_bot_unchanged(world, seams, reason):
    from app.services.chatbot.router import RouteDecision

    seams.decision = RouteDecision("chat", reason)

    contact, mid = _drive(world, seams, label="bot1")

    assert len(seams.route_calls) == 1
    assert seams.agent_calls == []
    assert len(seams.bot_calls) == 1
    assert seams.bot_calls[0].get("queued_turn_id") == world.row_for(contact, mid)["id"]
    assert seams.sent[0]["actions"] == _expected_actions(BOT_REPLY)
    assert world.row_for(contact, mid)["status"] == "done"


# ---------------------------------------------------------------- AC-W20: a router exception falls to the bot


@pytest.mark.parametrize("error", [RuntimeError("zzt router down"), ValueError("zzt bad state")])
def test_ac_w20_a_router_exception_falls_to_the_bot(world, seams, error):
    seams.route_error = error

    contact, mid = _drive(world, seams, label="bot2")

    assert len(seams.route_calls) == 1
    assert seams.agent_calls == []
    assert len(seams.bot_calls) == 1
    assert seams.sent[0]["actions"] == _expected_actions(BOT_REPLY)
    assert world.row_for(contact, mid)["status"] == "done"


# ---------------------------------------------------------------- AC-W21: an agent failure is one honest line


def _failure_errors():
    from app.services.chatbot.agent.access import AgentRefused
    from app.services.chatbot.agent.loop import AgentBusy

    return [RuntimeError("zzt model down"), AgentBusy("zzt another turn"), AgentRefused("switch_off")]


@pytest.mark.parametrize("index", [0, 1, 2], ids=["error", "busy", "refused"])
def test_ac_w21_an_agent_failure_posts_the_fixed_line_and_does_not_run_the_bot(world, seams, index):
    seams.agent_error = _failure_errors()[index]

    contact, mid = _drive(world, seams, label="fail1")

    assert len(seams.agent_calls) == 1
    assert seams.bot_calls == [], "an agent failure is never a bot re-run"
    assert len(seams.sent) == 1
    actions = seams.sent[0]["actions"]
    assert [a["kind"] for a in actions] == ["send_message"]
    text = actions[0]["text"]
    assert isinstance(text, str) and text.strip()
    assert "sorry" not in text.lower()
    assert "busy" not in text.lower()
    assert "zzt" not in text.lower(), "the exception detail never reaches the customer"


def test_ac_w21_the_failure_line_is_fixed_not_the_exception_text(world, seams):
    seams.agent_error = RuntimeError("zzt secret detail 12345")

    _drive(world, seams, label="fail2")

    assert "12345" not in json.dumps(seams.sent[0]["actions"])


# ---------------------------------------------------------------- AC-W22: the turn is a live turn


def _scripted_provider():
    from app.services.llm_provider import ChatResult

    class Provider:
        def chat(self, messages, *, tools=None, **kw):
            return ChatResult(
                content="", prompt_tokens=10, completion_tokens=1, total_tokens=11,
                tool_calls=[{
                    "id": "a1", "name": "answer",
                    "arguments": {"text": "Hello.", "figures": [], "not_found": [], "not_checked": []},
                }],
            )

    return Provider()


def _forbidden(name, args):
    raise AssertionError(f"no tool call expected, got {name}")


def _turn_row(db, turn_id):
    from app.models.chatbot_turn import ChatbotTurn

    return db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one()


def test_ac_w22_a_console_agent_turn_stays_is_test_true():
    from app.services.chatbot.agent.loop import run_agent_turn
    from tests.chatbot.agent._seed import seed_agent_contact

    with blank_session() as db:
        contact = seed_agent_contact(db)

        result = run_agent_turn(
            db, contact_respond_id=contact["respond_id"], text="hello",
            provider=_scripted_provider(), mcp_call=_forbidden, catalog={},
        )

        assert _turn_row(db, result.turn_id).is_test is True


def test_ac_w22_is_test_false_writes_a_live_agent_turn():
    from app.services.chatbot.agent.loop import run_agent_turn
    from tests.chatbot.agent._seed import seed_agent_contact

    with blank_session() as db:
        contact = seed_agent_contact(db)

        result = run_agent_turn(
            db, contact_respond_id=contact["respond_id"], text="hello",
            provider=_scripted_provider(), mcp_call=_forbidden, catalog={}, is_test=False,
        )

        row = _turn_row(db, result.turn_id)
        assert row.is_test is False
        assert row.ingress == "agent"


def test_ac_w22_an_unlinked_contact_runs_a_live_agent_turn_end_to_end():
    """The contact principal through the real loop: no linked user, still answered, still not a test turn."""
    from app.services.chatbot.agent.loop import run_agent_turn
    from tests.chatbot.agent._seed import seed_contact

    with blank_session() as db:
        contact = seed_contact(db)

        result = run_agent_turn(
            db, contact_respond_id=contact["respond_id"], text="hello",
            provider=_scripted_provider(), mcp_call=_forbidden, catalog={}, is_test=False,
        )

        assert result.status == "answered"
        assert "Hello" in result.reply_text
        assert _turn_row(db, result.turn_id).is_test is False


def test_ac_w22_the_whatsapp_drain_asks_for_a_live_turn(world, seams):
    _drive(world, seams, label="live1")

    assert seams.agent_calls[0]["is_test"] is False
