"""S6 tester triage (coordinator instruction, 16 Sep 2026): `console_service._borrow_envelope`
must borrow only from a REAL inbound envelope (`ingress == "webhook"` and `is_test == False`),
never from a console/test turn's own recorded envelope.

Measured defect on the hand-pass clone: a console smoke turn stored an envelope with
`contact.custom_fields: []`, and every LATER console turn for that contact borrowed THAT
envelope - `_borrow_envelope`'s query orders by `created_at DESC` with no `ingress`/`is_test`
filter, so the newest row wins regardless of which world wrote it - instead of the real
WhatsApp delivery's envelope. `engine._stock_check_denied` then read `is_allowed_stock` as
missing (the console envelope never carried it) and routed "check stock srtwc286" to
`demand_qty` on the owner's own hand pass, not `stock_denied`.

Two cases:
1. A webhook/live row and a NEWER console/test row both exist for one contact - the webhook
   row's envelope must still be the one borrowed, even though it is older.
2. Only console/test rows exist for a contact (no real delivery on record) - `_borrow_envelope`
   must raise `ConsoleContactUnknown`, the same as a contact with no rows at all, rather than
   silently handing back a console turn's own envelope.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot.console_service import ConsoleContactUnknown, _borrow_envelope

CONTACT_ID = "555001001"


def _seed_turn(
    session_factory,
    *,
    contact_id: str,
    ingress: str,
    is_test: bool,
    custom_fields: list[dict],
    created_at,
    message_id,
):
    db = session_factory()
    envelope = {
        "contact": {"id": int(contact_id), "firstName": "ZZT", "custom_fields": custom_fields},
        "message": {
            "event_type": "message.received",
            "contact": {"id": int(contact_id)},
            "message": {
                "messageId": message_id or "ZZT-console-msg",
                "contactId": int(contact_id),
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "check stock srtwc286"},
            },
        },
    }
    row = ChatbotTurn(
        contact_respond_id=contact_id,
        message_id=message_id,
        ingress=ingress,
        envelope=envelope,
        is_test=is_test,
        status="done" if ingress == "webhook" else "processing",
        stage="sent",
        branch_kind="business_query",
        created_at=created_at,
    )
    db.add(row)
    db.commit()


class TestBorrowEnvelopeIgnoresConsoleAndTestTurns:
    def test_borrows_the_real_webhook_envelope_not_a_newer_console_one(self, session_factory):
        now = datetime.now(timezone.utc)
        _seed_turn(
            session_factory,
            contact_id=CONTACT_ID,
            ingress="webhook",
            is_test=False,
            custom_fields=[{"name": "is_allowed_stock", "value": "true"}],
            created_at=now - timedelta(hours=1),
            message_id="ZZT-real-msg",
        )
        _seed_turn(
            session_factory,
            contact_id=CONTACT_ID,
            ingress="console",
            is_test=True,
            custom_fields=[],
            created_at=now,
            message_id=None,
        )

        db = session_factory()
        envelope = _borrow_envelope(db, CONTACT_ID)

        assert envelope["contact"]["custom_fields"] == [
            {"name": "is_allowed_stock", "value": "true"}
        ], (
            "borrowed the newer console/test turn's envelope instead of the real webhook "
            f"one: {envelope['contact']['custom_fields']!r}"
        )

    def test_only_console_or_test_rows_on_record_raises_contact_unknown(self, session_factory):
        now = datetime.now(timezone.utc)
        _seed_turn(
            session_factory,
            contact_id=CONTACT_ID,
            ingress="console",
            is_test=True,
            custom_fields=[],
            created_at=now,
            message_id=None,
        )

        db = session_factory()
        with pytest.raises(ConsoleContactUnknown):
            _borrow_envelope(db, CONTACT_ID)
