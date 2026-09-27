"""Identity S1 fix lane round 2 (#1280): the reviewer pass at 56daafae.

Each test here was run red against 56daafae for the reviewer's failing
scenario before the fix landed:

- B1: the Redis reservation locked on the 5th verify BEFORE comparing, so a
  user really got 4 tries and a right 5th code answered 429.
- B2: a sign-in or portal code sent to a contact's WhatsApp was readable in
  the CRM thread views (Respond lane, local lane, search) and was cached
  into ``chat_histories`` unmasked.
- SF1: the portal OTP job's RQ description (logged at INFO by the worker)
  carried the code.
- SF2: the unknown-email and trashed-user branches of ``/auth/login`` had no
  test pinning the timing-equalising dummy bcrypt check.
- Nit 2: an unknown number skipped the OTP lookup SELECT an eligible one ran.
- Nit 3: a send failure logged the exception text (which can echo the code)
  at WARNING.

Postgres only (``tests/_pg_fixture.py``), one rolled-back transaction per
test.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import bcrypt
import pytest

from app.models.chat_history import ChatHistory
from app.models.respond_template import RespondTemplateDefault
from app.services import conversation_thread_service as thread_svc
from tests._pg_fixture import blank_session, unique_code
from tests.test_identity_s1_phone_signin import (
    _contact,
    _digits,
    _eligible_chain,
    _phone_client,
    _seed_signin_code,
    _user,
    _workspace,
    rate_limit_cleanup,  # noqa: F401 - pytest fixture
)


# --------------------------------------------------------------------------- #
# B1: five wrong attempts per code, not four                                   #
# --------------------------------------------------------------------------- #
def test_r2_b1_fifth_attempt_with_the_right_code_signs_in(rate_limit_cleanup):
    """RED at 56daafae: the 5th call's INCR hit the lock threshold before the
    compare, so the right code on the 5th try answered 429."""
    with blank_session() as db:
        ws, contact, user, digits = _eligible_chain(db)
        rate_limit_cleanup.append(digits)
        with _phone_client(db) as client:
            with patch("app.services.queue_service.enqueue_job"):
                client.post("/api/v1/auth/phone/request-code", json={"phone": digits})
            code = _seed_signin_code(db, contact)
            wrong = "000000" if code != "000000" else "111111"

            lefts = []
            for _ in range(4):
                resp = client.post(
                    "/api/v1/auth/phone/verify", json={"phone": digits, "code": wrong}
                )
                assert resp.status_code == 401, resp.text
                lefts.append(resp.json().get("attempts_left"))
            assert lefts == [4, 3, 2, 1]

            fifth = client.post(
                "/api/v1/auth/phone/verify", json={"phone": digits, "code": code}
            )
            assert fifth.status_code == 200, fifth.text
            assert fifth.json()["id"] == user.id


# --------------------------------------------------------------------------- #
# B2: no sign-in or portal code in any CRM thread surface                      #
# --------------------------------------------------------------------------- #
SIGNIN_CODE = "418273"
PORTAL_CODE = "592046"
TEMPLATE_CODE = "730915"
OTP_TEMPLATE = "zzt_auth_code_r2"


def _thread_contact() -> thread_svc.ThreadContact:
    return thread_svc.ThreadContact(
        respond_io_id=f"ZZT{uuid.uuid4().int % 10**9}",
        phone_number="+60100000002",
        first_name="Zzt",
        last_name="Otp",
    )


def _otp_default(db, use_case: str = "login_otp") -> None:
    db.add(
        RespondTemplateDefault(
            id=str(uuid.uuid4()),
            use_case=use_case,
            template_id=None,
            template_name_snapshot=OTP_TEMPLATE,
            param_mapping={"1": "otp_code"},
        )
    )
    db.flush()


def _respond_items() -> list[dict]:
    """Newest-first, as Respond's list endpoint returns them."""
    return [
        {
            "messageId": 1780751894000000,
            "traffic": "outgoing",
            "message": {"type": "text", "text": "Order 418273 is on its way."},
            "status": [],
        },
        {
            "messageId": 1780751893000000,
            "traffic": "outgoing",
            "message": {
                "type": "whatsapp_template",
                "template": {
                    "name": OTP_TEMPLATE,
                    "components": [
                        {
                            "type": "body",
                            "text": "{{1}} is your verification code.",
                            "parameters": [{"type": "text", "text": TEMPLATE_CODE}],
                        },
                        {
                            "type": "button",
                            "sub_type": "copy_code",
                            "parameters": [{"type": "coupon_code", "coupon_code": TEMPLATE_CODE}],
                        },
                    ],
                },
            },
            "status": [],
        },
        {
            "messageId": 1780751892000000,
            "traffic": "outgoing",
            "message": {
                "type": "text",
                "text": (
                    f"Your Sorento portal verification code is {PORTAL_CODE}. It expires "
                    "in 10 minutes. Please do not share with anyone."
                ),
            },
            "status": [],
        },
        {
            "messageId": 1780751891000000,
            "traffic": "outgoing",
            "message": {
                "type": "text",
                "text": (
                    f"Your Sorento sign-in code is {SIGNIN_CODE}. It expires in 10 "
                    "minutes. Please do not share it with anyone."
                ),
            },
            "status": [],
        },
    ]


def _fake_client(items: list[dict]) -> MagicMock:
    client = MagicMock()
    client.list_messages.return_value = {"items": [dict(i) for i in json.loads(json.dumps(items))]}
    return client


def test_r2_b2_respond_thread_page_and_cache_carry_no_code():
    """RED at 56daafae: the Respond lane returned the items verbatim and
    ``persist_messages`` cached the code into ``chat_histories``."""
    with blank_session() as db:
        _otp_default(db)
        contact = _thread_contact()
        page = thread_svc.fetch_thread_page(
            db, contact, limit=10, client=_fake_client(_respond_items())
        )

        dumped = json.dumps(page)
        for code in (SIGNIN_CODE, PORTAL_CODE, TEMPLATE_CODE):
            # The unrelated order message legitimately carries 418273; the
            # OTP bodies must not.
            assert f"code is {code}" not in dumped
        assert TEMPLATE_CODE not in dumped
        texts = [i["message"].get("text") for i in page["items"]]
        assert "Order 418273 is on its way." in texts, texts

        rows = (
            db.query(ChatHistory)
            .filter(ChatHistory.contact_id == contact.respond_io_id)
            .all()
        )
        assert len(rows) == 4
        stored = " | ".join(r.message or "" for r in rows)
        assert f"code is {SIGNIN_CODE}" not in stored
        assert f"code is {PORTAL_CODE}" not in stored
        assert TEMPLATE_CODE not in stored
        assert "Order 418273 is on its way." in stored


def test_r2_b2_local_lane_and_search_carry_no_code():
    """RED at 56daafae: a row the n8n mirror already wrote with the code in
    it was served verbatim by the local lane and by in-thread search."""
    with blank_session() as db:
        contact = _thread_contact()
        db.add(
            ChatHistory(
                channel="whatsapp",
                contact_id=contact.respond_io_id,
                phone_number=contact.phone_number,
                message=f"Your Sorento sign-in code is {SIGNIN_CODE}. It expires in 10 minutes.",
                sent_at=datetime(2026, 9, 27, 9, 0, 0),
                type="outgoing",
                message_id="1780751891000000",
            )
        )
        db.flush()

        page = thread_svc.fetch_thread_page(db, contact, limit=10)
        assert SIGNIN_CODE not in json.dumps(page)

        found = thread_svc.search_thread(db, contact, q="sign-in code")
        assert found["total"] == 1
        assert SIGNIN_CODE not in json.dumps(found)
        # No digit-by-digit oracle: searching for the code finds nothing.
        assert thread_svc.search_thread(db, contact, q=SIGNIN_CODE)["total"] == 0


def test_r2_b2_external_ingest_stores_no_code():
    """RED at 56daafae: Respond's own outgoing-message trigger mirrors every
    send through n8n into ``POST /external/chat-history/messages``, which
    stored the code as typed."""
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user_or_api_key, get_db, get_external_api_user
    from app.main import app
    from tests._external_auth import external_permissions_granted

    with blank_session() as db:
        ident = f"ZZT{uuid.uuid4().int % 10**9}"

        def _u():
            return {"id": "system"}

        def _db():
            yield db

        app.dependency_overrides[get_external_api_user] = _u
        app.dependency_overrides[get_current_user_or_api_key] = _u
        app.dependency_overrides[get_db] = _db
        try:
            with external_permissions_granted():
                resp = TestClient(app).post(
                    "/api/v1/external/chat-history/messages",
                    json={
                        "channel": "whatsapp",
                        "contact_id": ident,
                        "phone_number": "+60100000003",
                        "message": f"Your Sorento portal verification code is {PORTAL_CODE}.",
                        "sent_at": 1780751906900,
                        "type": "outgoing",
                        "message_id": "1780751906900000",
                    },
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code in (200, 201), resp.text

        row = db.query(ChatHistory).filter(ChatHistory.contact_id == ident).one()
        assert PORTAL_CODE not in (row.message or "")


def test_r2_b2_respond_client_list_messages_carries_no_code():
    """RED at 56daafae: every other surface that reads a contact's messages
    straight from Respond (complaints, stock inquiries, purchase requests,
    ticket drafts, activities, the chatbot) goes through
    ``RespondClient.list_messages``, which returned the code verbatim."""
    from app.services.integration_service import RespondClient

    response = MagicMock()
    response.content = b"x"
    response.json.return_value = {"items": _respond_items()}
    response.raise_for_status.return_value = None
    http = MagicMock()
    http.__enter__.return_value.get.return_value = response

    with blank_session() as db:
        _otp_default(db, "portal_otp")
        with patch("app.services.integration_service.httpx.Client", return_value=http), patch(
            "app.services.otp_redaction.otp_template_code_slots",
            return_value={OTP_TEMPLATE: {1}},
        ):
            payload = RespondClient(api_key="k", base_url="http://respond.test").list_messages(
                "123", limit=10
            )

    dumped = json.dumps(payload)
    assert f"code is {SIGNIN_CODE}" not in dumped
    assert f"code is {PORTAL_CODE}" not in dumped
    assert TEMPLATE_CODE not in dumped
    assert "Order 418273 is on its way." in dumped


# --------------------------------------------------------------------------- #
# SF1: the portal OTP job description carries no code                          #
# --------------------------------------------------------------------------- #
def test_r2_sf1_portal_otp_job_description_carries_no_code():
    """RED at 56daafae: RQ's worker logs ``job.description`` at INFO, and the
    portal enqueue left it at the default, which renders every argument -
    the code included."""
    from rq import Queue

    from app.services.portal_service import PortalService
    from app.services.queue_service import redis_conn
    from app.tasks.respond_io_tasks import send_portal_otp_respond_message

    queue = Queue(f"zzt_r2_{uuid.uuid4().hex[:8]}", connection=redis_conn)
    with blank_session() as db:
        ws = _workspace(db)
        contact = _contact(db, ws, _digits())
        with patch("app.services.queue_service.get_queue", return_value=queue), patch(
            "app.services.queue_service.trigger_drain_async"
        ):
            otp = PortalService(db).create_and_dispatch_otp(
                contact,
                ws.space_id,
                "Your Sorento portal verification code is {code}.",
                send_portal_otp_respond_message,
            )
        try:
            jobs = queue.get_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            code = job.args[3]
            assert otp.id == job.args[0]
            assert code not in (job.description or ""), job.description
            assert "send_portal_otp_respond_message" in (job.description or "")
        finally:
            queue.empty()
            queue.delete(delete_jobs=True)


# --------------------------------------------------------------------------- #
# SF2: unknown and trashed email branches run the dummy bcrypt check           #
# --------------------------------------------------------------------------- #
def _login_client(db):
    return _phone_client(db)


def test_r2_sf2_unknown_email_login_runs_the_dummy_bcrypt_check():
    with blank_session() as db:
        with _login_client(db) as client, patch(
            "bcrypt.checkpw", wraps=bcrypt.checkpw
        ) as mock_checkpw:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": f"{unique_code('nobody')}@x.com".lower(), "password": "whatever-1"},
            )
    assert resp.status_code == 401, resp.text
    mock_checkpw.assert_called_once()


def test_r2_sf2_trashed_user_login_runs_the_dummy_bcrypt_check():
    with blank_session() as db:
        user = _user(db, email=f"{unique_code('trash')}@x.com".lower(), is_trashed=True)
        user.password = bcrypt.hashpw(b"right-password-1", bcrypt.gensalt()).decode()
        db.commit()
        with _login_client(db) as client, patch(
            "bcrypt.checkpw", wraps=bcrypt.checkpw
        ) as mock_checkpw:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "right-password-1"},
            )
    assert resp.status_code == 401, resp.text
    mock_checkpw.assert_called_once()


# --------------------------------------------------------------------------- #
# Nit 2: an unknown number runs the same OTP lookup an eligible one does       #
# --------------------------------------------------------------------------- #
def _count_otp_selects(db, fn) -> int:
    from sqlalchemy import event

    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        low = statement.lower()
        if low.lstrip().startswith("select") and "portal_otp_codes" in low:
            seen.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return len(seen)


def test_r2_nit2_unknown_number_runs_the_same_otp_select_as_an_eligible_one(rate_limit_cleanup):
    """RED at 56daafae: ``attempt_verify`` returned before the OTP SELECT for
    an unknown number, one statement fewer than an eligible one."""
    from app.services import phone_signin_service as svc

    with blank_session() as db:
        ws, contact, user, digits = _eligible_chain(db)
        unknown = _digits()
        rate_limit_cleanup.extend([digits, unknown])
        known = _count_otp_selects(
            db, lambda: svc.attempt_verify(db, digits, "000000", user_agent=None, ip_address=None)
        )
        other = _count_otp_selects(
            db, lambda: svc.attempt_verify(db, unknown, "000000", user_agent=None, ip_address=None)
        )
    assert known >= 1
    assert other == known, (known, other)


# --------------------------------------------------------------------------- #
# Nit 3: a send failure never logs the exception text above DEBUG              #
# --------------------------------------------------------------------------- #
def test_r2_nit3_send_failure_warning_does_not_echo_the_exception_text(caplog):
    """RED at 56daafae: the WARNING carried ``str(e)``, and a Respond.io error
    body can echo the message it was sent - the code included."""
    from app.services import phone_signin_service as svc

    contact = MagicMock()
    contact.id = "c-1"
    contact.workspace = None
    boom = RuntimeError("Respond said: bad message 'Your Sorento sign-in code is 555123'")
    with patch.object(svc.PortalService, "create_and_dispatch_otp", side_effect=boom):
        with caplog.at_level(logging.INFO, logger=svc.logger.name):
            svc.send_signin_code(MagicMock(), contact)

    above_debug = [r for r in caplog.records if r.levelno > logging.DEBUG]
    assert above_debug, "the failure must still be logged"
    for record in above_debug:
        assert "555123" not in record.getMessage()
    assert any("RuntimeError" in r.getMessage() for r in above_debug)
