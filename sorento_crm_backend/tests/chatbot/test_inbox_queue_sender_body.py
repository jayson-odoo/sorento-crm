"""CHAT-INBOX-QUEUE follow-up: the drain's POST to the chatbot sender carries what the spine's
action executor reads off `/chat/turn`'s own response.

* `ctx`: `sub-send-attachments` addresses the customer by `ctx.contact.id` and its fallback
  text reads `ctx.text`; the spine hands it the turn's ctx, the sender had none.
* The actions go out split exactly as `/chat/turn` sends them (`TurnResult.as_dict` runs
  `split_send_actions`), so a marked long reply is several messages, not one over
  WhatsApp's limit.
* An answer's `send_attachments` action carries the reply, as the tail's and the
  formatter's already do.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.services.chatbot import engine as engine_mod
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    assert_nothing_to_send,
    iq_serial,
    redis_client,
    world,
)


def _capture_bodies(world, monkeypatch) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []

    def capture(url, **kwargs):
        bodies.append(dict(kwargs.get("json") or {}))
        return world._fake_post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", capture)
    return bodies


def _body_for(bodies: list[dict[str, Any]], contact: str) -> dict[str, Any]:
    mine = [b for b in bodies if str(b.get("contact_id")) == contact]
    assert len(mine) == 1, mine
    return mine[0]


def test_a_drained_turn_posts_its_ctx_with_the_contact_and_the_text(world, monkeypatch):
    bodies = _capture_bodies(world, monkeypatch)
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 20, "ctx1")

    queued, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(queued)
    world.wait_posts(1, contact)

    ctx = _body_for(bodies, contact).get("ctx")
    assert isinstance(ctx, dict), f"the sender body carries no ctx: {ctx!r}"
    assert str((ctx.get("contact") or {}).get("id")) == contact, ctx.get("contact")
    assert ctx.get("text"), f"ctx.text is empty: {ctx!r}"


def test_the_drain_splits_a_marked_reply_and_posts_the_turns_own_ctx(world, monkeypatch):
    bodies = _capture_bodies(world, monkeypatch)
    marked = "(1/2)\nzzt part one\n\n(2/2)\nzzt part two"
    action = {
        "kind": "send_message",
        "text": marked,
        "quick_replies": ["zzt yes"],
        "result_set": [{"position": 1}],
        "dry_run": False,
    }
    expected = engine_mod.split_send_actions([dict(action)])
    assert len(expected) == 2, "the fixture text must be a complete marked run"

    def fake_run_turn(envelope, **kwargs):
        return engine_mod.TurnResult(
            turn_id=kwargs.get("queued_turn_id"),
            status="done",
            actions=[dict(action)],
            ctx={"contact": {"id": engine_mod._contact_respond_id(envelope)}, "text": {"zzt": True}},
        )

    monkeypatch.setattr(engine_mod, "run_turn", fake_run_turn)
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 20, "split1")

    queued, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(queued)
    world.wait_posts(1, contact)

    body = _body_for(bodies, contact)
    assert body.get("actions") == expected, body.get("actions")
    assert body.get("ctx") == {"contact": {"id": contact}, "text": {"zzt": True}}, body.get("ctx")


def test_an_answers_attachments_action_carries_the_reply():
    from app.services.chatbot.turn import compose as turn_compose

    files = [{"url": "https://example.invalid/zzt.pdf", "name": "zzt.pdf"}]
    answer = turn_compose.Answer(text="zzt here are the files", files=files)
    reply = {"text": "zzt here are the files", "quick_replies": None, "result_set": [], "attachments_src": files}

    actions = engine_mod._answer_actions(answer, dry_run=False, reply=reply)

    attach = [a for a in actions if a.get("kind") == "send_attachments"]
    assert attach == [
        {"kind": "send_attachments", "attachments_src": files, "reply": reply, "dry_run": False}
    ], attach
