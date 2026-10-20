"""CHAT-CONSOLE-UX: a quoted voice note or image carries the quote, like WhatsApp.

The console's `reply_to` already rides a TEXT turn as the webhook's own `replyTo` block
(`test_console_turn_reply_to.py`). A media turn dropped it: `run_console_turn` never handed
it to `_run_console_media_turn`. The owner answers bot questions by voice and a quoted reply
sets the bot's context, so the media envelope must carry the same block, same shape.

Seams and seeding are the media suite's own (`test_console_media_turn.py`).
"""
from __future__ import annotations

import uuid

from app.services.chatbot import console_service

from tests.chatbot.test_console_media_turn import (  # noqa: F401  (fixtures)
    CONSOLE_TURN_URL,
    _media_payload,
    _permissions,
    _run_inline,
    _seeded_contact_and_media_limit,
    client,
    stub_console_and_media_seams,
)


def _spy_run_turn(monkeypatch) -> list[dict]:
    seen: list[dict] = []
    real = console_service.run_turn

    def spy(envelope, *args, **kwargs):
        seen.append(envelope.model_dump(mode="json", by_alias=True) if hasattr(envelope, "model_dump") else envelope)
        return real(envelope, *args, **kwargs)

    monkeypatch.setattr(console_service, "run_turn", spy)
    return seen


def _post_media(client, respond_io_id: str, **extra):
    return client.post(
        CONSOLE_TURN_URL,
        json={
            "contact_respond_id": respond_io_id,
            "text": "",
            "run_id": f"ZZT-console-{uuid.uuid4().hex[:8]}",
            "media": _media_payload(),
            **extra,
        },
    )


def _extract_ok(monkeypatch):
    import app.tasks.media_tasks as media_tasks_mod

    monkeypatch.setattr(
        media_tasks_mod,
        "run_media_extraction",
        lambda job: {"rendered_text": "the second one", "entities": []},
    )


class TestMediaTurnCarriesReplyTo:
    def test_a_quoted_media_turn_carries_the_webhook_reply_to_block(
        self, client, session_factory, stub_console_and_media_seams, monkeypatch,
    ):
        respond_io_id, _ = _seeded_contact_and_media_limit(session_factory)
        _run_inline(monkeypatch)
        _extract_ok(monkeypatch)
        seen = _spy_run_turn(monkeypatch)

        resp = _post_media(
            client,
            respond_io_id,
            reply_to={"id": "bot-turn-1-0", "text": "Which one do you mean?", "source": "n8n"},
        )
        assert resp.status_code == 200, resp.text
        assert len(seen) == 1
        inner = seen[0]["message"]["message"]
        assert inner["replyTo"] == {
            "id": "bot-turn-1-0",
            "sender": {"source": "n8n"},
            "message": {"text": "Which one do you mean?"},
        }
        # Still the attachment message, the quote rides beside it.
        assert inner["message"]["type"] == "attachment"

    def test_a_quote_of_the_customers_own_message_keeps_its_source(
        self, client, session_factory, stub_console_and_media_seams, monkeypatch,
    ):
        respond_io_id, _ = _seeded_contact_and_media_limit(session_factory)
        _run_inline(monkeypatch)
        _extract_ok(monkeypatch)
        seen = _spy_run_turn(monkeypatch)

        resp = _post_media(
            client,
            respond_io_id,
            reply_to={"id": "console-abc123", "text": "any WC?", "source": "contact"},
        )
        assert resp.status_code == 200, resp.text
        assert seen[0]["message"]["message"]["replyTo"]["sender"] == {"source": "contact"}

    def test_an_unquoted_media_turn_has_no_reply_to_key(
        self, client, session_factory, stub_console_and_media_seams, monkeypatch,
    ):
        respond_io_id, _ = _seeded_contact_and_media_limit(session_factory)
        _run_inline(monkeypatch)
        _extract_ok(monkeypatch)
        seen = _spy_run_turn(monkeypatch)

        resp = _post_media(client, respond_io_id)
        assert resp.status_code == 200, resp.text
        assert "replyTo" not in seen[0]["message"]["message"]
