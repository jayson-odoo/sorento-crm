"""SIGNIN-2FA-NOT-ROLE fix round 2: phone sign-in picks the fresh code, not a future-stamped one.

Rows written before the OTP clock fix carry `created_at` in the DB session's local time stored as
naive (Asia/Seoul: utc+9h). `check_code` orders by `created_at desc`, so without its
`created_at <= _utcnow()` filter such a row (already expired) shadows the code just sent and the
right code is refused.

Postgres only, own seed chain, Seoul session time zone pinned on the service's own connection
(`SET LOCAL`, discarded at teardown). Nothing is sent: the RQ enqueue is patched.
Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md (AC-12).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.models.access import RespondContact
from app.models.portal import PortalOtpCode
from app.models.respond_workspace import RespondWorkspace
from app.models.user import User
from app.services import phone_signin_service as pss
from app.services.portal_service import _hash_otp
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture()
def seoul_db():
    with blank_session() as s:
        s.execute(text("SET LOCAL TIME ZONE 'Asia/Seoul'"))
        assert s.execute(text("SHOW TIME ZONE")).scalar() == "Asia/Seoul"
        yield s


def _seed(db):
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="ZZT WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(ws)
    db.flush()
    phone = f"+6011{uuid.uuid4().int % 10_000_000:07d}"
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone,
        name="ZZT Phone Signin",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=ws.id,
    )
    db.add(contact)
    db.flush()
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('psc', alpha=True)}@example.com".lower(),
        name="ZZT Phone Signin",
        status="ACTIVE",
        contact_number=phone,
        respond_contact_id=contact.id,
    )
    db.add(user)
    db.commit()
    return contact, user


def test_fresh_signin_code_verifies_despite_an_older_future_stamped_row(seoul_db):
    contact, user = _seed(seoul_db)

    # A pre-fix row: Seoul local time stored as naive (utc+9h), already expired, unconsumed.
    stale = PortalOtpCode(
        contact_id=contact.id,
        space_id=contact.workspace.space_id if contact.workspace else "",
        code_hash=_hash_otp("999999"),
        expires_at=datetime.utcnow() - timedelta(minutes=5),
        created_at=datetime.utcnow() + timedelta(hours=9),
        purpose="sign_in",
    )
    seoul_db.add(stale)
    seoul_db.commit()

    with patch("app.services.queue_service.enqueue_job") as enqueue:
        pss.send_signin_code(seoul_db, contact)
    # send_signin_code swallows a cooldown/cap refusal, so prove a code really went out.
    assert enqueue.call_count == 1, "a fresh sign-in code must be created despite the stale row"
    # enqueue_job(task, otp_id, identifier, otp_text, code, space_id, ...)
    fresh_code = enqueue.call_args.args[4]
    assert fresh_code != "999999"

    result = pss.attempt_verify(
        seoul_db,
        pss.normalize(contact.phone_number),
        fresh_code,
        user_agent="ZZT-Agent/1.0",
        ip_address="127.0.0.1",
    )
    assert result is not None, "the fresh code must sign in; the future-stamped row shadowed it"

    seoul_db.expire_all()
    assert seoul_db.get(PortalOtpCode, stale.id).consumed_at is None
