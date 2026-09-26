"""A contact's turns are answered in WhatsApp SEND order, not arrival order (issue #1262 round 3).

Mr Loo, 26 Sep 2026: he sent a PHOTO at 14:57:25 (UTC+8) and the word "Stock" at 14:57:29.
n8n forwards a text to `/chat/turn` at once, but runs its own media intake on a photo first
(`sub-media-intake` calls `/external/media/process` and waits ~20 s for the extraction), so
"Stock" reached the CRM first, ran as turn 378 and was answered from yesterday's SRTWC
products. The photo ran as turn 379 twenty seconds later.

The CRM already knows the photo exists when "Stock" arrives: n8n's `/external/media/process`
call wrote the ledger row (`contact_media_usage`) for that message before the text was even
forwarded. And once n8n's media intake is removed (plan S6), both messages reach
`/chat/turn` near together and the photo's row sits in the per-contact queue. Either way the
rule is the same, with no timer: when a turn gets its slot it first answers every
earlier-sent message of this contact the CRM already knows about and has not answered, then
itself. The earlier message's own delivery later comes back `duplicate: true`, so n8n sends
nothing twice.

The last class is the stale-focus guard (round 3 N6 / R3-6): a bare "Stock" with no product,
on a focus left over from an earlier day, asks which product instead of answering yesterday.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope

from tests.chatbot.test_engine import _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_media_intake_turn import (
    _fresh_contact_id,
    _seed_media_limit,
    _seed_settings,
    media_pipeline,  # noqa: F401
)

# Mr Loo's two messages, with the send times respond.io stamped on them (ms since epoch).
# "Stock" is the real envelope's `timestamp` (1790405849000 = 06:57:29Z = 14:57:29 local);
# the photo is the owner's WhatsApp screenshot, 14:57:25 local.
PHOTO_SENT_MS = 1790405845000
STOCK_SENT_MS = 1790405849000
PHOTO_MESSAGE_ID = "1790405845000000"
STOCK_MESSAGE_ID = "1790405849000000"

PHOTO_CODES = ["M72-GM-DIY", "M210-GM", "M227-BL"]
YESTERDAY_CODES = ["SRTWC8516-SH-UF-150-NEW", "SRTWC8517-SH-UF-150-NEW"]

@pytest.fixture(autouse=True)
def _stub_mcp(monkeypatch):
    """No stock rows for any code: these tests are about WHICH products a turn asks
    about and in what order, never about the stock figures."""
    from app.services.ai_assistant_service import MCPRuntimeClient

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"data": []}))


PHOTO_RESULT = {
    "rendered_text": ", ".join(PHOTO_CODES),
    "confirmation_message": None,
    "entities": [{"raw": code} for code in PHOTO_CODES],
    "attributes": [],
    "notes": "Handwritten list of product codes.",
    "truncated": False,
    "needs_clarification": False,
}


def _product(code: str) -> dict[str, Any]:
    return {"raw": code, "canonical_code": code, "hint": "product", "current_message": False}


def _seed_contact(session_factory, contact_id: int, *, focus_codes: list[str]) -> None:
    session_vars = {
        "focus": {"products": [_product(c) for c in focus_codes], "domains": ["inventory"]},
        "open_question": None,
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
    }
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(contact_id), "phone": "+60163281179", "sv": json.dumps(session_vars)},
    )
    db.commit()


def _base_envelope(contact_id: int, *, message_id: str, sent_ms: int, inner: dict[str, Any]) -> Envelope:
    return Envelope(
        contact={"id": contact_id, "firstName": "Mr", "lastName": "Loo"},
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": message_id,
                "timestamp": sent_ms,
                "contactId": contact_id,
                "channelId": 453209,
                "traffic": "incoming",
                "message": inner,
            },
        },
    )


def _stock_envelope(contact_id: int) -> Envelope:
    return _base_envelope(
        contact_id,
        message_id=STOCK_MESSAGE_ID,
        sent_ms=STOCK_SENT_MS,
        inner={"type": "text", "text": "Stock"},
    )


PHOTO_URL = "https://cdn.example/mr-loo-list.jpg"


def _photo_envelope(contact_id: int) -> Envelope:
    return _base_envelope(
        contact_id,
        message_id=PHOTO_MESSAGE_ID,
        sent_ms=PHOTO_SENT_MS,
        inner={
            "type": "attachment",
            "attachment": {"type": "image", "url": PHOTO_URL, "mimeType": "image/jpeg", "size": 98641},
        },
    )


def _n8n_media_intake(session_factory, contact_id: int) -> None:
    """What n8n's `sub-media-intake` does for the photo BEFORE it calls `/chat/turn`: one
    `/external/media/process` call through the real fast path (decide, meter, record,
    enqueue; the `media_pipeline` fixture runs the job inline)."""
    from app.api.v1.external.media import _decide_meter_record_and_enqueue
    from app.schemas.external.media import MediaProcessRequest

    db = session_factory()
    _decide_meter_record_and_enqueue(
        db,
        MediaProcessRequest(
            respond_io_id=str(contact_id),
            message_id=PHOTO_MESSAGE_ID,
            modality="image",
            media_url=PHOTO_URL,
            mime_type="image/jpeg",
            turn_id="17448466",
        ),
    )


def _verdicts_by_message(calls: list[str]):
    """A parser stub that answers by what the message says, and records every user block.

    The photo's turn reads the codes the extraction rendered; "Stock" names nothing and
    reuses the subject, which is exactly what the live parser returned for turn 378
    (inventory / check_stock, 0 entities, `entity_op: reuse`)."""

    def _on_call(user_block: str) -> None:
        calls.append(user_block)

    def _parse(config, user_block):
        _on_call(user_block)
        if "M210-GM" in user_block.split("Current user message:", 1)[-1].split("\n", 1)[0]:
            return _parser_output(
                domain_hint="inventory",
                intent_hint="check_stock",
                entities=[
                    {
                        "raw": code,
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    }
                    for code in PHOTO_CODES
                ],
                entity_op="replace_combine",
            )
        return _parser_output(
            domain_hint="inventory",
            intent_hint="check_stock",
            entities=[],
            entity_op="reuse",
        )

    return _parse


def _install_parser(monkeypatch, calls: list[str]) -> None:
    from app.services.chatbot.head import parser as parser_mod

    monkeypatch.setattr(
        parser_mod,
        "resolve_config",
        lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
        ),
    )
    monkeypatch.setattr(parser_mod, "parse", _verdicts_by_message(calls))


def _message_line(user_block: str) -> str:
    return user_block.split("Current user message:", 1)[-1].split("\n", 1)[0].strip()


def _subject_line(user_block: str) -> str:
    return next((line for line in user_block.splitlines() if line.startswith("Current subject")), "")


def _turn_for(session_factory, contact_id: int, message_id: str) -> ChatbotTurn | None:
    return (
        session_factory()
        .query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == str(contact_id),
            ChatbotTurn.message_id == message_id,
        )
        .order_by(ChatbotTurn.created_at.desc())
        .first()
    )


def _texts(actions: list[dict[str, Any]]) -> list[str]:
    return [str(a.get("text") or "") for a in actions if a.get("kind") == "send_message"]


class TestPhotoStillInN8nMediaIntake:
    """Today's path: n8n is still extracting the photo when "Stock" reaches `/chat/turn`."""

    def test_mr_loo_photo_is_answered_first_and_stock_applies_to_its_products(
        self, session_factory, stub_access, media_pipeline, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(PHOTO_RESULT)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        # 14:57:25 photo sent -> n8n starts its own media intake (the ledger row exists).
        _n8n_media_intake(session_factory, contact_id)
        # 14:57:29 "Stock" sent -> forwarded at once, reaches /chat/turn FIRST.
        result = engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)

        assert [_message_line(c) for c in calls][:1] == [", ".join(PHOTO_CODES)], (
            "the photo, sent 4 s before 'Stock', must be answered first; the parser saw "
            f"{[_message_line(c) for c in calls]}"
        )
        assert len(calls) == 2, [_message_line(c) for c in calls]
        stock_subject = _subject_line(calls[1])
        assert "M210-GM" in stock_subject, (
            f"'Stock' must apply to the photo's products, not yesterday's: {stock_subject!r}"
        )
        assert "SRTWC8517" not in stock_subject, stock_subject

        photo_row = _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID)
        assert photo_row is not None, "the photo was answered, so it has its own turn row"
        assert photo_row.status == "done", (photo_row.status, photo_row.error)

        texts = _texts(result.actions)
        assert len(texts) >= 2, texts
        assert "M210-GM" in texts[0], f"the photo's reply is sent first: {texts}"

    def test_the_photos_own_late_delivery_is_a_duplicate_and_sends_nothing(
        self, session_factory, stub_access, media_pipeline, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(PHOTO_RESULT)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        _n8n_media_intake(session_factory, contact_id)
        engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)
        parsed = len(calls)

        # ~20 s later n8n's own intake finishes and it calls /chat/turn for the photo.
        late = engine_mod.run_turn(_photo_envelope(contact_id), session_factory=session_factory)

        assert late.duplicate is True
        assert len(calls) == parsed, "the photo must not be parsed or answered a second time"

    def test_an_old_ledger_row_already_behind_a_later_turn_is_not_replayed(
        self, session_factory, stub_access, media_pipeline, monkeypatch
    ):
        """Bound, with no clock: only a media message the CRM heard about AFTER this
        contact's previous turn is 'earlier and unanswered'. A photo n8n answered on its
        own reply arm last week (no turn row) must never be answered again today."""
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=[])
        _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(PHOTO_RESULT)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        _n8n_media_intake(session_factory, contact_id)
        db = session_factory()
        db.execute(
            text("UPDATE contact_media_usage SET created_at = :t WHERE respond_io_id = :c"),
            {"t": datetime.now() - timedelta(days=7), "c": str(contact_id)},
        )
        db.commit()
        # A turn after that photo (last week's answered text).
        engine_mod.run_turn(
            _base_envelope(
                contact_id, message_id="ZZT-old", sent_ms=STOCK_SENT_MS - 86_400_000,
                inner={"type": "text", "text": "hello"},
            ),
            session_factory=session_factory,
        )
        calls.clear()

        engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)

        assert [_message_line(c) for c in calls] == ["Stock"], [_message_line(c) for c in calls]
        assert _turn_for(session_factory, contact_id, PHOTO_MESSAGE_ID) is None


class TestBothInThePerContactQueue:
    """After plan S6 both messages reach `/chat/turn` near together. The queue is still
    taken in arrival order; the turn that gets the slot first answers the earlier-SENT
    message that is waiting behind it, then itself."""

    def test_a_queued_earlier_sent_message_is_answered_before_the_one_holding_the_slot(
        self, session_factory, stub_access, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        # The photo arrived second and is still waiting for its slot: its row exists, at
        # stage `queued`, exactly as `run_turn` leaves it before `wait_for_turn` returns.
        photo = _base_envelope(
            contact_id,
            message_id=PHOTO_MESSAGE_ID,
            sent_ms=PHOTO_SENT_MS,
            inner={"type": "text", "text": ", ".join(PHOTO_CODES)},
        )
        db = session_factory()
        waiting = engine_mod._insert_turn(db, envelope=photo, contact_respond_id=str(contact_id), queued=True)
        waiting_id = str(waiting.id)

        result = engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)

        assert [_message_line(c) for c in calls] == [", ".join(PHOTO_CODES), "Stock"]
        assert "M210-GM" in _subject_line(calls[1])
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == waiting_id).first()
        assert row.status == "done", (row.status, row.stage, row.error)
        assert "M210-GM" in _texts(result.actions)[0]

        # Its own request, once it gets the slot, finds the row answered.
        assert engine_mod._claim_own_row(session_factory, waiting_id) is False

    def test_a_queued_later_sent_message_is_left_for_its_own_request(
        self, session_factory, stub_access, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        stub_access()
        calls: list[str] = []
        _install_parser(monkeypatch, calls)

        later = _base_envelope(
            contact_id,
            message_id="ZZT-later",
            sent_ms=STOCK_SENT_MS + 5000,
            inner={"type": "text", "text": "thanks"},
        )
        db = session_factory()
        waiting = engine_mod._insert_turn(db, envelope=later, contact_respond_id=str(contact_id), queued=True)

        engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)

        assert [_message_line(c) for c in calls] == ["Stock"]
        assert engine_mod._claim_own_row(session_factory, str(waiting.id)) is True


def _seed_previous_turn(session_factory, contact_id: int, *, days_ago: int) -> None:
    db = session_factory()
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.add(
        ChatbotTurn(
            contact_respond_id=str(contact_id),
            message_id=f"ZZT-prev-{days_ago}",
            envelope={},
            status="done",
            stage="sent",
            created_at=when,
            started_at=when,
            finished_at=when,
        )
    )
    db.commit()


class TestStaleFocusOnABareDomainWord:
    """Round 3 N6 / R3-6, turn 378: "Stock" alone, with only yesterday's products in focus."""

    def _stock_only(self, session_factory, contact_id, monkeypatch):
        calls: list[str] = []
        _install_parser(monkeypatch, calls)
        result = engine_mod.run_turn(_stock_envelope(contact_id), session_factory=session_factory)
        return result, calls

    def test_turn_378_bare_stock_on_yesterdays_focus_asks_which_product(
        self, session_factory, stub_access, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        _seed_previous_turn(session_factory, contact_id, days_ago=1)
        stub_access()

        result, calls = self._stock_only(session_factory, contact_id, monkeypatch)

        texts = " ".join(_texts(result.actions))
        assert "SRTWC8516" not in texts and "SRTWC8517" not in texts, (
            f"a bare 'Stock' must not answer yesterday's products: {texts!r}"
        )
        assert "which product" in texts.lower(), texts

    def test_bare_stock_on_a_focus_named_today_still_answers_it(
        self, session_factory, stub_access, monkeypatch
    ):
        contact_id = _fresh_contact_id()
        _seed_contact(session_factory, contact_id, focus_codes=YESTERDAY_CODES)
        _seed_previous_turn(session_factory, contact_id, days_ago=0)
        stub_access()

        result, calls = self._stock_only(session_factory, contact_id, monkeypatch)

        assert "SRTWC8517" in _subject_line(calls[0])
        assert "which product" not in " ".join(_texts(result.actions)).lower()
