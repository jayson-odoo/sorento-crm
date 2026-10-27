"""AUDIT-TRAIL-DIFF: a record's Audit Trail also lists its child rows.

A complaint's product lines (``complaint_product_lines``, ``__audit_parent__ = "complaint_id"``)
are audited under their own entity_type with the complaint as ``root_entity_*``. The record
trail used to match ``entity_type/entity_id`` only, so a resubmit that swapped the product
code never showed on the complaint. Rows are written by hand: the shapes, not real data.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  registers every router
from app.api.v1.audit import audit_logs as audit_routes
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.main import app
from app.models.audit import AuditLog
from app.services.audit_service import list_audit_logs
from tests._pg_fixture import blank_session


def _row(db, *, entity_type, entity_id, action, old=None, new=None, root=None, minute=0, description=None):
    row = AuditLog(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values=old,
        new_values=new,
        description=description,
        root_entity_type=root[0] if root else entity_type,
        root_entity_id=root[1] if root else entity_id,
        actor_type="contact",
        # Pinned rather than clock_timestamp(), so the order is the test's.
        changed_at=datetime(2026, 9, 1, 9, minute),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded():
    with blank_session() as db:
        complaint_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        line_id = str(uuid.uuid4())
        root = ("complaint", complaint_id)
        # Resubmit shape 2: product code swapped on the line, status rejected -> submitted.
        _row(db, entity_type="complaint", entity_id=complaint_id, action="UPDATE",
             old={"status": "rejected", "product_code": "CWCX604-P-RL-NEW"},
             new={"status": "submitted", "product_code": "CWCY604"}, minute=33)
        _row(db, entity_type="complaint_product_lines", entity_id=line_id, action="INSERT",
             new={"id": line_id, "complaint_id": complaint_id, "product_code": "CWCX604-P-RL-NEW", "quantity": "2"},
             root=root, minute=10)
        _row(db, entity_type="complaint_product_lines", entity_id=line_id, action="UPDATE",
             old={"quantity": "2"}, new={"quantity": "3"}, root=root, minute=20)
        # Another complaint's line: never on this trail.
        _row(db, entity_type="complaint_product_lines", entity_id=str(uuid.uuid4()), action="INSERT",
             new={"product_code": "OTHER-1"}, root=("complaint", other_id), minute=30)
        yield db, complaint_id, line_id


def test_record_trail_includes_child_rows(seeded):
    db, complaint_id, line_id = seeded
    items, total = list_audit_logs(db, entity_type="complaint", entity_id=complaint_id, include_children=True)
    assert total == 3
    assert {(i.entity_type, i.action) for i in items} == {
        ("complaint", "UPDATE"),
        ("complaint_product_lines", "INSERT"),
        ("complaint_product_lines", "UPDATE"),
    }
    assert all(i.entity_id in (complaint_id, line_id) for i in items)


def test_without_flag_only_the_record_itself(seeded):
    db, complaint_id, _ = seeded
    items, total = list_audit_logs(db, entity_type="complaint", entity_id=complaint_id)
    assert total == 1
    assert items[0].entity_type == "complaint"


def _get(db, monkeypatch, **params):
    monkeypatch.setattr(audit_routes, "_is_audit_admin", lambda db, uid: True)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4())}
    try:
        res = TestClient(app).get("/api/v1/audit/logs/", params=params)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_route_without_the_flag_returns_only_the_record(seeded, monkeypatch):
    """Other readers (the Packing List Timeline, the admin Audit Logs screen) send
    entity_type + entity_id too and render every row as the record itself."""
    db, complaint_id, _ = seeded
    rows = _get(db, monkeypatch, entity_type="complaint", entity_id=complaint_id)
    assert [r["entity_type"] for r in rows] == ["complaint"]


def test_route_names_child_rows_by_their_product_code(seeded, monkeypatch):
    db, complaint_id, _ = seeded
    rows = _get(db, monkeypatch, entity_type="complaint", entity_id=complaint_id, include_children="true")
    assert len(rows) == 3
    children = [r for r in rows if r["entity_type"] == "complaint_product_lines"]
    # The UPDATE carries only the quantity; it is still named by the line's product code.
    assert {r["entity_label"] for r in children} == {"Product line CWCX604-P-RL-NEW"}
    header = next(r for r in rows if r["entity_type"] == "complaint")
    # The summary is still served; the FE lists the field diff under it.
    assert header["description"] == "status: rejected → submitted"
    assert header["new_values"]["product_code"] == "CWCY604"


def test_child_named_from_the_live_row_when_no_audit_row_on_the_page_carries_it(monkeypatch):
    """An UPDATE of a line carries only what changed; with no INSERT on the page the
    product code is read from the line itself."""
    from app.models.complaints import Complaint, ComplaintProductLine

    with blank_session() as db:
        # No audited INSERT of the line, so nothing on the page carries its product code.
        db.info["skip_audit_entity_types"] = {"complaint", "complaint_product_lines"}
        complaint = Complaint(id=str(uuid.uuid4()), complaint_number="ZZT-CMP-1", status="submitted")
        db.add(complaint)
        db.flush()
        line = ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=complaint.id, product_code="ZZT-LIVE-1")
        db.add(line)
        db.flush()
        _row(db, entity_type="complaint_product_lines", entity_id=line.id, action="UPDATE",
             old={"quantity": "1"}, new={"quantity": "4"}, root=("complaint", complaint.id), minute=5)
        rows = _get(db, monkeypatch, entity_type="complaint", entity_id=complaint.id, include_children="true")
    assert [r["entity_label"] for r in rows] == ["Product line ZZT-LIVE-1"]
