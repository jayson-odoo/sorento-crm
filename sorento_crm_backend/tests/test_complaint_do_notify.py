"""Notification side-effect tests for the complaint <-> DO auto-fulfilment flow.

Covers the UAC notify lines of docs/plans/PLAN-complaint-do-auto-fulfilment.md that
are NOT exercised by the reconcile-boundary tests in test_complaint_do_fulfilment.py:

  N1 — customer Respond/WhatsApp delivery FACT names complaint#, DO#, items
  N3 — Complaint team (Tier 1+2) in-app + email, same per-delivery content
  N5 — contact_id (respond_inbox_url) null -> customer notify skipped gracefully
  N6 — wording is a delivery fact, NEVER "fulfilled"

The external Respond.io send is enqueued onto the ``respond_io`` RQ queue, so we stub
``queue_service.enqueue_job`` to capture the payload without a worker. The team fan-out
is pinned to one seeded user via monkeypatch of the team-resolver so the test needs no
Access-Agent / Team seed.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.complaints import Complaint
from app.models.notification import Notification
from app.models.user import User
from app.services.complaints_service import ComplaintService

C_PREFIX = "CDN-"
U_EMAIL_PREFIX = "cdn-notify-"


def _safe_exec(conn, sql: str) -> None:
    try:
        conn.execute(text(sql))
    except Exception:
        conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    def _wipe(conn):
        _safe_exec(
            conn,
            "DELETE FROM notification_deliveries WHERE notification_id IN "
            "(SELECT id FROM notifications WHERE source_entity_id IN "
            "(SELECT id FROM complaints WHERE complaint_number LIKE 'CDN-%'))",
        )
        _safe_exec(
            conn,
            "DELETE FROM notifications WHERE source_entity_id IN "
            "(SELECT id FROM complaints WHERE complaint_number LIKE 'CDN-%')",
        )
        _safe_exec(conn, "DELETE FROM complaints WHERE complaint_number LIKE 'CDN-%'")
        _safe_exec(conn, "DELETE FROM users WHERE email LIKE 'cdn-notify-%'")
        conn.commit()

    with engine.connect() as conn:
        _wipe(conn)
    yield
    with engine.connect() as conn:
        _wipe(conn)


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _mk_complaint(db: Session, number: str, *, respond_inbox_url=None) -> Complaint:
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=number,
        status="processed_by_cs",
        respond_inbox_url=respond_inbox_url,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _patch_enqueue(monkeypatch, captured: list) -> None:
    """Capture the Respond.io send payload + stub the identifier resolver."""
    from app.services import queue_service
    from app.services import respond_identifier

    def fake_enqueue(fn, *args, **kw):  # noqa: ANN001
        captured.append({"fn": getattr(fn, "__name__", str(fn)), "args": args})

        class _Job:
            id = "job-1"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    monkeypatch.setattr(
        respond_identifier, "resolve_send_identifier", lambda db, last_seg: str(last_seg)
    )


_ITEMS = [{"product_code": "SKU-1", "qty": 2}, {"product_code": "SKU-2", "qty": 1}]


def test_N1_N6_customer_delivery_fact_wording(db: Session, monkeypatch) -> None:
    """N1: customer message names complaint#, DO#, items. N6: never says 'fulfilled'."""
    captured: list = []
    _patch_enqueue(monkeypatch, captured)
    c = _mk_complaint(
        db,
        f"{C_PREFIX}0042",
        respond_inbox_url="https://app.respond.io/space/42/contact/123456",
    )
    sent = ComplaintService(db).notify_customer_do_delivered(
        c.id,
        complaint_number=f"{C_PREFIX}0042",
        order_number="REPPS-0012",
        items=_ITEMS,
    )
    assert sent is True
    assert len(captured) == 1
    # send_complaint_respond_message(complaint_id, identifier, display_message, ...)
    display_message = captured[0]["args"][2]
    assert f"{C_PREFIX}0042" in display_message
    assert "REPPS-0012" in display_message
    assert "SKU-1" in display_message and "SKU-2" in display_message
    assert "fulfilled" not in display_message.lower()
    # structured: each item on its own line under an "Items delivered:" header
    assert "Items delivered:" in display_message
    assert "- SKU-1 x 2" in display_message
    assert "- SKU-2 x 1" in display_message
    assert "\n- SKU-1 x 2\n- SKU-2 x 1" in display_message


def test_N5_customer_skipped_without_contact(db: Session, monkeypatch) -> None:
    """N5: no respond_inbox_url -> returns False, nothing enqueued."""
    captured: list = []
    _patch_enqueue(monkeypatch, captured)
    c = _mk_complaint(db, f"{C_PREFIX}NOINBOX", respond_inbox_url=None)
    sent = ComplaintService(db).notify_customer_do_delivered(
        c.id, complaint_number=f"{C_PREFIX}NOINBOX", order_number="REPPS-0001", items=_ITEMS
    )
    assert sent is False
    assert captured == []


def test_N3_N6_team_in_app_and_email(db: Session, monkeypatch) -> None:
    """N3: team gets in-app + email with the per-delivery content. N6: no 'fulfilled'."""
    captured: list = []
    _patch_enqueue(monkeypatch, captured)
    user = User(
        id=str(uuid.uuid4()),
        email=f"{U_EMAIL_PREFIX}{uuid.uuid4().hex[:6]}@example.com",
        name="CDN Notify User",
        status="ACTIVE",
    )
    db.add(user)
    db.commit()

    svc = ComplaintService(db)
    # Pin the team fan-out to our seeded user (no Access-Agent / Team seed needed).
    monkeypatch.setattr(
        svc, "_get_complaint_team_user_ids_tiers", lambda tiers=(1, 2): [str(user.id)]
    )
    c = _mk_complaint(db, f"{C_PREFIX}TEAM")
    svc.notify_team_do_delivered(
        c.id, complaint_number=f"{C_PREFIX}TEAM", order_number="REPPS-0099", items=_ITEMS
    )

    db.expire_all()
    notif = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "complaint",
            Notification.source_entity_id == c.id,
            Notification.user_id == str(user.id),
        )
        .first()
    )
    assert notif is not None
    assert notif.event_type == "do_delivered:REPPS-0099"
    assert "REPPS-0099" in (notif.body or "")
    assert "delivered" in (notif.body or "").lower()
    assert "fulfilled" not in (notif.body or "").lower()
    # structured email/in-app body: one item per line
    assert "\n- SKU-1 x 2\n- SKU-2 x 1" in (notif.body or "")
    # email HTML uses a <ul> list
    assert "<li>SKU-1 x 2</li>" in ((notif.data or {}).get("body_html") or "")
    # email recipient captured in data for the single-email-to-all path
    assert (notif.data or {}).get("recipient_emails")


def test_N3_team_no_members_noop(db: Session, monkeypatch) -> None:
    """No Complaint team members -> graceful no-op (no crash, no notification)."""
    svc = ComplaintService(db)
    monkeypatch.setattr(
        svc, "_get_complaint_team_user_ids_tiers", lambda tiers=(1, 2): []
    )
    c = _mk_complaint(db, f"{C_PREFIX}NOTEAM")
    svc.notify_team_do_delivered(
        c.id, complaint_number=f"{C_PREFIX}NOTEAM", order_number="REPPS-0000", items=_ITEMS
    )
    db.expire_all()
    n = (
        db.query(Notification)
        .filter(Notification.source_entity_id == c.id)
        .count()
    )
    assert n == 0


def test_N8_notify_failure_does_not_propagate(db: Session, monkeypatch) -> None:
    """UAC-N8: a raising notify send is swallowed by dispatch_delivery_notifications —
    it never propagates, so the already-committed import/PUT is not 500'd. Both the
    customer and team send raise; dispatch must still return normally."""
    from app.services.complaint_fulfilment_service import ComplaintFulfilmentService

    c = _mk_complaint(db, f"{C_PREFIX}N8")

    def _boom(*a, **kw):
        raise RuntimeError("respond down")

    monkeypatch.setattr(ComplaintService, "notify_customer_do_delivered", _boom)
    monkeypatch.setattr(ComplaintService, "notify_team_do_delivered", _boom)

    payloads = [
        {
            "complaint_id": str(c.id),
            "complaint_number": f"{C_PREFIX}N8",
            "order_number": "REPPS-0808",
            "items": _ITEMS,
        }
    ]
    # Must NOT raise despite both sends throwing (best-effort post-commit).
    ComplaintFulfilmentService(db).dispatch_delivery_notifications(payloads)
