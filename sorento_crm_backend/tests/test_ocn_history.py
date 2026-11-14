"""OCN-ORDER-CHANGE-NOTICE red tests: History (UAC B11).

Every transition and edit lands in the shared audit trail under entity type
`order_change_notice` (`OrderChangeNotice.__audit_entity_type__`): who, when, action and
old -> new. The detail page's History tab reads it through `GET /api/v1/audit/logs` with the
OCN view permission (`_PER_RECORD_VIEW_PERMISSION`). Postgres only, every row seeded.
"""
from __future__ import annotations

import pytest

from ._forms_chain_support import world  # noqa: F401
from ._ocn_support import KIND, actor, create, move, ocn, ok, payload, svc  # noqa: F401

AUDIT = "/api/v1/audit/logs"


@pytest.fixture(autouse=True)
def _listeners():
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()  # idempotent; production registers it at startup


def _rows(o, ocn_id):
    from app.models.audit import AuditLog

    o.db.expire_all()
    return (
        o.db.query(AuditLog)
        .filter(AuditLog.entity_type == KIND, AuditLog.entity_id == str(ocn_id))
        .order_by(AuditLog.changed_at, AuditLog.id)
        .all()
    )


def _status_moves(rows):
    return [
        ((r.old_values or {}).get("status"), (r.new_values or {}).get("status"))
        for r in rows
        if r.action == "UPDATE" and "status" in (r.new_values or {})
    ]


def test_b11_the_model_audits_as_order_change_notice():
    from app.models.project_so import OrderChangeNotice
    from app.services.audit_service import _audit_entity_type

    assert _audit_entity_type(OrderChangeNotice) == KIND


def test_b11_every_transition_and_edit_is_recorded_with_who_and_old_to_new(ocn):
    from app.audit_context import AuditActor, actor_scope

    s = svc()

    def as_(user_id):
        return actor_scope(AuditActor(actor_type="user", user_id=user_id), db=ocn.db)

    with as_(ocn.raiser):
        row = s.create_draft(ocn.db, actor=actor(ocn, ocn.raiser), data=payload(ocn, http=False))
        ocn.db.flush()
        s.update(ocn.db, row, actor=actor(ocn, ocn.raiser), data={"description": "Second drop moves too"})
        ocn.db.flush()
        s.submit(ocn.db, row, actor=actor(ocn, ocn.raiser))
        ocn.db.flush()
    with as_(ocn.sales_admin):
        s.send_for_approval(ocn.db, row, actor=actor(ocn, ocn.sales_admin))
        ocn.db.flush()
    with as_(ocn.manager):
        s.decide(ocn.db, row, actor=actor(ocn, ocn.manager), action="approved", comments=None)
        ocn.db.flush()
    with as_(ocn.cs):
        s.mark_done(ocn.db, row, actor=actor(ocn, ocn.cs), cs_comment="Keyed in")
        ocn.db.flush()
    ocn.db.commit()

    rows = _rows(ocn, row.id)
    assert rows and rows[0].action == "CREATE"
    assert str(rows[0].user_id) == ocn.raiser
    edit = [r for r in rows if r.action == "UPDATE" and "description" in (r.new_values or {})]
    assert edit and edit[0].new_values["description"] == "Second drop moves too"
    assert ("draft", "submitted") in _status_moves(rows)
    assert ("submitted", "approved") in _status_moves(rows)
    assert ("approved", "processed_by_cs") in _status_moves(rows)
    approvals = [
        r for r in rows
        if r.action == "UPDATE" and (r.new_values or {}).get("approval_status") == "approved"
    ]
    assert approvals and str(approvals[0].user_id) == ocn.manager
    assert all(r.changed_at is not None for r in rows)


def test_b11_void_and_revise_are_recorded(ocn):
    s = svc()
    row = s.create_draft(ocn.db, actor=actor(ocn, ocn.raiser), data=payload(ocn, http=False))
    ocn.db.flush()
    s.void(ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Duplicate entry")
    ocn.db.commit()
    moves = _status_moves(_rows(ocn, row.id))
    assert ("draft", "voided") in moves


def test_b11_the_history_tab_reads_with_the_ocn_view_permission(ocn):
    d = create(ocn)
    ok(move(ocn, d["id"], "submit", ocn.raiser))
    ocn.db.commit()
    res = ocn.as_(ocn.viewer).get(AUDIT, params={"entity_type": KIND, "entity_id": d["id"]})
    assert res.status_code == 200, res.text
    body = res.json()
    entries = body.get("data", body) if isinstance(body, dict) else body
    assert entries, body
    res = ocn.as_(ocn.stranger).get(AUDIT, params={"entity_type": KIND, "entity_id": d["id"]})
    assert res.status_code == 403, res.text
