"""PROJECT-REGISTER-V2 UAC D5, D6, E2-E7, F1-F3: register interest (a takeover request of kind
dispute), reassign to an interested person, and who is told.

Several cases pin rules that already hold (D5, D6, E2): they are guards and may be green now.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    LIST,
    MANAGE,
    STAFF,
    approved_project,
    as_user,
    developer,
    notes,
    project,
    register_body,
    title,
    uid,
    v2,
)

REASON = "Found this project at the site briefing last week."


def _interest(w, user: str, project_id: str, reason: str = REASON):
    return as_user(w, user).post(
        f"{STAFF}/{project_id}/takeover-requests", json={"kind": "dispute", "reason": reason}
    )


def _decide(w, user: str, project_id: str, request_id: str, approve: bool):
    return as_user(w, user).post(
        f"{STAFF}/{project_id}/takeover-requests/{request_id}/decide",
        json={"approve": approve},
    )


def _row(w, request_id: str):
    from app.models.projects import ProjectTakeoverRequest

    w.db.expire_all()
    return w.db.get(ProjectTakeoverRequest, request_id)


def _owner_of(w, project_id: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, project_id).owner_user_id


def _collaborators(w, project_id: str) -> set:
    from app.models.projects import ProjectCollaborator

    w.db.expire_all()
    return {
        r.user_id
        for r in w.db.query(ProjectCollaborator).filter(ProjectCollaborator.project_id == project_id)
    }


# ------------------------------------------------------------------ D5, D6


def test_d5_a_direct_register_on_a_blocking_clash_is_still_409(v2):
    dev = developer(v2.db, v2.company_id, "CONTOH Developer Sdn Bhd")
    ttl = title("Residensi")
    approved_project(v2, ttl=ttl, dev=dev)
    res = as_user(v2, v2.sales_b).post(
        LIST, json=register_body(v2, title=ttl, developer_party_id=dev.id)
    )
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_already_registered"


def test_d6_interest_is_a_dispute_request_with_the_note(v2):
    row = approved_project(v2)
    res = _interest(v2, v2.sales_b, row.id)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "dispute" and body["status"] == "pending" and body["reason"] == REASON


def test_d6_no_interest_in_your_own_project(v2):
    row = approved_project(v2)
    res = _interest(v2, v2.owner, row.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_takeover_self"


def test_d6_no_second_open_interest_by_the_same_user(v2):
    row = approved_project(v2)
    assert _interest(v2, v2.sales_b, row.id).status_code == 201
    again = _interest(v2, v2.sales_b, row.id)
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "project_takeover_already_open"


def test_d6_none_on_an_unapproved_project(v2):
    pending = project(v2.db, v2.company_id, title("Pending"), approval_state="pending", owner=v2.owner)
    res = _interest(v2, v2.sales_b, pending.id)
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_not_approved"


# ------------------------------------------------------------------ E2


def test_e2_a_non_manager_deciding_an_interest_is_403_the_owner_included(v2):
    row = approved_project(v2)
    rid = _interest(v2, v2.sales_b, row.id).json()["id"]
    for user in (v2.owner, v2.sales_c, v2.approver):
        res = _decide(v2, user, row.id, rid, True)
        assert res.status_code == 403, (user, res.text)
    assert _row(v2, rid).status == "pending"
    assert _owner_of(v2, row.id) == v2.owner


# ------------------------------------------------------------------ E3, E4


def test_e3_reassign_moves_the_owner_keeps_the_old_one_as_collaborator_leaves_others_pending(v2):
    row = approved_project(v2)
    chosen = _interest(v2, v2.sales_b, row.id).json()["id"]
    other = _interest(v2, v2.sales_c, row.id).json()["id"]

    res = _decide(v2, v2.manager, row.id, chosen, True)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"

    assert _owner_of(v2, row.id) == v2.sales_b
    assert v2.owner in _collaborators(v2, row.id)
    done = _row(v2, chosen)
    assert done.status == "approved" and done.decided_by == v2.manager and done.decided_at is not None
    assert _row(v2, other).status == "pending"


def test_e4_dismiss_rejects_the_request_and_changes_nothing_else(v2):
    row = approved_project(v2)
    rid = _interest(v2, v2.sales_b, row.id).json()["id"]
    res = _decide(v2, v2.manager, row.id, rid, False)
    assert res.status_code == 200, res.text
    assert _row(v2, rid).status == "rejected"
    assert _owner_of(v2, row.id) == v2.owner
    assert _collaborators(v2, row.id) == set()


# ------------------------------------------------------------------ E6


def test_e6_reassign_writes_an_activity_line_naming_both_people(v2):
    from app.models.activities import ActivityEvent

    row = approved_project(v2)
    rid = _interest(v2, v2.sales_b, row.id).json()["id"]
    assert _decide(v2, v2.manager, row.id, rid, True).status_code == 200

    v2.db.expire_all()
    events = (
        v2.db.query(ActivityEvent)
        .filter(ActivityEvent.entity_type == "project", ActivityEvent.entity_id == row.id)
        .all()
    )
    text = " ".join(
        f"{e.system_template} {e.body_text} {e.system_payload}" for e in events if e.kind == "system"
    )
    assert "reassign" in text.lower(), text
    # Names as words, or the ids the feed renders names from.
    for who, uid_ in (("Sales A", v2.owner), ("Sales B", v2.sales_b)):
        assert who in text or uid_ in text, (who, text)


def test_e6_the_owner_change_is_in_the_audit_log(v2):
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    row = approved_project(v2)
    rid = _interest(v2, v2.sales_b, row.id).json()["id"]
    assert _decide(v2, v2.manager, row.id, rid, True).status_code == 200
    v2.db.expire_all()
    logs = v2.db.query(AuditLog).filter(AuditLog.entity_id == row.id).all()
    assert any(v2.sales_b in str(l.new_values) for l in logs), [l.new_values for l in logs]


# ------------------------------------------------------------------ E7


def test_e7_a_view_own_user_with_a_pending_interest_can_open_the_project(v2):
    from app.models.projects import ProjectTakeoverRequest

    row = approved_project(v2)
    assert as_user(v2, v2.viewer_own).get(f"{STAFF}/{row.id}").status_code == 404
    v2.db.add(
        ProjectTakeoverRequest(
            project_id=row.id, requester_user_id=v2.viewer_own, kind="dispute", reason=REASON,
            status="pending",
        )
    )
    v2.db.flush()
    res = as_user(v2, v2.viewer_own).get(f"{STAFF}/{row.id}")
    assert res.status_code == 200, res.text
    assert res.json()["id"] == row.id


def test_e7_a_dismissed_interest_no_longer_opens_the_project(v2):
    from app.models.projects import ProjectTakeoverRequest

    row = approved_project(v2)
    v2.db.add(
        ProjectTakeoverRequest(
            project_id=row.id, requester_user_id=v2.viewer_own, kind="dispute", reason=REASON,
            status="rejected",
        )
    )
    v2.db.flush()
    assert as_user(v2, v2.viewer_own).get(f"{STAFF}/{row.id}").status_code == 404


# ------------------------------------------------------------------ F1, F2, F3


def test_f1_a_new_interest_notifies_the_owner_and_active_managers_never_the_requester(v2):
    row = approved_project(v2)
    assert _interest(v2, v2.sales_b, row.id).status_code == 201
    recipients = {n.user_id for n in notes(v2, row.id)}
    assert recipients == {v2.owner, v2.manager, v2.manager2}
    assert v2.sales_b not in recipients
    assert v2.ex_manager not in recipients


def test_f2_a_reassign_notifies_the_new_and_the_previous_owner(v2):
    row = approved_project(v2)
    rid = _interest(v2, v2.sales_b, row.id).json()["id"]
    seen = {n.id for n in notes(v2, row.id)}
    assert _decide(v2, v2.manager, row.id, rid, True).status_code == 200
    fresh = {n.user_id for n in notes(v2, row.id) if n.id not in seen}
    assert {v2.sales_b, v2.owner} <= fresh


def test_f3_management_is_the_manage_permission_and_reaches_its_active_holders(v2):
    from app.services import project_notify_service as notify

    assert notify.MANAGEMENT_PERMISSION == MANAGE == "projects.projects.manage"
    ids = set(notify.management_user_ids(v2.db))
    assert {v2.manager, v2.manager2} <= ids
    assert v2.ex_manager not in ids and v2.approver not in ids
