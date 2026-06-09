"""Service-level tests for ComplaintService notify-salesperson methods.

Mocks RespondClient.send_message and the outbound webhook enqueue helper so the
flow exercises the real code path (message-builder, identifier resolution,
integration log writes, ``*_notified_at`` persistence) without hitting Respond.io.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
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
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _patch_send(monkeypatch, captured: list[dict]):
    """Stub Respond.io send + outbound webhook + identifier resolver."""
    from app.services import integration_service, crm_chat_outbound_webhook
    from app.services import respond_identifier

    def fake_send_message(self, identifier, message, *a, **kw):  # noqa: ANN001
        captured.append({"identifier": identifier, "message": message})
        return {"id": "respond-msg-1", "status": "sent"}

    monkeypatch.setattr(integration_service.RespondClient, "send_message", fake_send_message)

    # The 24h-window pre-check scans list_messages; return a recent incoming so
    # the window is open and the plain-text branch is exercised (the template
    # branch has its own coverage in test_respond_templates.py).
    import time

    def fake_list_messages(self, identifier, *a, **kw):  # noqa: ANN001
        recent_ms = int((time.time() - 3600) * 1000)
        return {"items": [{"traffic": "incoming", "status": [{"timestamp": recent_ms}]}]}

    monkeypatch.setattr(integration_service.RespondClient, "list_messages", fake_list_messages)
    monkeypatch.setattr(
        crm_chat_outbound_webhook,
        "enqueue_crm_chat_outbound_webhook",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        crm_chat_outbound_webhook,
        "resolve_sla_assignee_respond_user_id",
        lambda *a, **kw: None,
    )
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
    assert captured[0]["identifier"] == "123456"
    assert "There has been an update regarding your complaint" in captured[0]["message"]

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

    db.expire_all()
    refreshed = db.query(Complaint).filter(Complaint.id == c.id).first()
    assert refreshed is not None and refreshed.resolution_notified_at is not None


def test_notify_writes_integration_log(db: Session, monkeypatch) -> None:
    _patch_send(monkeypatch, [])

    complaint, _ = _seed_complaint_with_root_cause(db, complaint_number="NOTIFY-TEST-LOG")
    ComplaintService(db).notify_root_cause_to_salesperson(complaint.id, respond_user_id="u-1")

    rows = db.execute(
        text(
            "SELECT integration_channel, status FROM integration_log "
            "WHERE business_table='complaints' AND business_id=:cid AND direction='outbound'"
        ),
        {"cid": complaint.id},
    ).fetchall()
    assert any(r[0] == "respond_io" and r[1] == "success" for r in rows), rows
