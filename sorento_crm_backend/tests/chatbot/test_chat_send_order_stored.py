"""CHAT-SEND-ORDER: an earlier-SENT photo is answered before a later text, by send time.

Prod, 24 Oct ~08:15 MYT: a customer forwarded a product IMAGE (a card printed with one product
code), then seconds later the TEXT "Pls check stock". respond.io delivered the image late, so
the text reached the CRM first and its turn answered the product held from an earlier chat;
two replies went out, the wrong one first.

When the text's turn runs, the CRM has usually already STORED the photo: its own respond.io
webhook writes every message to `chat_histories` on arrival. The photo is not yet at
`/chat/turn` and n8n's media intake has not touched it, so neither of #1262's sources (a queued
turn row, a media ledger row) sees it. This lane adds that stored row as a third source.

Owner ruling 24 Oct (option c): no timer, no waiting window, no merge. Every message keeps its
own turn and its own reply; only the order changes. The plan:
`documentation/plans/chatbot/PLAN-chat-send-order.md`.

No real names, phone numbers or respond ids: every id here is synthetic.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chat_history import ChatHistory
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import send_order
from app.services.chatbot.contracts import Envelope

from tests.chatbot.test_engine import _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_media_intake_turn import (
    _fresh_contact_id,
    _seed_media_limit,
    _seed_settings,
    media_pipeline,  # noqa: F401
)
from tests.chatbot.test_turn_order_by_send_time import (
    _base_envelope,
    _message_line,
    _seed_contact,
    _subject_line,
    _texts,
    _turn_for,
)

# One whole second of respond.io's clock. `timestamp` on a real envelope is whole seconds in
# ms; the message id carries the microseconds.
SECOND = 1792807500
PHOTO_MESSAGE_ID = str(SECOND * 1_000_000 - 4_000_000)  # sent 4 s before the text
TEXT_MESSAGE_ID = str(SECOND * 1_000_000)
TEXT_SENT_MS = SECOND * 1000
PHOTO_SENT_MS = TEXT_SENT_MS - 4000

CARD_CODE = "SRTWC2350-P-RL"
HELD_CODE = "SRT6638"
PHOTO_URL = "https://cdn.example/zzt-card.jpg"

CARD_RESULT = {
    "rendered_text": CARD_CODE,
    "confirmation_message": None,
    "entities": [{"raw": CARD_CODE}],
    "attributes": [],
    "notes": "A product card with one printed code.",
    "truncated": False,
    "needs_clarification": False,
}


@pytest.fixture(autouse=True)
def _stub_mcp(monkeypatch):
    from app.services.ai_assistant_service import MCPRuntimeClient

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"data": []}))


def _text_envelope(contact_id: int, *, message_id: str = TEXT_MESSAGE_ID, sent_ms: int = TEXT_SENT_MS) -> Envelope:
    return _base_envelope(
        contact_id, message_id=message_id, sent_ms=sent_ms, inner={"type": "text", "text": "Pls check stock"}
    )


def _photo_envelope(contact_id: int) -> Envelope:
    return _base_envelope(
        contact_id,
        message_id=PHOTO_MESSAGE_ID,
        sent_ms=PHOTO_SENT_MS,
        inner={"type": "attachment", "attachment": {"type": "image", "url": PHOTO_URL, "mimeType": "image/jpeg"}},
    )


def _store(
    session_factory,
    contact_id: int,
    *,
    message_id: str,
    media_type: str | None = "image",
    media_url: str | None = PHOTO_URL,
    traffic: str = "incoming",
    message: str | None = None,
    file_name: str | None = None,
    channel: str = "whatsapp",
    sender_source: str = "contact",
) -> None:
    """What the CRM's respond.io webhook writes for a message on arrival
    (`respond_webhook.map_webhook_message` -> `upsert_message_row`)."""
    if message is None:
        # The webhook's typed placeholder for a media message with no text
        # (`conversation_thread_service._respond_item_text`).
        label = f"[{media_type}]" if media_type else ""
        message = f"{label} {file_name}" if file_name else label
    sent_at = datetime.fromtimestamp(int(message_id) / 1_000_000, tz=timezone.utc).replace(tzinfo=None)
    db = session_factory()
    db.add(
        ChatHistory(
            channel=channel,
            contact_id=str(contact_id),
            phone_number="+60100000000",
            message=message,
            sent_at=sent_at,
            type=traffic,
            message_id=message_id,
            media_url=media_url,
            media_type=media_type,
            media_file_name=file_name,
            sender_source=sender_source,
        )
    )
    db.commit()


def _install_parser(monkeypatch, calls: list[str]) -> None:
    """The photo's turn reads the code the extraction rendered; "Pls check stock" names
    nothing and reuses the subject."""
    from app.services.chatbot.head import parser as parser_mod

    monkeypatch.setattr(
        parser_mod,
        "resolve_config",
        lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
        ),
    )

    def _parse(config, user_block):
        calls.append(user_block)
        if CARD_CODE in _message_line(user_block):
            return _parser_output(
                domain_hint="inventory",
                intent_hint="check_stock",
                entities=[
                    {
                        "raw": CARD_CODE,
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    }
                ],
                entity_op="replace_combine",
            )
        return _parser_output(domain_hint="inventory", intent_hint="check_stock", entities=[], entity_op="reuse")

    monkeypatch.setattr(parser_mod, "parse", _parse)


def _media_ready(session_factory, contact_id: int, media_pipeline) -> None:  # noqa: F811
    _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
    _seed_settings(session_factory, media_sync_wait_seconds=5)
    media_pipeline.set_result(CARD_RESULT)


class TestProdCase24Oct:
    """The photo is stored, not yet at `/chat/turn`, and n8n has not started reading it."""

    def test_the_stored_photo_is_answered_first_and_the_text_answers_its_product(
        self, session_factory, stub_access, media_pipeline, monkeypatch  # noqa: F811
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        _media_ready(session_factory, contact_id, media_pipeline)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        # The CRM webhook stored the photo (respond.io delivered it late, but before the
        # text's turn got going). The text reaches /chat/turn first.
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        result = engine_mod.run_turn(_text_envelope(contact_id), session_factory=session_factory)

        lines = [_message_line(c) for c in calls]
        assert lines[:1] == [CARD_CODE], f"the photo, sent first, is answered first; parser saw {lines}"
        assert len(calls) == 2, lines
        subject = _subject_line(calls[1])
        assert CARD_CODE in subject, f"'Pls check stock' answers the photo's product: {subject!r}"
        assert HELD_CODE not in subject, subject

        photo_row = _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID)
        assert photo_row is not None, "the photo is answered on its own turn row"
        assert photo_row.status == "done", (photo_row.status, photo_row.error)
        texts = _texts(result.actions)
        assert len(texts) >= 2, texts
        assert texts[0] == _texts(photo_row.response["actions"])[0], "the photo's reply goes out first"

        from app.models.media import MediaExtractionJob

        job = session_factory().query(MediaExtractionJob).filter(MediaExtractionJob.media_url == PHOTO_URL).all()
        assert [j.caption for j in job] == [None], "the webhook's '[image]' placeholder is not a caption"

    def test_the_photos_own_late_delivery_is_a_duplicate_read_and_charged_once(
        self, session_factory, stub_access, media_pipeline, monkeypatch  # noqa: F811
    ):
        from app.models.media import ContactMediaUsage, MediaExtractionJob

        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        _media_ready(session_factory, contact_id, media_pipeline)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        engine_mod.run_turn(_text_envelope(contact_id), session_factory=session_factory)
        parsed = len(calls)

        late = engine_mod.run_turn(_photo_envelope(contact_id), session_factory=session_factory)

        assert late.duplicate is True
        assert len(calls) == parsed, "the photo is not parsed or answered a second time"
        db = session_factory()
        usage = (
            db.query(ContactMediaUsage)
            .filter(
                ContactMediaUsage.respond_io_id == str(contact_id),
                ContactMediaUsage.message_id == PHOTO_MESSAGE_ID,
            )
            .all()
        )
        assert len(usage) == 1, [(u.outcome, u.created_at) for u in usage]
        assert db.query(MediaExtractionJob).filter(MediaExtractionJob.usage_id == usage[0].id).count() == 1

    def test_a_dry_run_never_answers_a_stored_customer_message(
        self, session_factory, stub_access, media_pipeline, monkeypatch  # noqa: F811
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        _media_ready(session_factory, contact_id, media_pipeline)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        envelope = _text_envelope(contact_id).model_copy(update={"is_test": True})
        engine_mod.run_turn(envelope, session_factory=session_factory)

        assert [_message_line(c) for c in calls] == ["Pls check stock"]
        assert _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID) is None


class TestSameSecond:
    """15 Oct shape: a photo and a text sent inside one second carry the SAME `timestamp`
    (whole seconds, in ms). The message id's microseconds decide which was sent first."""

    def test_a_queued_photo_sent_earlier_in_the_same_second_is_answered_first(
        self, session_factory, stub_access, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        photo_id = str(SECOND * 1_000_000 + 200_000)
        text_id = str(SECOND * 1_000_000 + 700_000)
        # The photo already read upstream (rendered as its code), waiting at `queued`.
        photo = _base_envelope(
            contact_id, message_id=photo_id, sent_ms=TEXT_SENT_MS, inner={"type": "text", "text": CARD_CODE}
        )
        db = session_factory()
        waiting = engine_mod._insert_turn(db, envelope=photo, contact_respond_id=str(contact_id), queued=True)

        engine_mod.run_turn(
            _text_envelope(contact_id, message_id=text_id, sent_ms=TEXT_SENT_MS), session_factory=session_factory
        )

        assert [_message_line(c) for c in calls] == [CARD_CODE, "Pls check stock"]
        assert CARD_CODE in _subject_line(calls[1])
        assert engine_mod._claim_own_row(session_factory, str(waiting.id)) is False

    def test_a_stored_photo_sent_earlier_in_the_same_second_is_found(self, session_factory):
        contact_id = _fresh_contact_id()
        photo_id = str(SECOND * 1_000_000 + 200_000)
        _store(session_factory, contact_id, message_id=photo_id)
        me = _me(session_factory, contact_id, message_id=str(SECOND * 1_000_000 + 700_000))

        found = send_order.earlier_unanswered(session_factory(), contact_respond_id=str(contact_id), me=me)

        assert [e.message_id for e in found] == [photo_id]


def _me(session_factory, contact_id: int, *, message_id: str = TEXT_MESSAGE_ID, dry_run: bool = False) -> ChatbotTurn:
    envelope = _text_envelope(contact_id, message_id=message_id)
    if dry_run:
        envelope = envelope.model_copy(update={"is_test": True})
    return engine_mod._insert_turn(session_factory(), envelope=envelope, contact_respond_id=str(contact_id))


def _found(session_factory, contact_id: int, me: ChatbotTurn) -> list[str | None]:
    return [
        e.message_id
        for e in send_order.earlier_unanswered(session_factory(), contact_respond_id=str(contact_id), me=me)
    ]


class TestStoredOnlyDiscovery:
    """Which stored rows count as an earlier, unanswered message on its way."""

    @pytest.mark.parametrize(
        ("media_type", "file_name"),
        [("audio", None), ("file", "zzt-price-list.pdf"), ("sticker", None), ("image", None)],
    )
    def test_each_media_type_is_found_and_rebuilt_with_its_own_attachment(
        self, session_factory, media_type, file_name
    ):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID, media_type=media_type, file_name=file_name)
        me = _me(session_factory, contact_id)

        found = send_order.earlier_unanswered(session_factory(), contact_respond_id=str(contact_id), me=me)

        assert [e.message_id for e in found] == [PHOTO_MESSAGE_ID]
        mine = _text_envelope(contact_id).model_dump(mode="json")
        rebuilt = Envelope.model_validate(send_order.stored_envelope(mine, found[0]))
        inner = rebuilt.message["message"]
        assert inner["messageId"] == PHOTO_MESSAGE_ID
        assert inner["timestamp"] == PHOTO_SENT_MS
        attachment = inner["message"]["attachment"]
        assert inner["message"]["type"] == "attachment"
        assert attachment["type"] == media_type
        assert attachment["url"] == PHOTO_URL
        if file_name:
            assert attachment["fileName"] == file_name
        assert rebuilt.contact["id"] == contact_id
        # Only a photo or a voice note can sit in the media poll.
        assert found[0].carries_media is (media_type in ("image", "audio"))

    def test_a_stored_text_row_is_not_answered_ahead(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID, media_type=None, media_url=None, message="hi")
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_media_row_with_no_url_is_not_answered_ahead(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID, media_url=None)
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_an_outgoing_row_is_not_answered_ahead(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID, traffic="outgoing")
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_later_sent_row_is_left_for_its_own_turn(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=str(int(TEXT_MESSAGE_ID) + 1_000_000))
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_this_turns_own_row_is_not_found(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=TEXT_MESSAGE_ID)
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_row_that_already_has_a_turn_is_not_found(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        engine_mod._insert_turn(
            session_factory(), envelope=_photo_envelope(contact_id), contact_respond_id=str(contact_id)
        )
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_row_n8n_media_intake_has_touched_is_left_to_the_ledger_rule(self, session_factory):
        """Once a ledger row exists, #1262's ledger rule owns the photo (a finished job may
        already have been answered on n8n's own reply arm)."""
        from app.models.media import ContactMediaUsage

        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        db = session_factory()
        db.add(
            ContactMediaUsage(
                respond_io_id=str(contact_id),
                message_id=PHOTO_MESSAGE_ID,
                modality="image",
                period_key="2026-10",
                outcome="rejected",
            )
        )
        db.commit()
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_row_older_than_the_lookback_is_history(self, session_factory):
        contact_id = _fresh_contact_id()
        old = int(TEXT_MESSAGE_ID) - int((send_order.STORED_LOOKBACK_SECONDS + 1) * 1_000_000)
        _store(session_factory, contact_id, message_id=str(old))
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_row_sent_before_the_latest_answered_turn_is_history(self, session_factory):
        """A media message the bot never took (a human had the chat) followed by an answered
        turn is not on its way."""
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        answered_id = str(int(PHOTO_MESSAGE_ID) + 1_000_000)
        now = datetime.now(timezone.utc)
        db = session_factory()
        db.add(
            ChatbotTurn(
                contact_respond_id=str(contact_id),
                message_id=answered_id,
                envelope=_base_envelope(
                    contact_id, message_id=answered_id, sent_ms=PHOTO_SENT_MS + 1000, inner={"type": "text", "text": "ok"}
                ).model_dump(mode="json"),
                status="done",
                stage="sent",
                started_at=now - timedelta(seconds=2),
                finished_at=now - timedelta(seconds=1),
            )
        )
        db.commit()
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_another_contacts_row_is_never_found(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id + 1, message_id=PHOTO_MESSAGE_ID)
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_dry_run_turn_finds_nothing(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        assert _found(session_factory, contact_id, _me(session_factory, contact_id, dry_run=True)) == []


def test_send_key_prefers_the_message_id_microseconds():
    """`envelope.message` is the webhook body; the id and timestamp sit on its `message`."""
    body = {"message": {"messageId": str(SECOND * 1_000_000 + 250_000), "timestamp": TEXT_SENT_MS}}
    assert send_order.send_key_ms(body) == pytest.approx(TEXT_SENT_MS + 250.0)
    # No clock in the id (a test id): the timestamp, as before.
    assert send_order.send_key_ms({"message": {"messageId": "ZZT-x", "timestamp": TEXT_SENT_MS}}) == TEXT_SENT_MS
    assert send_order.send_key_ms({"message": {"messageId": "ZZT-x"}}) is None
    # No timestamp: the id alone. An id outside the timestamp's second: the timestamp.
    assert send_order.send_key_ms({"message": {"messageId": str(SECOND * 1_000_000)}}) == TEXT_SENT_MS
    assert send_order.send_key_ms(
        {"message": {"messageId": str(SECOND * 1_000_000 + 5_000_000), "timestamp": TEXT_SENT_MS}}
    ) == TEXT_SENT_MS


class TestReviewRound2:
    def test_the_photos_read_is_filed_under_its_own_turn(
        self, session_factory, stub_access, media_pipeline, monkeypatch  # noqa: F811
    ):
        """S4: the ledger row (and the stored photo) belong to the photo's turn, not to the
        text's turn that carried its answer."""
        from app.models.media import ContactMediaUsage

        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        _media_ready(session_factory, contact_id, media_pipeline)
        stub_access()
        _install_parser(monkeypatch, [])

        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        engine_mod.run_turn(_text_envelope(contact_id), session_factory=session_factory)

        photo_row = _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID)
        usage = (
            session_factory()
            .query(ContactMediaUsage)
            .filter(
                ContactMediaUsage.respond_io_id == str(contact_id),
                ContactMediaUsage.message_id == PHOTO_MESSAGE_ID,
            )
            .one()
        )
        assert usage.turn_id == str(photo_row.id)

    def test_a_staff_reply_from_the_business_app_hides_it(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        _store(
            session_factory,
            contact_id,
            message_id=str(int(PHOTO_MESSAGE_ID) + 1_000_000),
            traffic="outgoing",
            media_type=None,
            media_url=None,
            message="noted",
            sender_source="echo",
        )
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []


class TestReviewRound1:
    """Reviewer pass 1 on this lane: S1 (read first), S2 (channel), S3 (agent reply), B1."""

    @pytest.mark.parametrize("outcome", ["still_reading", "failed"])
    def test_a_stored_photo_not_read_in_time_is_left_to_its_own_delivery(
        self, session_factory, stub_access, media_pipeline, monkeypatch, outcome  # noqa: F811
    ):
        """n8n's `media-route` replies on its own to a read that fails or runs out, so the
        text's turn never answers such a photo ahead: no turn row, nothing sent for it."""
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[HELD_CODE])
        _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=1)
        if outcome == "failed":
            media_pipeline.set_result(error=RuntimeError("unreadable"))
        else:
            media_pipeline.never_runs()
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        result = engine_mod.run_turn(_text_envelope(contact_id), session_factory=session_factory)

        assert [_message_line(c) for c in calls] == ["Pls check stock"]
        assert _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID) is None
        assert len(_texts(result.actions)) == 1, _texts(result.actions)
        row = _turn_for(session_factory, contact_id, TEXT_MESSAGE_ID)
        facts = next(r for r in row.trace if r.get("stage") == "received").get("facts") or {}
        assert "photo_not_read" in str(facts.get("earlier_left_because")), facts

    def test_a_row_on_another_channel_is_not_found(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID, channel="instagram")
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_row_a_person_answered_is_not_found(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        _store(
            session_factory,
            contact_id,
            message_id=str(int(PHOTO_MESSAGE_ID) + 1_000_000),
            traffic="outgoing",
            media_type=None,
            media_url=None,
            message="noted",
            sender_source="user",
        )
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == []

    def test_a_bot_reply_in_between_does_not_hide_it(self, session_factory):
        contact_id = _fresh_contact_id()
        _store(session_factory, contact_id, message_id=PHOTO_MESSAGE_ID)
        _store(
            session_factory,
            contact_id,
            message_id=str(int(PHOTO_MESSAGE_ID) + 1_000_000),
            traffic="outgoing",
            media_type=None,
            media_url=None,
            message="an earlier answer",
            sender_source="api",
        )
        assert _found(session_factory, contact_id, _me(session_factory, contact_id)) == [PHOTO_MESSAGE_ID]

    @pytest.mark.parametrize(
        ("attachment", "caption"),
        [
            ({"type": "image", "url": PHOTO_URL}, None),
            ({"type": "file", "url": PHOTO_URL, "fileName": "zzt-a.pdf"}, None),
            ({"type": "sticker", "url": PHOTO_URL}, None),
            ({"type": "image", "url": PHOTO_URL, "description": "price for this?"}, "price for this?"),
        ],
    )
    def test_the_caption_survives_the_webhook_and_its_placeholder_is_not_one(
        self, session_factory, attachment, caption
    ):
        """Stored exactly as the respond.io webhook maps it: a captioned photo keeps the
        customer's words (`attachment.description`), a bare one its `[type]` placeholder."""
        from app.api.v1.public.respond_webhook import map_webhook_message
        from app.services.chat_history_ingest_service import upsert_message_row

        contact_id = _fresh_contact_id()
        payload = {
            "event_type": "message.received",
            "contact": {"id": contact_id, "phone": "+60100000000", "firstName": "Zzt"},
            "channel": {"source": "whatsapp_cloud"},
            "message": {
                "messageId": PHOTO_MESSAGE_ID,
                "traffic": "incoming",
                "sender": {"source": "contact"},
                "message": {"type": "attachment", "attachment": attachment},
            },
        }
        db = session_factory()
        row = map_webhook_message(payload, db)
        row.media_url = PHOTO_URL  # the test host is not a respond.io media host
        upsert_message_row(db, row)
        me = _me(session_factory, contact_id)
        found = send_order.earlier_unanswered(session_factory(), contact_respond_id=str(contact_id), me=me)
        assert [e.caption for e in found] == [caption]


# MEDIA-INTAKE-GUARD (3): chat_histories keeps no mime column, so the rebuilt
# attachment names the mime its stored file name shows; with no file name it
# sends none rather than a guess.
@pytest.mark.parametrize(
    "file_name, expected",
    [
        ("invoice.pdf", "application/pdf"),
        ("IMG_0001.JPG", "image/jpeg"),
        ("clip.mp4", "video/mp4"),
        (None, None),
        ("no-extension", None),
    ],
)
def test_stored_attachment_passes_the_stored_mime_type(file_name, expected):
    earlier = send_order.Earlier(
        order_key=1.0,
        message_id="ZZT-msg-1",
        media_url="https://cdn.example/x",
        attachment_type="file" if file_name else "image",
        file_name=file_name,
    )

    attachment = send_order.stored_attachment(earlier)

    assert attachment.get("mimeType") == expected
