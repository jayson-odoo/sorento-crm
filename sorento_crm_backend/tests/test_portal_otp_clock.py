"""SIGNIN-2FA-NOT-ROLE AC-12: `portal_otp_codes.created_at` is written from the same naive-UTC
clock (`_utcnow()`) the cooldown and daily cap compare it with.

Today the column is `server_default=func.now()`, which Postgres renders in the SESSION time
zone. Under `Asia/Seoul` a code written "now" lands nine hours in the future, so the 60 s
cooldown holds for nine hours and a day-old batch still counts toward the 10-a-day cap.

Every test pins `SET LOCAL TIME ZONE 'Asia/Seoul'` on the very connection the service uses
(blank_session's outer transaction; discarded at teardown), drives the service itself to write
the rows, and moves the service's clock with a patched `_utcnow`. Nothing is ever sent: the
RQ enqueue is patched.

Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md (AC-12).
Postgres only, own seed chain per test.
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
from app.services import portal_service as ps
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session


@pytest.fixture()
def seoul_db():
    with blank_session() as s:
        s.execute(text("SET LOCAL TIME ZONE 'Asia/Seoul'"))
        assert s.execute(text("SHOW TIME ZONE")).scalar() == "Asia/Seoul"
        yield s


@pytest.fixture()
def no_send():
    with patch("app.services.queue_service.enqueue_job") as mock_enqueue:
        yield mock_enqueue


def _seed(db) -> tuple[RespondContact, RespondWorkspace]:
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="ZZT WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(ws)
    db.flush()
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().int % 10_000_000:07d}",
        name="ZZT Clock",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=ws.id,
    )
    db.add(contact)
    db.commit()
    return contact, ws


def _otps(db, contact_id: str) -> list[PortalOtpCode]:
    db.expire_all()
    return (
        db.query(PortalOtpCode)
        .filter(PortalOtpCode.contact_id == contact_id)
        .order_by(PortalOtpCode.created_at.asc())
        .all()
    )


def _assert_naive_utc(row: PortalOtpCode) -> None:
    assert row.created_at is not None
    assert row.created_at.tzinfo is None, "created_at stays a naive (UTC) timestamp"
    drift = abs(row.created_at - datetime.utcnow())
    assert drift < timedelta(minutes=1), (
        f"created_at {row.created_at} is {drift} away from naive UTC now "
        f"{datetime.utcnow()} - written in the session time zone, not UTC"
    )


def test_ac12_service_written_code_has_naive_utc_created_at_under_seoul_session(seoul_db, no_send):
    contact, ws = _seed(seoul_db)

    PortalService(seoul_db).request_otp(contact.id, ws.space_id)

    rows = _otps(seoul_db, contact.id)
    assert len(rows) == 1
    _assert_naive_utc(rows[0])
    assert no_send.call_count == 1


def test_ac12_code_created_two_minutes_ago_does_not_trigger_please_wait(
    seoul_db, no_send, monkeypatch
):
    contact, ws = _seed(seoul_db)
    svc = PortalService(seoul_db)

    svc.request_otp(contact.id, ws.space_id)
    assert len(_otps(seoul_db, contact.id)) == 1

    # Two minutes later (UTC), well past the 60 s cooldown.
    real_utcnow = ps._utcnow
    monkeypatch.setattr(ps, "_utcnow", lambda: real_utcnow() + timedelta(minutes=2))

    # Must not raise "Please wait before requesting another verification code."
    svc.request_otp(contact.id, ws.space_id)
    assert len(_otps(seoul_db, contact.id)) == 2
    assert no_send.call_count == 2


def test_ac12_ten_codes_from_25_hours_ago_do_not_trigger_the_daily_cap(
    seoul_db, no_send, monkeypatch
):
    contact, ws = _seed(seoul_db)
    svc = PortalService(seoul_db)

    # Burn the whole daily allowance through the service itself. The cooldown is lifted so
    # the ten writes can happen back to back; the cap is what this test is about.
    monkeypatch.setattr(ps, "OTP_REQUEST_COOLDOWN", timedelta(days=-3650))
    for _ in range(ps.OTP_DAILY_CAP):
        svc.request_otp(contact.id, ws.space_id)
    assert len(_otps(seoul_db, contact.id)) == ps.OTP_DAILY_CAP

    # 25 hours later (UTC): those ten are outside the 24 h window.
    real_utcnow = ps._utcnow
    monkeypatch.setattr(ps, "_utcnow", lambda: real_utcnow() + timedelta(hours=25))

    # Must not raise "Daily verification limit reached. Please try again tomorrow."
    svc.request_otp(contact.id, ws.space_id)
    rows = _otps(seoul_db, contact.id)
    assert len(rows) == ps.OTP_DAILY_CAP + 1
    for row in rows[: ps.OTP_DAILY_CAP]:
        _assert_naive_utc(row)


def test_ac12_daily_cap_still_holds_inside_24_hours(seoul_db, no_send, monkeypatch):
    """Regression guard for the fix: the cap itself must keep working."""
    from app.services.error_handler import AppException

    contact, ws = _seed(seoul_db)
    svc = PortalService(seoul_db)
    monkeypatch.setattr(ps, "OTP_REQUEST_COOLDOWN", timedelta(days=-3650))
    for _ in range(ps.OTP_DAILY_CAP):
        svc.request_otp(contact.id, ws.space_id)

    real_utcnow = ps._utcnow
    monkeypatch.setattr(ps, "_utcnow", lambda: real_utcnow() + timedelta(hours=23))
    with pytest.raises(AppException) as ei:
        svc.request_otp(contact.id, ws.space_id)
    assert "Daily verification limit" in str(ei.value.detail)
