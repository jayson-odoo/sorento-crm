"""PORTAL-P4-REQUESTS owner ruling a54382059 (29 Oct): a submit-only user (holds
`projects.registrations.submit`, not `projects.projects.edit`) is narrowed to own draft or
rejected only on UNAPPROVED registrations. On an approved project (approval_state 'approved' or
null) the general edit rule applies: owner, approved collaborator.
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    STAFF,
    approve_as_manager,
    approved_project,
    as_user,
    seed_lead,
    submit_new,
    title,
    v2,
)


def _title_of(w, pid: str) -> str:
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, pid).title


def _detail(w, user: str, pid: str) -> dict:
    res = as_user(w, user).get(f"{STAFF}/{pid}")
    assert res.status_code == 200, res.text
    return res.json()


def _approved_own(w) -> str:
    pid = submit_new(w, w.sub_a).json()["id"]
    assert approve_as_manager(w, pid, owner=w.sub_a).status_code == 200
    return pid


def test_pp4_approved_own_registration_is_editable_by_submit_only_owner(v2):
    pid = _approved_own(v2)
    assert _detail(v2, v2.sub_a, pid)["can_edit"] is True
    new = title("Approved edit")
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"title": new})
    assert res.status_code == 200, res.text
    assert _title_of(v2, pid) == new


def test_pp4_staff_project_is_editable_by_submit_only_owner(v2):
    pid = approved_project(v2, owner=v2.sub_a).id
    v2.db.commit()
    assert _detail(v2, v2.sub_a, pid)["can_edit"] is True
    new = title("Staff edit")
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"title": new})
    assert res.status_code == 200, res.text
    assert _title_of(v2, pid) == new


def test_pp4_submit_only_stranger_cannot_edit_an_approved_project(v2):
    pid = _approved_own(v2)
    before = _title_of(v2, pid)
    detail = as_user(v2, v2.sub_b).get(f"{STAFF}/{pid}")
    if detail.status_code == 200:
        assert detail.json()["can_edit"] is False
    res = as_user(v2, v2.sub_b).put(f"{STAFF}/{pid}", json={"title": title("Hijack")})
    assert res.status_code in (403, 404), res.text
    assert _title_of(v2, pid) == before


def test_pp4_submit_only_approved_collaborator_can_edit(v2):
    from app.models.projects import ProjectCollaborator

    row = approved_project(v2, owner=v2.owner)
    v2.db.add(ProjectCollaborator(project_id=row.id, user_id=v2.sub_b, granted_by=v2.owner))
    v2.db.commit()
    assert _detail(v2, v2.sub_b, row.id)["can_edit"] is True
    new = title("Collab edit")
    res = as_user(v2, v2.sub_b).put(f"{STAFF}/{row.id}", json={"title": new})
    assert res.status_code == 200, res.text
    assert _title_of(v2, row.id) == new


def test_pp4_pending_own_registration_stays_read_only(v2):
    pid = submit_new(v2, v2.sub_a).json()["id"]
    assert _detail(v2, v2.sub_a, pid)["can_edit"] is False
    before = _title_of(v2, pid)
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"title": title("Late")})
    assert res.status_code == 403, res.text
    assert _title_of(v2, pid) == before


def test_pp4_submit_only_owner_cannot_reassign_an_approved_project(v2):
    from app.models.projects import Project

    pid = _approved_own(v2)
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"owner_user_id": v2.sub_b})
    assert res.status_code == 403, res.text
    v2.db.expire_all()
    assert v2.db.get(Project, pid).owner_user_id == v2.sub_a


def _lead_of(w, pid: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, pid).lead_id


def test_pp4_submit_only_owner_can_link_their_own_lead_on_an_approved_project(v2):
    pid = _approved_own(v2)
    lead = seed_lead(v2, v2.sub_a)
    v2.db.commit()
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"lead_id": lead.id})
    assert res.status_code == 200, res.text
    assert _lead_of(v2, pid) == lead.id


def test_pp4_submit_only_owner_cannot_link_another_users_lead_on_an_approved_project(v2):
    pid = _approved_own(v2)
    before = _lead_of(v2, pid)
    foreign = seed_lead(v2, v2.sub_b)
    v2.db.commit()
    res = as_user(v2, v2.sub_a).put(f"{STAFF}/{pid}", json={"lead_id": foreign.id})
    assert res.status_code == 404, res.text
    assert _lead_of(v2, pid) == before
