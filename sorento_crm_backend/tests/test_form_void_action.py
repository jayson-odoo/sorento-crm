"""Form void — action + guards, per form x4 (UAC ACT-1..ACT-5).

Per form: happy (200 + voided), 403 (no perm), 422 (blank reason), 409 (terminal).
Plus: sponsorship form uses its own slug (R3); irreversibility = a voided form
re-voided -> 409 and there is no un-void route.

Run: venv/bin/pytest tests/test_form_void_action.py -q
"""
from __future__ import annotations

import pytest

import tests._void_harness as H

PR_BASE = "/api/v1/procurement/purchase-requests"
SI_BASE = "/api/v1/procurement/stock-inquiries"
CMP_BASE = "/api/v1/complaints-management/complaints"


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
    from app.services.procurement_service import PurchaseRequestService, StockInquiryService
    from app.services.complaints_service import ComplaintService
    monkeypatch.setattr(PurchaseRequestService, "_notify_request_voided", lambda self, *a, **k: None)
    monkeypatch.setattr(StockInquiryService, "_notify_inquiry_voided", lambda self, *a, **k: None)
    monkeypatch.setattr(ComplaintService, "_notify_complaint_voided", lambda self, *a, **k: None)
    yield
    H.ACTOR_GRANTS.clear()
    from app.main import app
    app.dependency_overrides.clear()


def _actor(db, slugs):
    uid = H.new_user(db)
    H.ACTOR_GRANTS[uid] = set(slugs)
    return uid


# =========================================================================== #
# ACT-1 / ACT-2 — happy path per form
# =========================================================================== #
def test_pr_void_happy(db):
    uid = _actor(db, {"procurement.purchase_requests.void"})
    pid = H.new_pr(db, request_type="purchase_request", status="draft", approval_status=None)
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{PR_BASE}/{pid}/void", json={"void_reason": "created in error"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "voided"


def test_sponsorship_form_void_happy(db):
    uid = _actor(db, {"procurement.purchase_requests.void"})
    pid = H.new_pr(db, request_type="sponsorship_form", status="pending", approval_status="pending")
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{PR_BASE}/{pid}/void", json={"void_reason": "duplicate sponsorship"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "voided"


def test_complaint_void_happy(db):
    uid = _actor(db, {"complaint_management.complaints.void"})
    cid = H.new_complaint(db, status="new")
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{CMP_BASE}/{cid}/void", json={"void_reason": "wrong complaint"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "voided"


def test_stock_inquiry_void_happy(db):
    uid = _actor(db, {"procurement.stock_inquiries.void"})
    sid = H.new_stock_inquiry(db, status="pending_purchasing")
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{SI_BASE}/{sid}/void", json={"void_reason": "mistaken inquiry"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "voided"


# =========================================================================== #
# ACT-2 (R3) — PR + SF SHARE one void slug (shared router + detail component):
# procurement.purchase_requests.void unlocks a sponsorship-form void too.
# =========================================================================== #
def test_sponsorship_form_shares_pr_void_slug_200(db):
    uid = _actor(db, {"procurement.purchase_requests.void"})
    pid = H.new_pr(db, request_type="sponsorship_form", status="approved")
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{PR_BASE}/{pid}/void", json={"void_reason": "duplicate submission"})
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "voided"


# =========================================================================== #
# ACT-4 — no permission -> 403 (per form)
# =========================================================================== #
@pytest.mark.parametrize("form", ["pr", "complaint", "si"])
def test_void_no_permission_403(db, form):
    uid = _actor(db, set())  # no grants
    client = H.make_client(db, {"id": uid})
    if form == "pr":
        pid = H.new_pr(db, status="approved")
        r = client.post(f"{PR_BASE}/{pid}/void", json={"void_reason": "no perm"})
    elif form == "complaint":
        cid = H.new_complaint(db, status="approved")
        r = client.post(f"{CMP_BASE}/{cid}/void", json={"void_reason": "no perm"})
    else:
        sid = H.new_stock_inquiry(db, status="pending_purchasing")
        r = client.post(f"{SI_BASE}/{sid}/void", json={"void_reason": "no perm"})
    assert r.status_code == 403, r.text


# =========================================================================== #
# ACT-3 — blank reason -> 422 (per form)
# =========================================================================== #
@pytest.mark.parametrize("form", ["pr", "complaint", "si"])
def test_void_blank_reason_422(db, form):
    if form == "pr":
        uid = _actor(db, {"procurement.purchase_requests.void"})
        pid = H.new_pr(db, status="approved")
        url = f"{PR_BASE}/{pid}/void"
    elif form == "complaint":
        uid = _actor(db, {"complaint_management.complaints.void"})
        cid = H.new_complaint(db, status="approved")
        url = f"{CMP_BASE}/{cid}/void"
    else:
        uid = _actor(db, {"procurement.stock_inquiries.void"})
        sid = H.new_stock_inquiry(db, status="pending_purchasing")
        url = f"{SI_BASE}/{sid}/void"
    client = H.make_client(db, {"id": uid})
    r = client.post(url, json={"void_reason": "  "})
    assert r.status_code == 422, r.text


# =========================================================================== #
# ACT-3 — terminal state -> 409 (per form). Covers voided / rejected / resolved
# / closed / (CS-processed). Also ACT-5: a voided form re-voided -> 409.
# =========================================================================== #
@pytest.mark.parametrize("status", ["voided", "rejected", "closed", "processed_by_cs"])
def test_pr_void_terminal_409(db, status):
    uid = _actor(db, {"procurement.purchase_requests.void"})
    # a rejected PR carries approval_status='rejected' too
    approval = "rejected" if status == "rejected" else "approved"
    pid = H.new_pr(db, status=status, approval_status=approval)
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{PR_BASE}/{pid}/void", json={"void_reason": "second void"})
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("status", ["voided", "rejected", "resolved", "closed", "processed_by_cs"])
def test_complaint_void_terminal_409(db, status):
    uid = _actor(db, {"complaint_management.complaints.void"})
    cid = H.new_complaint(db, status=status)
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{CMP_BASE}/{cid}/void", json={"void_reason": "second void"})
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("status", ["voided", "rejected"])
def test_stock_inquiry_void_terminal_409(db, status):
    uid = _actor(db, {"procurement.stock_inquiries.void"})
    sid = H.new_stock_inquiry(db, status=status)
    client = H.make_client(db, {"id": uid})
    r = client.post(f"{SI_BASE}/{sid}/void", json={"void_reason": "second void"})
    assert r.status_code == 409, r.text


# =========================================================================== #
# ACT-5 — irreversible: no un-void / reopen route for a voided form
# =========================================================================== #
def test_no_unvoid_route():
    from app.main import app
    void_paths = {r.path for r in app.routes if getattr(r, "path", "").endswith("/void")}
    assert void_paths, "void routes should exist"
    bad = {r.path for r in app.routes if "unvoid" in getattr(r, "path", "").lower()
           or "un-void" in getattr(r, "path", "").lower()}
    assert not bad, f"unexpected un-void route(s): {bad}"
