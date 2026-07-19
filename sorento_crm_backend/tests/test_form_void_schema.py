"""Form void — schema + state (UAC SCH-1..SCH-3).

SCH-1: the reason quad (void_reason / voided_by / voided_at) exists on all three
       form models (the DB migration up/down is verified separately via alembic).
SCH-2: a successful void sets status='voided', voided_by=actor, voided_at≈now,
       void_reason=text.
SCH-3: void_reason is required, free-text >= 3 chars — blank / whitespace / short
       -> 422 (enforced at the FormVoidRequest schema layer).

Run: venv/bin/pytest tests/test_form_void_schema.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.models.complaints import Complaint
import tests._void_harness as H


@pytest.fixture
def db():
    s = H.make_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _patches(monkeypatch):
    H.ACTOR_GRANTS.clear()
    H.patch_permissions(monkeypatch)
    H.patch_serializers(monkeypatch)
    # void notify is exercised in the notify test file; no-op it here.
    from app.services.procurement_service import PurchaseRequestService, StockInquiryService
    from app.services.complaints_service import ComplaintService
    monkeypatch.setattr(PurchaseRequestService, "_notify_request_voided", lambda self, *a, **k: None)
    monkeypatch.setattr(StockInquiryService, "_notify_inquiry_voided", lambda self, *a, **k: None)
    monkeypatch.setattr(ComplaintService, "_notify_complaint_voided", lambda self, *a, **k: None)
    yield
    H.ACTOR_GRANTS.clear()
    from app.main import app
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# SCH-1 — columns present on all three form models
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("model", [PurchaseRequestHeader, StockInquiry, Complaint])
def test_reason_quad_columns_exist(model):
    cols = set(model.__table__.columns.keys())
    assert {"void_reason", "voided_by", "voided_at"} <= cols


# --------------------------------------------------------------------------- #
# SCH-2 — void writes status + reason quad
# --------------------------------------------------------------------------- #
def test_void_sets_status_and_reason_quad(db):
    from app.services.procurement_service import PurchaseRequestService
    actor = H.new_user(db)
    pid = H.new_pr(db)
    before = datetime.utcnow() - timedelta(seconds=1)
    hdr = PurchaseRequestService(db).void_request(pid, void_reason="wrong customer", actor_user_id=actor)
    after = datetime.utcnow() + timedelta(seconds=1)
    assert hdr.status == "voided"
    assert hdr.voided_by == actor
    assert hdr.void_reason == "wrong customer"
    assert hdr.voided_at is not None and hdr.voided_at.tzinfo is None  # naive UTC
    assert before <= hdr.voided_at <= after


# --------------------------------------------------------------------------- #
# SCH-3 — reason required, >= 3 non-space chars -> 422
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, "", "   ", "ab", "  a "])
def test_blank_or_short_reason_422(db, bad):
    actor = H.new_user(db)
    H.ACTOR_GRANTS[actor] = {"procurement.purchase_requests.void"}
    pid = H.new_pr(db)
    client = H.make_client(db, {"id": actor})
    body = {} if bad is None else {"void_reason": bad}
    r = client.post(f"/api/v1/procurement/purchase-requests/{pid}/void", json=body)
    assert r.status_code == 422, r.text
    from app.models.procurement import PurchaseRequestHeader as PR
    row = db.query(PR).filter(PR.id == pid).first()
    assert row.status != "voided"  # unchanged


def test_valid_reason_trimmed_and_voids(db):
    actor = H.new_user(db)
    H.ACTOR_GRANTS[actor] = {"procurement.purchase_requests.void"}
    pid = H.new_pr(db)
    client = H.make_client(db, {"id": actor})
    r = client.post(
        f"/api/v1/procurement/purchase-requests/{pid}/void",
        json={"void_reason": "  duplicate submission  "},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "voided"
    assert body["void_reason"] == "duplicate submission"


# --------------------------------------------------------------------------- #
# BAN-1 — detail DTO exposes voided_by_name (resolved, no UUID) + wa_phone + when
# --------------------------------------------------------------------------- #
def test_ban1_dto_fields_on_void_response(db):
    actor = H.new_user(db, name="Jane Voider")
    H.ACTOR_GRANTS[actor] = {"procurement.purchase_requests.void"}
    pid = H.new_pr(db)
    client = H.make_client(db, {"id": actor})
    r = client.post(
        f"/api/v1/procurement/purchase-requests/{pid}/void",
        json={"void_reason": "created in error"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["voided_by_name"] == "Jane Voider"   # resolved NAME, never the UUID
    assert body["voided_by_name"] != actor
    assert body["voided_by_wa_phone"] is None         # no person-links resolver on this branch
    assert body["voided_at"] is not None
    assert body["void_reason"] == "created in error"
    assert "voided_by" not in body                     # raw UUID not exposed
