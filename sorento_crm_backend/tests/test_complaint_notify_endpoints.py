"""Service-level tests for ComplaintService notify-salesperson methods.

``notify_root_cause_to_salesperson`` / ``notify_resolution_to_salesperson`` send
via ``_send_respond_message_for_complaint`` -> the decoupled ``respond_io`` RQ
queue every other complaint/stock-inquiry send uses (the call is enqueued, not
fired synchronously), so we stub ``queue_service.enqueue_job`` to capture the
payload without a worker -- mirroring test_complaint_do_notify.py. The
integration_log write for the ACTUAL send happens worker-side in
``_send_and_log`` (see test_whatsapp_notification_outbox_log.py /
test_respond_outbox_no_bypass.py for that guarantee); this file stays scoped
to the ComplaintService message-builder, identifier resolution, and
``*_notified_at`` persistence.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from tests._pg_fixture import pg_session
from app.models.complaints import Complaint
from app.models.complaint_master_data import (
    ComplaintRootCause,
    ComplaintResolution,
)
from app.services.complaints_service import ComplaintService
from app.services.error_handler import AppException


def _safe_exec(conn, sql: str, params=None):
    try:
        conn.execute(text(sql), params or {})
    except Exception:
        conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        _safe_exec(conn, "DELETE FROM integration_log WHERE business_id LIKE 'NOTIFY-TEST-%'")
        _safe_exec(conn, "DELETE FROM complaints WHERE complaint_number LIKE 'NOTIFY-TEST-%'")
        _safe_exec(conn, "DELETE FROM complaint_root_causes WHERE name LIKE 'NotifyTest RC%'")
        _safe_exec(conn, "DELETE FROM complaint_resolutions WHERE name LIKE 'NotifyTest RES%'")
        conn.commit()
    yield
    with engine.connect() as conn:
        _safe_exec(conn, "DELETE FROM integration_log WHERE business_id LIKE 'NOTIFY-TEST-%'")
        _safe_exec(conn, "DELETE FROM complaints WHERE complaint_number LIKE 'NOTIFY-TEST-%'")
        _safe_exec(conn, "DELETE FROM complaint_root_causes WHERE name LIKE 'NotifyTest RC%'")
        _safe_exec(conn, "DELETE FROM complaint_resolutions WHERE name LIKE 'NotifyTest RES%'")
        conn.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    with pg_session() as s:
        yield s


def _patch_send(monkeypatch, captured: list[dict]):
    """Stub the ``respond_io`` RQ enqueue + identifier resolver.

    ``captured[i]["args"]`` mirrors ``send_complaint_respond_message``'s
    positional signature: (complaint_id, identifier, display_message,
    respond_user_id, crm_sender_user_id, space_id, extra_context_vars).
    """
    from app.services import queue_service
    from app.services import respond_identifier

    def fake_enqueue(fn, *args, **kw):  # noqa: ANN001
        captured.append({"fn": getattr(fn, "__name__", str(fn)), "args": args})

        class _Job:
            id = "job-1"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    # Pretend the URL's last segment IS the respond_io_id (avoids needing a respond_contacts row).
    monkeypatch.setattr(
        respond_identifier,
        "resolve_send_identifier",
        lambda db, last_seg: str(last_seg),
    )


def _seed_complaint_with_root_cause(db: Session, *, complaint_number: str) -> tuple[Complaint, ComplaintRootCause]:
    rc = ComplaintRootCause(id=str(uuid.uuid4()), name=f"NotifyTest RC {uuid.uuid4().hex[:6]}")
    db.add(rc)
    db.flush()
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=complaint_number,
        delivery_order_number="DO-9999",
        status="responded",
        respond_inbox_url="https://app.respond.io/space/42/contact/123456",
        root_cause_id=rc.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    db.refresh(rc)
    return c, rc


def test_notify_root_cause_sends_respond_message_and_persists_timestamp(db: Session, monkeypatch) -> None:
    captured: list[dict] = []
    _patch_send(monkeypatch, captured)

    complaint, rc = _seed_complaint_with_root_cause(db, complaint_number="NOTIFY-TEST-1")
    service = ComplaintService(db)
    result = service.notify_root_cause_to_salesperson(
        complaint.id, respond_user_id="u-1", crm_sender_user_id=None
    )

    assert result["sent"] is True
    assert "Root cause is identified as" in result["message"]
    assert rc.name in result["message"]
    assert "delivery order DO-9999" in result["message"]
    assert len(captured) == 1
    _, identifier, display_message = captured[0]["args"][:3]
    assert identifier == "123456"
    assert "There has been an update regarding your complaint" in display_message

    db.expire_all()
    refreshed = db.query(Complaint).filter(Complaint.id == complaint.id).first()
    assert refreshed is not None and refreshed.root_cause_notified_at is not None


def test_notify_root_cause_validation_when_field_empty(db: Session, monkeypatch) -> None:
    _patch_send(monkeypatch, [])

    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="NOTIFY-TEST-EMPTY",
        status="responded",
        respond_inbox_url="https://app.respond.io/space/42/contact/123",
    )
    db.add(c)
    db.commit()

    service = ComplaintService(db)
    with pytest.raises(AppException) as exc_info:
        service.notify_root_cause_to_salesperson(c.id, respond_user_id="u-1")
    assert exc_info.value.status_code in (400, 422)
    msg = exc_info.value.detail.get("message") if isinstance(exc_info.value.detail, dict) else str(exc_info.value.detail)
    assert "no root cause" in str(msg).lower()


def test_notify_root_cause_validation_when_no_respond_inbox_url(db: Session, monkeypatch) -> None:
    _patch_send(monkeypatch, [])

    rc = ComplaintRootCause(id=str(uuid.uuid4()), name=f"NotifyTest RC {uuid.uuid4().hex[:6]}")
    db.add(rc)
    db.flush()
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="NOTIFY-TEST-NOINBOX",
        status="responded",
        root_cause_id=rc.id,
        respond_inbox_url=None,
    )
    db.add(c)
    db.commit()

    service = ComplaintService(db)
    with pytest.raises(AppException) as exc_info:
        service.notify_root_cause_to_salesperson(c.id, respond_user_id="u-1")
    assert exc_info.value.status_code in (400, 422)
    msg = exc_info.value.detail.get("message") if isinstance(exc_info.value.detail, dict) else str(exc_info.value.detail)
    assert "no respond.io contact" in str(msg).lower()


def test_notify_resolution_sends_message_and_persists_timestamp(db: Session, monkeypatch) -> None:
    captured: list[dict] = []
    _patch_send(monkeypatch, captured)

    res = ComplaintResolution(id=str(uuid.uuid4()), name=f"NotifyTest RES {uuid.uuid4().hex[:6]}")
    db.add(res)
    db.flush()
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="NOTIFY-TEST-RES",
        status="responded",
        respond_inbox_url="https://app.respond.io/space/42/contact/9999",
        resolution_id=res.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    result = ComplaintService(db).notify_resolution_to_salesperson(
        c.id, respond_user_id="u-1"
    )
    assert "Resolution is identified as" in result["message"]
    assert res.name in result["message"]
    assert len(captured) == 1
    _, identifier, display_message = captured[0]["args"][:3]
    assert identifier == "9999"
    assert res.name in display_message

    db.expire_all()
    refreshed = db.query(Complaint).filter(Complaint.id == c.id).first()
    assert refreshed is not None and refreshed.resolution_notified_at is not None


def test_notify_enqueues_onto_the_respond_io_queue(db: Session, monkeypatch) -> None:
    """The send is decoupled through the ``respond_io`` RQ queue -- same
    guarantee as every other complaint/stock-inquiry send (worker-side
    ``_send_and_log`` is what actually writes the integration_log outbox row
    on success AND failure; covered by test_whatsapp_notification_outbox_log.py
    / test_respond_outbox_no_bypass.py, not re-tested here)."""
    captured: list[dict] = []
    _patch_send(monkeypatch, captured)

    complaint, _ = _seed_complaint_with_root_cause(db, complaint_number="NOTIFY-TEST-LOG")
    ComplaintService(db).notify_root_cause_to_salesperson(complaint.id, respond_user_id="u-1")

    assert len(captured) == 1
    assert captured[0]["fn"] == "send_complaint_respond_message"
    complaint_id_arg = captured[0]["args"][0]
    assert complaint_id_arg == complaint.id
