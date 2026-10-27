"""CHAT-SPEED direct ingress, what is left after CHAT-INBOX-QUEUE (UAC AC-6..AC-10).

The webhook-started turn job (`chat_turns.run_direct_turn_job`) is gone: a covered message
is queued and answered by the inbox drain (`tests/chatbot/test_inbox_queue_*.py` covers the
send, the takeover check and the failures). What stays here is the engine's ordering of an
n8n copy and the switch and workspace helpers the queue reuses.

Real, committed Postgres via `SessionLocal`, like `test_d15_duplicate_race.py`. Rows are
`ZZT-` prefixed and removed by hand.
"""
from __future__ import annotations

import json
import time
import types
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.models.integration import IntegrationLog
from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod
from app.utils.field_encryption import encrypt_secret
from tests.chatbot.test_engine import _parser_output

SENDER_URL = "https://automate-zzt.example.com/webhook/chatbot-sender"
SENDER_KEY = "ZZT-plain-sender-key-0001"


def _message_id(age_seconds: float = 1.0) -> str:
    return str(int((time.time() - age_seconds) * 1_000_000))


def _payload(contact: str, message_id: str, text_value: str = "price for SRTWC8517") -> dict:
    """A respond.io `message.received` body, as the webhook enqueues it."""
    return {
        "event_type": "message.received",
        "contact": {
            "id": contact,
            "firstName": "ZZT",
            "phone": "+60000000901",
            "custom_fields": [{"name": "is_human_intervened", "value": None}],
        },
        "message": {
            "messageId": message_id,
            "contactId": contact,
            "channelId": 12,
            "traffic": "incoming",
            "timestamp": int(message_id) // 1000,
            "message": {"type": "text", "text": text_value},
            "sender": {"source": "contact"},
        },
        "channel": {"id": 12, "source": "whatsapp_cloud"},
    }


def _n8n_copy(payload: dict) -> Envelope:
    """What the n8n producer + dispatcher post to `/chat/turn` for the same message."""
    return Envelope(message=payload, contact=payload["contact"], ingress="webhook")


@pytest.fixture()
def contacts():
    """Seeds committed `respond_contacts` rows; deletes them and their turns afterwards."""
    made: list[str] = []

    def _seed(suffix: str) -> str:
        cid = f"ZZT-direct-{suffix}-{uuid.uuid4().hex[:6]}"
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
                ),
                # A phone of its own: `respond_contacts.phone_number` is UNIQUE, and the
                # suite runs files in parallel against one database.
                {"cid": cid, "phone": f"+600{uuid.uuid4().int % 10**9:09d}", "sv": json.dumps({"variables": {}})},
            )
            db.commit()
        finally:
            db.close()
        made.append(cid)
        return cid

    yield _seed

    db = SessionLocal()
    try:
        for cid in made:
            db.query(ChatbotTurn).filter(ChatbotTurn.contact_respond_id == cid).delete(
                synchronize_session=False
            )
            db.query(IntegrationLog).filter(IntegrationLog.external_reference == cid).delete(
                synchronize_session=False
            )
            db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid})
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def stub_engine_seams(monkeypatch):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: _parser_output())
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    # The AI-allowed gate reads company membership; the seeded contacts belong to nobody.
    monkeypatch.setattr(engine_mod, "_ai_allowed", lambda session_factory, contact: True)


@pytest.fixture(autouse=True)
def lookup(monkeypatch):
    """The respond.io contact lookup the job makes before the turn (n8n's findcontact).
    `records[contact]` is what respond.io returns; a missing entry is a failed lookup."""
    records: dict[str, Any] = {}
    calls: list[str] = []

    def _fake(db, contact_id):
        calls.append(contact_id)
        return records.get(contact_id, {
            "id": contact_id,
            "firstName": "ZZT",
            "phone": "+60000000901",
            "custom_fields": [{"name": "is_human_intervened", "value": "false"}],
        })

    monkeypatch.setattr(direct_ingress, "_lookup_contact", _fake)
    return types.SimpleNamespace(records=records, calls=calls)


@pytest.fixture()
def sender(monkeypatch):
    """A configured sender on the default workspace, and every POST it receives."""
    workspace = types.SimpleNamespace(
        chatbot_sender_url=SENDER_URL,
        chatbot_sender_key_ciphertext=encrypt_secret(SENDER_KEY),
    )
    monkeypatch.setattr(direct_ingress, "_default_workspace", lambda db: workspace)
    monkeypatch.setattr(direct_ingress, "assert_safe_outbound_url", lambda url, label: None)
    posts: list[dict[str, Any]] = []
    state = {"status": 200, "raise": None}

    def _fake_post(url, **kwargs):
        posts.append({"url": url, **kwargs})
        if state["raise"] is not None:
            raise state["raise"]
        return httpx.Response(state["status"], text="ok", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _fake_post)
    return types.SimpleNamespace(workspace=workspace, posts=posts, state=state)


def _turns(contact: str) -> list[ChatbotTurn]:
    db = SessionLocal()
    try:
        return (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == contact)
            .order_by(ChatbotTurn.created_at)
            .all()
        )
    finally:
        db.close()


def _outbound_logs(contact: str) -> list[IntegrationLog]:
    db = SessionLocal()
    try:
        return (
            db.query(IntegrationLog)
            .filter(
                IntegrationLog.external_reference == contact,
                IntegrationLog.direction == "outbound",
            )
            .all()
        )
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# AC-6: run, send, then the n8n copy is a duplicate
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# AC-7: nothing to send
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# AC-8 / AC-9: a failed or refused send is visible, never raised
# --------------------------------------------------------------------------- #


def _trace_stages(turn: ChatbotTurn) -> list[dict]:
    return [r for r in (turn.trace or []) if isinstance(r, dict) and r.get("stage") == "sent"]


# --------------------------------------------------------------------------- #
# AC-10: ordered per contact even with S7 ordering off
# --------------------------------------------------------------------------- #


def test_n8n_copy_with_s7_off_still_takes_no_ticket(contacts, stub_engine_seams, monkeypatch):
    """With direct ingress off for the contact, an n8n turn is unordered exactly as today."""
    from app.services.chatbot import dispatch

    monkeypatch.setattr(engine_mod, "_s7_mode", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        dispatch, "contact_ticket", lambda *a, **k: pytest.fail("ticket taken with S7 off")
    )
    contact = contacts("n8n-off")
    result = engine_mod.run_turn(
        _n8n_copy(_payload(contact, _message_id())), session_factory=SessionLocal
    )
    assert result.duplicate is False


def _switches_with(real, *, mode: str, contacts: str):
    """`_read_switches` with the direct-ingress fields overridden: the committed test DB's
    settings row is shared, so the switch is set on the snapshot, never on the row."""
    import dataclasses

    def _read(db):
        return dataclasses.replace(
            real(db), chatbot_direct_ingress_mode=mode, chatbot_direct_ingress_contacts=contacts
        )

    return _read


# --------------------------------------------------------------------------- #
# The producer's takeover gate, read through the contact lookup
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Security review L3: the sender speaks for the DEFAULT workspace only
# --------------------------------------------------------------------------- #


def test_on_default_workspace_reads_the_contacts_own_workspace():
    from app.models.access import RespondContact
    from app.schemas.respond_workspace import RespondWorkspaceCreate
    from app.services.respond_workspace_service import RespondWorkspaceService
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        svc = RespondWorkspaceService(db)
        default = svc.create(RespondWorkspaceCreate(space_id="ZZT-ws-default", api_key="k", is_default=True))
        other = svc.create(RespondWorkspaceCreate(space_id="ZZT-ws-other", api_key="k"))
        for cid, ws in (("ZZT-c-default", default.id), ("ZZT-c-other", other.id), ("ZZT-c-none", None)):
            db.add(RespondContact(
                respond_io_id=cid, phone_number=f"+600{uuid.uuid4().int % 10**9:09d}", workspace_id=ws
            ))
        db.commit()

        assert direct_ingress._on_default_workspace(db, "ZZT-c-default") is True
        assert direct_ingress._on_default_workspace(db, "ZZT-c-none") is True
        assert direct_ingress._on_default_workspace(db, "ZZT-c-unknown") is True
        assert direct_ingress._on_default_workspace(db, "ZZT-c-other") is False


# --------------------------------------------------------------------------- #
# Review B1 / S3 / S5
# --------------------------------------------------------------------------- #


def test_read_switches_carries_the_direct_ingress_fields():
    """B1: the engine's per-turn snapshot is a manual builder; the ordering rule reads it."""
    from app.models.user import SystemSetting
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        db.add(SystemSetting(
            id=str(uuid.uuid4()), name="ZZT Co",
            chatbot_direct_ingress_mode="contacts", chatbot_direct_ingress_contacts="ZZT-a\nZZT-b",
        ))
        db.commit()
        switches = engine_mod._read_switches(db)
        assert switches.chatbot_direct_ingress_mode == "contacts"
        assert switches.chatbot_direct_ingress_contacts == "ZZT-a\nZZT-b"
        assert direct_ingress.covers(switches, "ZZT-b") is True
        assert direct_ingress.covers(switches, "ZZT-c") is False


