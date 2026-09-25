"""S4 - ideation idle draft: one WhatsApp reminder at 24h, then close.

Keys back to
``documentation/plans/ideation/ideation-intake-redesign-24sep-acceptance-criteria.md``:

- **AC-1401** - stale ``updated_at``, no ``reminded_at`` -> one reminder sent
  (``ideation_draft_reminder``) and ``reminded_at`` written.
- **AC-1402** - stale ``reminded_at`` -> ``cancel: true`` to shared-service, the
  pointer cleared, no message sent.
- **AC-1404** - two sweeps in the same tick send at most one reminder per draft.
- **AC-1405** - the reminder send raising is logged and swallowed; ``reminded_at``
  is still written.
- **AC-1406** - the outbound kill switch is handled exactly like AC-1405, no
  special case in the sweep.
- **AC-1407** - a shared-service outage during the close keeps the pointer.
- **AC-1408** - the scheduler registers the sweep at a 15-minute interval.

AC-1403 (a reply after the reminder drops ``reminded_at`` and moves
``updated_at``) is pinned in ``tests/test_ideation_turn.py`` - it exercises
``handle_turn``, which already rebuilds the pointer from scratch every turn.

Postgres only (``tests/_pg_fixture.py``); ``send_text_or_template`` and
``call_create_idea`` are monkeypatched seams - no live Respond.io, no live
shared-service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.services.ideation_turn_service as svc
from app.models.access import RespondContact
from app.models.integration import IntegrationLog
from app.services.error_handler import AppException
from app.services.ideation_turn_service import IdeationServiceError, sweep_idle_ideation_drafts
from app.services.respond_messaging_service import TemplateSendSkipped
from tests._pg_fixture import blank_session


@pytest.fixture
def db(monkeypatch) -> Session:
    with blank_session() as session:
        monkeypatch.setattr(
            svc,
            "_resolve_ideation_config",
            lambda _db: svc._IdeationConfig(
                base_url="https://shared.test", api_key="k", product_id="prod-1"
            ),
        )
        yield session


def _make_contact(db: Session, *, ideation: dict | None, phone: str | None = None) -> RespondContact:
    phone = phone or f"+601{uuid.uuid4().int % 10**8:08d}"
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone,
        respond_io_id=str(uuid.uuid4()),
        session_vars=({"ideation": ideation} if ideation is not None else {}),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def _reload_ideation(db: Session, contact_id: str) -> dict | None:
    db.expire_all()
    row = db.query(RespondContact).filter(RespondContact.id == contact_id).one()
    return (row.session_vars or {}).get("ideation")


NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------- #
# AC-1401 - reminder sent + reminded_at written                               #
# --------------------------------------------------------------------------- #
def test_reminder_sent_and_reminded_at_written(db, monkeypatch):
    send_spy = MagicMock(return_value={"sent_as": "template"})
    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", send_spy)

    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "title": "Show promo price in red on price tags",
            "updated_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 1, "closed": 0}
    assert send_spy.call_count == 1
    _, kwargs = send_spy.call_args
    assert kwargs["identifier"] == contact.respond_io_id
    assert kwargs["use_case"] == "ideation_draft_reminder"
    assert "Show promo price in red on price tags" in kwargs["text"]

    ideation = _reload_ideation(db, contact.id)
    assert ideation["reminded_at"] is not None
    assert ideation["draft_id"] == "d-1"  # pointer kept, not cleared


def test_fresh_draft_is_left_alone(db, monkeypatch):
    send_spy = MagicMock()
    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", send_spy)
    contact = _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=1))},
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 0}
    assert send_spy.call_count == 0
    assert _reload_ideation(db, contact.id) is not None


# --------------------------------------------------------------------------- #
# AC-1402 - close after reminded_at goes stale                                #
# --------------------------------------------------------------------------- #
def test_close_after_reminder_ttl(db, monkeypatch):
    send_spy = MagicMock()
    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", send_spy)
    create_idea_calls = []

    def _fake_create_idea(_base_url, _api_key, payload):
        create_idea_calls.append(payload)
        return {"status": "cancelled", "draft_id": payload.get("draft_id")}

    monkeypatch.setattr(svc, "call_create_idea", _fake_create_idea)

    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-9",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 1}
    assert send_spy.call_count == 0  # AC-1402: no message sent on close
    assert len(create_idea_calls) == 1
    payload = create_idea_calls[0]
    assert payload["cancel"] is True
    assert payload["draft_id"] == "d-9"
    assert payload["product_id"] == "prod-1"
    assert payload["submitter_contact_id"] == contact.phone_number

    assert _reload_ideation(db, contact.id) is None  # pointer cleared


# --------------------------------------------------------------------------- #
# AC-1404 - at most one reminder per draft, even swept twice                  #
# --------------------------------------------------------------------------- #
def test_second_sweep_in_the_same_tick_sends_no_second_reminder(db, monkeypatch):
    send_spy = MagicMock(return_value={"sent_as": "template"})
    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", send_spy)
    _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    first = sweep_idle_ideation_drafts(db, now=NOW)
    second = sweep_idle_ideation_drafts(db, now=NOW)

    assert first == {"reminded": 1, "closed": 0}
    assert second == {"reminded": 0, "closed": 0}
    assert send_spy.call_count == 1


# --------------------------------------------------------------------------- #
# AC-1405 - send failure: reminded_at still written, failure logged           #
# --------------------------------------------------------------------------- #
def test_reminder_send_failure_still_writes_reminded_at_and_logs(db, monkeypatch):
    """Nit 2 (reviewer round 1): raises the REAL ``TemplateSendSkipped`` the
    send path actually raises when no template is mapped, not a generic
    RuntimeError - documents the intent, same ``except Exception`` behaviour."""

    def _boom(**_kw):
        raise TemplateSendSkipped("ideation_draft_reminder", "no template mapped for use case")

    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", _boom)
    contact = _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 1, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation["reminded_at"] is not None

    logs = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.external_reference == contact.respond_io_id)
        .all()
    )
    assert len(logs) == 1
    assert logs[0].status == "failed"


def test_send_failure_then_close_proceeds_on_schedule(db, monkeypatch):
    """AC-1405's second half: the draft still closes on the next 24h tick."""

    def _boom(**_kw):
        raise RuntimeError("window closed, no template")

    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", _boom)
    monkeypatch.setattr(
        svc, "call_create_idea", lambda *_a, **_k: {"status": "cancelled"}
    )
    contact = _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    sweep_idle_ideation_drafts(db, now=NOW)  # reminder attempt fails, reminded_at written
    later = sweep_idle_ideation_drafts(db, now=NOW + timedelta(hours=25))

    assert later == {"reminded": 0, "closed": 1}
    assert _reload_ideation(db, contact.id) is None


# --------------------------------------------------------------------------- #
# AC-1406 - outbound kill switch handled like any other send failure          #
# --------------------------------------------------------------------------- #
def test_outbound_disabled_handled_same_as_any_send_failure(db, monkeypatch):
    """No special case in the sweep: whatever raises out of send_text_or_template
    (assert_outbound_enabled included, since it fires inside RespondClient) is
    caught the same generic way as AC-1405. Nit 2: the REAL exception
    ``assert_outbound_enabled`` raises (``AppException``, 403), not a local
    stand-in class."""

    def _boom(**_kw):
        raise AppException(
            status_code=403,
            message="Outbound messaging is switched off for this contact.",
        )

    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", _boom)
    contact = _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 1, "closed": 0}
    assert _reload_ideation(db, contact.id)["reminded_at"] is not None


# --------------------------------------------------------------------------- #
# AC-1407 - shared-service outage during close keeps the pointer              #
# --------------------------------------------------------------------------- #
def test_close_outage_keeps_the_pointer_for_retry(db, monkeypatch):
    def _boom(*_a, **_k):
        raise IdeationServiceError("shared-service down")

    monkeypatch.setattr(svc, "call_create_idea", _boom)
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation is not None
    assert ideation["draft_id"] == "d-1"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 4 (round 1, PR #1222 at 720bb8f5): a 4xx close error     #
# (the draft is already gone shared-service side) must clear the pointer      #
# instead of retrying forever; a 5xx/transport error keeps retrying (AC-1407).#
# --------------------------------------------------------------------------- #
def test_close_with_4xx_clears_the_pointer_without_retry(db, monkeypatch):
    def _boom(*_a, **_k):
        raise IdeationServiceError("draft already closed", status_code=404)

    monkeypatch.setattr(svc, "call_create_idea", _boom)
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 1}
    assert _reload_ideation(db, contact.id) is None


def test_close_with_5xx_keeps_the_pointer_for_retry(db, monkeypatch):
    def _boom(*_a, **_k):
        raise IdeationServiceError("shared-service error", status_code=500)

    monkeypatch.setattr(svc, "call_create_idea", _boom)
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation is not None
    assert ideation["draft_id"] == "d-1"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 2 (round 2): only the statuses that mean the draft is    #
# ALREADY GONE clear the pointer. A rotated/wrong api_key (401/403) or a rate #
# limit (429) is retryable, not "gone" - clearing the pointer there orphans   #
# the draft on shared-service while sorento forgets about it.                 #
# --------------------------------------------------------------------------- #
def test_close_with_401_keeps_the_pointer_for_retry(db, monkeypatch):
    def _boom(*_a, **_k):
        raise IdeationServiceError("unauthorized", status_code=401)

    monkeypatch.setattr(svc, "call_create_idea", _boom)
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation is not None
    assert ideation["draft_id"] == "d-1"


def test_close_with_429_keeps_the_pointer_for_retry(db, monkeypatch):
    def _boom(*_a, **_k):
        raise IdeationServiceError("rate limited", status_code=429)

    monkeypatch.setattr(svc, "call_create_idea", _boom)
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation is not None
    assert ideation["draft_id"] == "d-1"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 5 - the sweep must re-read session_vars fresh right      #
# before writing, so a live turn landing between the read and the write is    #
# never overwritten with the stale snapshot (plan S4: "reading the row        #
# fresh"); and one row's DB error must not abort the rest of the batch.       #
# --------------------------------------------------------------------------- #
def test_reminder_send_does_not_clobber_a_concurrent_live_turn_write(db, monkeypatch):
    contact = _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    def _send_and_race(*_a, **_kw):
        # Simulate a live turn writing a fresh pointer WHILE the reminder send
        # (a network call) is still in flight.
        svc.overwrite_for_contact(
            db,
            respond_io_id=contact.respond_io_id,
            state={
                "ideation": {
                    "draft_id": "d-1",
                    "status": "review",
                    "missing": [],
                    "updated_at": _iso(NOW),
                    "live_turn_marker": "written-mid-send",
                }
            },
        )
        return {"sent_as": "text"}

    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", _send_and_race)

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 1, "closed": 0}
    ideation = _reload_ideation(db, contact.id)
    assert ideation["status"] == "review"  # the live turn's write survives
    assert ideation["live_turn_marker"] == "written-mid-send"
    assert ideation["reminded_at"] is not None  # the reminder still stamped


def test_close_re_reads_fresh_before_clearing_the_pointer(db, monkeypatch):
    """A live turn starting a NEW draft while the close call is in flight must
    not have its pointer cleared by a close that targeted the OLD draft_id."""
    contact = _make_contact(
        db,
        ideation={
            "draft_id": "d-1",
            "status": "collecting",
            "updated_at": _iso(NOW - timedelta(hours=49)),
            "reminded_at": _iso(NOW - timedelta(hours=25)),
        },
    )

    def _close_and_race(_base_url, _api_key, payload):
        svc.overwrite_for_contact(
            db,
            respond_io_id=contact.respond_io_id,
            state={
                "ideation": {
                    "draft_id": "d-2",
                    "status": "collecting",
                    "missing": [],
                    "updated_at": _iso(NOW),
                }
            },
        )
        return {"status": "cancelled", "draft_id": payload.get("draft_id")}

    monkeypatch.setattr(svc, "call_create_idea", _close_and_race)

    result = sweep_idle_ideation_drafts(db, now=NOW)

    assert result == {"reminded": 0, "closed": 1}
    ideation = _reload_ideation(db, contact.id)
    assert ideation is not None
    assert ideation["draft_id"] == "d-2"  # the new draft survives the stale close


def test_bad_row_error_does_not_leave_the_session_transaction_aborted(db, monkeypatch):
    send_spy = MagicMock(return_value={"sent_as": "text"})
    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", send_spy)
    _make_contact(
        db,
        ideation={"draft_id": "d-1", "status": "collecting", "updated_at": _iso(NOW - timedelta(hours=25))},
    )

    def _boom(_db, *, respond_io_id, state):
        _db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(svc, "overwrite_for_contact", _boom)

    result = sweep_idle_ideation_drafts(db, now=NOW)
    assert result == {"reminded": 0, "closed": 0}  # the one row failed

    # The session must still be usable afterward - proves the sweep rolled
    # back the aborted transaction instead of leaving it poisoned for the
    # next row (or the next caller of this same session).
    other = _make_contact(db, ideation=None)
    assert other.id is not None


# --------------------------------------------------------------------------- #
# AC-1408 - scheduler registration                                            #
# --------------------------------------------------------------------------- #
def test_scheduler_registers_ideation_idle_sweep_every_15_minutes(monkeypatch):
    import app.scheduler.task_scheduler as scheduler_mod

    mock_scheduler = MagicMock()
    monkeypatch.setattr(
        scheduler_mod, "BackgroundScheduler", MagicMock(return_value=mock_scheduler)
    )

    scheduler_mod.start_scheduler()

    matching = [
        call
        for call in mock_scheduler.add_job.call_args_list
        if call.kwargs.get("id") == "ideation_idle_sweep"
    ]
    assert len(matching) == 1, mock_scheduler.add_job.call_args_list
    trigger = matching[0].kwargs.get("trigger")
    assert trigger is not None
    assert trigger.interval == timedelta(minutes=15)
