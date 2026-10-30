"""PROJECT-REGISTER-V2 UAC J1-J8: a salesperson holding only `projects.registrations.submit`
saves a draft and submits for approval. Assertions are on RECORDS (projects, notifications,
notification_deliveries, the outbox hand-off); the real NotificationService runs and nothing is
sent. Wire shape assumptions are documented in `_project_register_v2_support.py`.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    LIST,
    STAFF,
    approve_as_manager,
    as_user,
    channels_of,
    email_jobs,
    notes,
    register_body,
    reject_as_manager,
    save_draft,
    seed_lead,
    submit_existing,
    submit_new,
    title,
    uid,
    v2,
)
from ._project_registration_support import pending


def _project(w, pid: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, pid)


def _profile(w, pid: str):
    from app.models.projects import ProjectSalesProfile

    w.db.expire_all()
    return w.db.get(ProjectSalesProfile, pid)


def _all_notifications(w) -> int:
    from app.models.notification import Notification

    w.db.expire_all()
    return w.db.query(Notification).count()


def _ids(res) -> set:
    return {r["id"] for r in res.json()["data"]}


# ------------------------------------------------------------------ J1


def test_j1_a_submit_only_user_can_save_a_draft_and_submit(v2):
    assert save_draft(v2, v2.sub_a).status_code == 201
    assert submit_new(v2, v2.sub_a).status_code == 201


def test_j1_a_user_with_neither_permission_is_403(v2):
    assert save_draft(v2, v2.nobody).status_code == 403
    assert submit_new(v2, v2.nobody).status_code == 403


def test_j1b_a_submit_only_user_edits_only_their_own_draft_or_rejected_registration(v2):
    draft = save_draft(v2, v2.sub_a).json()["id"]
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{draft}", json={"title": title("Edited draft")})
    assert res.status_code == 200, res.text

    rejected = submit_new(v2, v2.sub_a).json()["id"]
    assert reject_as_manager(v2, rejected).status_code == 200
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{rejected}", json={"title": title("Edited rejected")})
    assert res.status_code == 200, res.text


def test_j1b_anything_else_is_refused(v2):
    waiting = submit_new(v2, v2.sub_a).json()["id"]
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{waiting}", json={"title": title("Late edit")})
    assert res.status_code == 403, res.text

    decided = submit_new(v2, v2.sub_a).json()["id"]
    assert approve_as_manager(v2, decided, owner=v2.sub_a).status_code == 200
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{decided}", json={"title": title("Approved edit")})
    assert res.status_code == 403, res.text

    # Someone else's registration: not theirs (403 or the own-records 404), never saved.
    rejected = submit_new(v2, v2.sub_a).json()["id"]
    reject_as_manager(v2, rejected)
    before = _project(v2, rejected).title
    res = as_user(v2, v2.sub_b).put(f"{STAFF}/{rejected}", json={"title": title("Hijack")})
    assert res.status_code in (403, 404), res.text
    assert _project(v2, rejected).title == before


# ------------------------------------------------------------------ J2


def test_j2_save_draft_stores_a_codeless_draft_owned_by_the_user_and_notifies_nobody(v2):
    before = _all_notifications(v2)
    res = save_draft(v2, v2.sub_a)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["approval_state"] == "draft"
    assert body["project_code"] is None
    assert body["owner_user_id"] == v2.sub_a
    profile = _profile(v2, body["id"])
    assert profile.contact_id == v2.a
    assert str(profile.sales_agent_id) == v2.agent_a.id
    assert _all_notifications(v2) == before
    assert v2.hand_offs == []


def test_j2_only_the_title_is_required_on_a_draft(v2):
    res = as_user(v2, v2.sub_a).post(LIST, json={"title": title("Bare"), "submit": False})
    assert res.status_code == 201, res.text
    assert res.json()["approval_state"] == "draft"
    empty = as_user(v2, v2.sub_a).post(LIST, json={"title": "", "submit": False})
    assert empty.status_code == 422


# ------------------------------------------------------------------ J3


def test_j3_a_draft_is_visible_to_its_owner_only(v2):
    pid = save_draft(v2, v2.sub_a).json()["id"]

    mine = as_user(v2, v2.sub_a).get(LIST, params={"limit": 100, "approval_state": "draft"})
    assert mine.status_code == 200, mine.text
    assert pid in _ids(mine)
    assert as_user(v2, v2.sub_a).get(f"{STAFF}/{pid}").status_code == 200

    for other in (v2.sub_b, v2.sales_b, v2.manager, v2.owner):
        listing = as_user(v2, other).get(LIST, params={"limit": 100})
        assert pid not in _ids(listing), other
        filtered = as_user(v2, other).get(LIST, params={"limit": 100, "approval_state": "draft"})
        assert pid not in _ids(filtered), other
        assert as_user(v2, other).get(f"{STAFF}/{pid}").status_code == 404, other


# ------------------------------------------------------------------ J4


def test_j4_submit_new_is_pending_with_submitted_at_and_the_portal_notice(v2):
    res = submit_new(v2, v2.sub_a)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["approval_state"] == "pending"
    assert body["submitted_at"] is not None and body["project_code"] is None
    row = _project(v2, body["id"])
    assert row.decided_at is None and row.decided_by is None and row.reject_reason is None

    rows = notes(v2, body["id"])
    assert {n.type for n in rows} == {"project_registration_submitted"}
    # Every active approve holder except the submitter (who is one by role).
    assert sorted(n.user_id for n in rows) == sorted([v2.approver, v2.manager])
    for n in rows:
        assert channels_of(v2, n) == {"in_app"}
        assert n.data["link"] == f"/project-sales/{body['id']}"
    assert v2.hand_offs == [] or all(
        "email" not in str(h) for h in v2.hand_offs
    )


def test_j4_submit_from_a_draft_does_the_same(v2):
    pid = save_draft(v2, v2.sub_a).json()["id"]
    assert notes(v2, pid) == []
    res = submit_existing(v2, v2.sub_a, pid)
    assert res.status_code == 200, res.text
    assert res.json()["approval_state"] == "pending"
    assert res.json()["submitted_at"] is not None
    rows = notes(v2, pid, "project_registration_submitted")
    assert sorted(n.user_id for n in rows) == sorted([v2.approver, v2.manager])
    assert all(channels_of(v2, n) == {"in_app"} for n in rows)


def test_j4_required_fields_are_enforced_on_submit(v2):
    # Each carries a lead with no customer, so the customer is the one thing missing.
    lead = seed_lead(v2, v2.sub_a)
    res = as_user(v2, v2.sub_a).post(
        LIST, json={"title": title(), "submit": True, "lead_id": lead.id}
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_required"

    lead = seed_lead(v2, v2.sub_a)
    pid = as_user(v2, v2.sub_a).post(
        LIST, json={"title": title(), "submit": False, "lead_id": lead.id}
    ).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid)
    assert res.status_code == 422, res.text
    assert _project(v2, pid).approval_state == "draft"
    assert notes(v2, pid) == []


# ------------------------------------------------------------------ J5


def test_j5_a_rejected_registration_resubmits_with_the_resubmitted_notice(v2):
    pid = submit_new(v2, v2.sub_a).json()["id"]
    assert reject_as_manager(v2, pid, "Already registered").status_code == 200
    assert _project(v2, pid).reject_reason == "Already registered"
    seen = {n.id for n in notes(v2, pid)}

    edit = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"title": title("Fixed")})
    assert edit.status_code == 200, edit.text
    res = submit_existing(v2, v2.sub_a, pid)
    assert res.status_code == 200, res.text
    assert res.json()["approval_state"] == "resubmitted"
    row = _project(v2, pid)
    assert row.reject_reason is None and row.decided_at is None and row.decided_by is None

    fresh = [n for n in notes(v2, pid, "project_registration_resubmitted") if n.id not in seen]
    assert sorted(n.user_id for n in fresh) == sorted([v2.approver, v2.manager])
    assert all(channels_of(v2, n) == {"in_app"} for n in fresh)


# ------------------------------------------------------------------ J6


def _decision_notice(w, monkeypatch, pid: str, kind: str, expected_user: str):
    rows = notes(w, pid, f"project_registration_{kind}")
    assert [n.user_id for n in rows] == [expected_user]
    assert channels_of(w, rows[0]) == {"in_app", "email"}
    assert "whatsapp" not in channels_of(w, rows[0])
    sent = email_jobs(w, monkeypatch, rows[0])
    assert [m["to"] for m in sent] == [f"{expected_user}@zzt.test"]


def test_j6_approve_reaches_the_salesperson_in_app_and_by_email(v2, monkeypatch):
    pid = submit_new(v2, v2.sub_a).json()["id"]
    res = approve_as_manager(v2, pid, owner=v2.sub_a)
    assert res.status_code == 200, res.text
    _decision_notice(v2, monkeypatch, pid, "approved", v2.sub_a)


def test_j6_reject_reaches_the_salesperson_in_app_and_by_email(v2, monkeypatch):
    pid = submit_new(v2, v2.sub_a).json()["id"]
    assert reject_as_manager(v2, pid).status_code == 200
    _decision_notice(v2, monkeypatch, pid, "rejected", v2.sub_a)


def test_j6_a_salesperson_without_a_linked_contact_is_reached_through_the_owner(v2, monkeypatch):
    approved = submit_new(v2, v2.sub_b).json()["id"]
    assert _profile(v2, approved).contact_id is None
    assert approve_as_manager(v2, approved, owner=v2.sub_b).status_code == 200
    _decision_notice(v2, monkeypatch, approved, "approved", v2.sub_b)

    rejected = submit_new(v2, v2.sub_b).json()["id"]
    assert reject_as_manager(v2, rejected).status_code == 200
    _decision_notice(v2, monkeypatch, rejected, "rejected", v2.sub_b)


# ------------------------------------------------------------------ J7


def _shape(w, pid: str, kind: str) -> list:
    return sorted(
        (
            n.type,
            n.title,
            n.data["link"].replace(pid, "<id>"),
            n.user_id,
            tuple(sorted(channels_of(w, n))),
        )
        for n in notes(w, pid, f"project_registration_{kind}")
    )


def test_j7_the_crm_path_notices_equal_the_portal_paths(v2):
    same = title("Parity")
    portal_id = pending(v2, v2.a, title=same)  # portal_submit through contact a, user sub_a
    crm_id = submit_new(v2, v2.sub_a, title=same).json()["id"]

    portal_shape = _shape(v2, portal_id, "submitted")
    assert portal_shape, "the portal path must have notified someone"
    assert _shape(v2, crm_id, "submitted") == portal_shape

    assert reject_as_manager(v2, portal_id).status_code == 200
    assert reject_as_manager(v2, crm_id).status_code == 200
    assert _shape(v2, crm_id, "rejected") == _shape(v2, portal_id, "rejected")
    assert _shape(v2, crm_id, "rejected")


# ------------------------------------------------------------------ J3b, J3c


def test_j3b_edit_is_offered_only_on_a_draft_or_a_rejected_registration(v2):
    draft = save_draft(v2, v2.sub_a).json()["id"]
    assert as_user(v2, v2.sub_a).get(f"{STAFF}/{draft}").json()["can_edit"] is True

    waiting = submit_new(v2, v2.sub_a).json()["id"]
    assert as_user(v2, v2.sub_a).get(f"{STAFF}/{waiting}").json()["can_edit"] is False
    assert (
        as_user(v2, v2.sub_a).put(f"{STAFF}/{waiting}", json={"title": title("Late")}).status_code
        == 403
    )

    assert reject_as_manager(v2, waiting).status_code == 200
    assert as_user(v2, v2.sub_a).get(f"{STAFF}/{waiting}").json()["can_edit"] is True


def test_j3c_a_lead_id_from_a_submit_only_user_is_ignored(v2):
    """AC-L4 (flipped from E6 "only the caller's own lead"): any lead_id is ignored."""
    from ._lead_governs_register_support import project_of, reload_lead

    lead = as_user(v2, v2.owner).post(
        "/api/v1/project-sales/leads",
        json={"title": title("Lead"), "customer_id": v2.customer.id},
    )
    assert lead.status_code in (200, 201), lead.text
    res = save_draft(v2, v2.sub_a, lead_id=lead.json()["id"])
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id is None
    assert reload_lead(v2, lead.json()["id"]).outcome == "open"
