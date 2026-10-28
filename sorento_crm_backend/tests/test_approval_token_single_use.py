"""A one-time approval link is consumed once, even by two submissions at the same moment.

`submit_approval` read the token, checked `used_at is None`, then set it, with no lock. While
the public route was `async def` with no await, one worker ran it start to finish, so only two
WORKERS could race. As a plain `def` (API-NONBLOCKING) it runs in the threadpool, so two
threads of one worker can both pass the check and both decide (security review S1).

Real, committed Postgres through `SessionLocal` (not `blank_session`): the race is between two
connections, which a single rolled-back transaction cannot show. Every row is created here
and deleted in `finally`.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402, F401

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.models.procurement import ApprovalToken, PurchaseRequestHeader
from app.services import procurement_service as procurement_service_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.procurement_service import PurchaseRequestService


@pytest.fixture(autouse=True)
def _silence_side_effects(monkeypatch):
    for name in (
        "_notify_requester_on_approved",
        "_notify_contact_on_approval_approved",
        "_notify_contact_on_approval_rejected",
        "_dispatch_approval_automation",
    ):
        monkeypatch.setattr(
            procurement_service_mod.PurchaseRequestService, name, lambda self, *a, **kw: None
        )
    monkeypatch.setattr(
        procurement_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


def _session():
    db = SessionLocal()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return db


def test_two_simultaneous_submissions_consume_the_link_once(monkeypatch):
    header_id, token = str(uuid.uuid4()), f"zzt-tok-{uuid.uuid4()}"
    db = _session()
    try:
        db.add(PurchaseRequestHeader(
            id=header_id, request_type="purchase_request", status="submitted",
            approval_status=None,
        ))
        db.add(ApprovalToken(
            id=str(uuid.uuid4()), entity_type="purchase_request", entity_id=header_id,
            token=token,
            expires=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24),
        ))
        db.commit()
    finally:
        db.close()

    # Hold each decision open after its check, so both submissions are inside the window at
    # once - the gap a slow notification or a slow commit opens on prod.
    real = PurchaseRequestService._apply_approval_decision

    def slow_decision(self, *a, **kw):
        time.sleep(0.5)
        return real(self, *a, **kw)

    monkeypatch.setattr(PurchaseRequestService, "_apply_approval_decision", slow_decision)

    outcomes: list[str] = []
    start = threading.Barrier(2)

    def submit(action: str) -> None:
        s = _session()
        try:
            start.wait()
            PurchaseRequestService(s).submit_approval(
                token, action, approved_by="zzt", approval_comments="zzt reason"
            )
            outcomes.append(action)
        except HTTPException as exc:
            outcomes.append(f"refused {exc.status_code}")
        finally:
            s.close()

    try:
        threads = [threading.Thread(target=submit, args=(a,)) for a in ("approved", "rejected")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)

        decided = [o for o in outcomes if not o.startswith("refused")]
        assert len(decided) == 1, outcomes
        assert [o for o in outcomes if o.startswith("refused")] == ["refused 409"], outcomes
        db = _session()
        try:
            header = db.get(PurchaseRequestHeader, header_id)
            assert header.approval_status == decided[0]
        finally:
            db.close()
    finally:
        db = _session()
        try:
            db.execute(text("DELETE FROM approval_tokens WHERE token = :t"), {"t": token})
            db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.id == header_id).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()
