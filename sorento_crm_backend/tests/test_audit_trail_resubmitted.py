"""AUDIT-TRAIL-RESUBMITTED: the audit rows a resubmit writes, as the Audit Trail reads them.

The trail (`lib/audit-fields.ts` `auditTrailHeadings`) heads a row "Resubmitted" from the
status move it records, so a resubmit must write ONE complaint row carrying the move out of
`rejected` together with the fields the customer changed. Pinned for both customer paths:
the portal submit and the chatbot / integration edit-via-submit.
"""
from __future__ import annotations

from app.models.audit import AuditLog
from app.schemas.complaints import ComplaintUpdate
from app.services.audit_service import register_audit_listeners
from app.services.complaints_service import ComplaintService
from app.services.portal_service import PortalService
from tests.test_resubmitted_status import (  # noqa: F401  fixtures
    _neutralize_side_effects,
    _reject,
    _seed_complaint,
    db,
)

register_audit_listeners()


def _status_rows(db, complaint_id):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "complaint", AuditLog.entity_id == str(complaint_id))
        .order_by(AuditLog.changed_at)
        .all()
    )
    return [r for r in rows if r.action == "UPDATE" and "status" in (r.new_values or {})]


def test_portal_resubmit_writes_the_status_move_and_the_changes_in_one_row(db):
    token, complaint = _seed_complaint(db)
    svc = PortalService(db)
    svc.submit_draft(token, "complaint", str(complaint.id), {"defect_description": "Cracked"})
    for attempt in ("Cracked, photos attached", "Cracked on two panels"):
        _reject(db, complaint)
        svc.submit_draft(token, "complaint", str(complaint.id), {"defect_description": attempt})

    moves = [
        ((r.old_values or {}).get("status"), r.new_values["status"]) for r in _status_rows(db, complaint.id)
    ]
    # Rejected twice, resubmitted twice: the trail's Rejected / Resubmitted / Rejected / Resubmitted.
    assert moves == [
        ("draft", "submitted"),
        ("submitted", "rejected"),
        ("rejected", "resubmitted"),
        ("resubmitted", "rejected"),
        ("rejected", "resubmitted"),
    ]
    last = _status_rows(db, complaint.id)[-1]
    assert last.old_values["defect_description"] == "Cracked, photos attached"
    assert last.new_values["defect_description"] == "Cracked on two panels"


def test_chatbot_resubmit_writes_the_status_move_and_the_changes_in_one_row(db):
    _token, complaint = _seed_complaint(db)
    _reject(db, complaint)

    ComplaintService(db).resubmit_rejected_complaint(
        str(complaint.id), ComplaintUpdate(defect_description="Photos attached this time")
    )
    db.commit()

    last = _status_rows(db, complaint.id)[-1]
    assert (last.old_values["status"], last.new_values["status"]) == ("rejected", "resubmitted")
    assert last.new_values["defect_description"] == "Photos attached this time"
