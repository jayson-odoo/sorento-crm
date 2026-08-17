"""The monthly quota decision is serialized per contact and modality.

`decide_and_record` locks the contact's gate row (`SELECT ... FOR UPDATE`) for
the rest of the transaction, so two concurrent items for the same contact
decide one after the other instead of both reading `used = limit - 1` and both
passing. The burst limiter normally bounds that overshoot, but it fails open on
a Redis outage, so the bound has to live in the transaction that spends.

Real, committed Postgres through `SessionLocal` (not `blank_session`): the whole
point is what a SECOND connection sees while the first holds the lock, and a
savepoint-scoped session cannot show that. Every row carries a `ZZT-` marker
and is deleted in `finally`.
"""
from __future__ import annotations

import threading
import uuid

from app.database import SessionLocal
from app.services import media_access_service as svc
from app.services.media_access_service import MediaRequest, decide_and_record


def _settings(**overrides):
    base = dict(
        image_monthly_limit=1,
        voice_monthly_limit=100,
        voice_max_seconds=120,
        burst_limit=0,
        burst_window_seconds=60,
        warn_threshold_percent=80,
        image_provider=None,
        image_model=None,
        image_degraded_model=None,
        transcribe_model="whisper-1",
        voice_degraded_model=None,
        language_mode="pinned",
        language_pinned="en",
        language_hints=[],
        sync_wait_seconds=5.0,
        extraction_timeout_seconds=10.0,
        max_entities=10,
    )
    base.update(overrides)
    return svc.MediaSettings(**base)


def _seed(db):
    from app.models.access import RespondContact
    from app.models.media import ContactMediaLimit

    unique = f"ZZT-quota-{uuid.uuid4().hex[:10]}"
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+1555{unique}",
        respond_io_id=unique,
        name=unique,
    )
    db.add(contact)
    db.add(
        ContactMediaLimit(
            contact_id=contact.id, modality="image", is_allowed=True, monthly_limit=1
        )
    )
    db.commit()
    return contact.id, unique


def _cleanup(contact_id):
    from app.models.access import RespondContact
    from app.models.media import ContactMediaLimit, ContactMediaUsage

    db = SessionLocal()
    try:
        db.query(ContactMediaUsage).filter(
            ContactMediaUsage.contact_id == contact_id
        ).delete(synchronize_session=False)
        db.query(ContactMediaLimit).filter(
            ContactMediaLimit.contact_id == contact_id
        ).delete(synchronize_session=False)
        db.query(RespondContact).filter(RespondContact.id == contact_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _request(respond_io_id, message_id):
    return MediaRequest(
        respond_io_id=respond_io_id,
        message_id=message_id,
        modality="image",
        media_url="https://cdn.respond.io/x.jpg",
        mime_type="image/jpeg",
    )


def test_two_concurrent_items_at_the_last_allowance_do_not_both_pass(monkeypatch):
    """Limit 1, no degraded model. Session A decides and holds its transaction
    open; session B, on its own connection, must wait for A rather than read a
    count of zero. Once A commits, B sees `used = 1` and refuses on quota."""
    monkeypatch.setattr(svc.rate_limit, "hit", lambda *a, **k: svc.rate_limit.RateResult(allowed=True))
    settings = _settings()

    seed_db = SessionLocal()
    contact_id, respond_io_id = _seed(seed_db)
    seed_db.close()

    session_a = SessionLocal()
    session_b = SessionLocal()
    b_started = threading.Event()
    b_done = threading.Event()
    b_result: dict = {}

    def _b():
        b_started.set()
        try:
            b_result["decision"] = decide_and_record(
                session_b, _request(respond_io_id, "m-2"), settings=settings
            )
            session_b.commit()
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            b_result["error"] = exc
            session_b.rollback()
        finally:
            b_done.set()

    try:
        first = decide_and_record(session_a, _request(respond_io_id, "m-1"), settings=settings)
        assert first.decision == "accepted"
        # A has NOT committed: it holds the gate row lock.

        worker = threading.Thread(target=_b, daemon=True)
        worker.start()
        b_started.wait(5)
        # B is blocked on A's lock: it must not have decided anything yet.
        assert not b_done.wait(1.0), "the second decision ran without waiting for the first"

        session_a.commit()
        assert b_done.wait(10), "the second decision never completed after the lock was released"

        assert "error" not in b_result, b_result.get("error")
        assert b_result["decision"].decision == "denied_quota"
        assert svc.count_usage(session_b, respond_io_id, "image", first.quota["period_key"]) == 1
    finally:
        session_a.rollback()
        session_a.close()
        session_b.close()
        _cleanup(contact_id)


def test_the_gate_row_lock_is_taken_by_the_fast_path(monkeypatch):
    """`get_limit_row(..., for_update=True)` is what the fast path calls, and
    only for a contact that exists; a second connection asking for the same
    row `NOWAIT` is refused while the first transaction is open."""
    from sqlalchemy.exc import OperationalError

    from app.models.media import ContactMediaLimit

    monkeypatch.setattr(svc.rate_limit, "hit", lambda *a, **k: svc.rate_limit.RateResult(allowed=True))
    seed_db = SessionLocal()
    contact_id, respond_io_id = _seed(seed_db)
    seed_db.close()

    holder = SessionLocal()
    prober = SessionLocal()
    try:
        decide_and_record(holder, _request(respond_io_id, "m-1"), settings=_settings())
        try:
            prober.query(ContactMediaLimit).filter(
                ContactMediaLimit.contact_id == contact_id,
                ContactMediaLimit.modality == "image",
            ).with_for_update(nowait=True).first()
        except OperationalError as exc:
            assert "could not obtain lock" in str(exc)
        else:
            raise AssertionError("the fast path did not lock the gate row")
    finally:
        holder.rollback()
        holder.close()
        prober.rollback()
        prober.close()
        _cleanup(contact_id)
