"""PROJECT-REG-PORTAL approve / reject / list / edit on the project itself (RW3, RW5, RW6, RW7,
RW9, RW11 plus the surviving B6-B10, C4, E1, F2 and fix-round cases), red-first.

REWORK (owner ruling 25 Oct 17:50): there is no registration queue. A pending portal project
is approved or rejected where it lives, `POST /api/v1/project-sales/projects/{id}/approve|reject`
(permission `projects.registrations.approve`), and the staff list shows pending and rejected
rows with their `approval_state`. The portal submission id IS the project id, so `pending()`
hands back the project id.

Contract these tests bind (flagged in the hand-off, the plan does not spell it out):
- approve / reject answer the ProjectResponse of the project: `id`, `project_code`,
  `approval_state`, `reject_reason`, `decided_at`.
- GET /projects/{id} carries `approval_state`, `reject_reason`, `submitted_at`, `decided_at`,
  `possible_duplicates` [{project_id, project_code, title}] and a nested `registration` object
  (`sales_agent_name`, `distributor_name`, `customer_name`, `your_ref`, `type_of_building`,
  `developer_name`, `main_contractor_name`, `architect_name`), null for a staff project.
- the approve body may be empty when the developer party was already picked on the project.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    LIST,
    MANAGE,
    OLD_CRM,
    STAFF,
    SUB,
    approve,
    approve_body,
    approve_url,
    as_contact,
    as_user,
    create_draft,
    developer,
    funnel,
    grant,
    pending,
    ppf_code,
    profile_of,
    project,
    project_count,
    project_type,
    reject,
    reject_url,
    registration,
    rule_next_value,
    submit,
    uid,
    world,  # noqa: F401  (fixture)
)


def _ids(res) -> list:
    assert res.status_code == 200, res.text
    return [r["id"] for r in res.json()["data"]]


def _rows(world, **params) -> dict:
    res = as_user(world, world.staff).get(LIST, params={"limit": 100, **params})
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["data"]}


# ------------------------------------------------------------------ RW11 / R11: the queue is gone


def test_r11_the_old_registrations_routes_are_gone(world):
    rid = pending(world)
    c = as_user(world, world.approver)
    assert c.get(OLD_CRM).status_code == 404
    assert c.get(f"{OLD_CRM}/{rid}").status_code == 404
    assert c.post(f"{OLD_CRM}/{rid}/approve", json={}).status_code == 404
    assert c.post(f"{OLD_CRM}/{rid}/reject", json={"reason": "x"}).status_code == 404


def test_r11_the_registrations_router_and_service_queue_functions_are_removed():
    import importlib

    with pytest.raises(ImportError):
        importlib.import_module("app.api.v1.projects.registrations")

    from app.services import project_registration_service as svc

    for name in ("list_rows", "detail", "get_or_404", "prime_meaning", "_crm_row", "_prefill"):
        assert not hasattr(svc, name), name
    for name in ("approve", "reject", "portal_list", "portal_get", "portal_save", "portal_submit",
                 "portal_delete", "find_possible_duplicates", "semantic_matches", "embed_text"):
        assert hasattr(svc, name), name


def test_the_slug_is_in_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert "projects.registrations.approve" in {p["slug"] for p in PERMISSION_REGISTRY}


# ------------------------------------------------------------------ RW3 the staff list


def test_rw3_the_list_shows_pending_and_rejected_with_their_state_and_never_drafts(world):
    draft = create_draft(world)["id"]
    pend = pending(world, title="LIST PENDING ONE")
    rej = pending(world, title="LIST REJECTED ONE")
    assert reject(world, rej, "duplicate").status_code == 200
    staff_project = project(world.db, world.company_id, "LIST STAFF ONE", code="PRJ-ZZT-L1")

    rows = _rows(world)
    assert draft not in rows
    assert rows[pend]["approval_state"] == "pending"
    assert rows[pend]["project_code"] is None
    assert rows[rej]["approval_state"] == "rejected"
    assert rows[rej]["project_code"] is None
    assert rows[staff_project.id]["approval_state"] is None
    assert rows[staff_project.id]["project_code"] == "PRJ-ZZT-L1"


def test_rw3_an_approved_portal_project_lists_as_approved_with_its_ppf_code(world):
    rid = pending(world, title="LIST APPROVED ONE")
    assert approve(world, rid).status_code == 200
    row = _rows(world)[rid]
    assert row["approval_state"] == "approved"
    assert row["project_code"] == ppf_code(5)


def test_rw3_approval_state_filters(world):
    pend = pending(world, title="FILTER PENDING")
    rej = pending(world, title="FILTER REJECTED")
    assert reject(world, rej).status_code == 200
    ok = pending(world, title="FILTER APPROVED")
    assert approve(world, ok).status_code == 200
    staff_project = project(world.db, world.company_id, "FILTER STAFF", code="PRJ-ZZT-F1")

    c = as_user(world, world.staff)
    assert set(_ids(c.get(LIST, params={"approval_state": "pending"}))) == {pend}
    assert set(_ids(c.get(LIST, params={"approval_state": "rejected"}))) == {rej}
    assert set(_ids(c.get(LIST, params={"approval_state": "approved"}))) == {ok}
    assert staff_project.id not in _ids(c.get(LIST, params={"approval_state": "approved"}))


def test_rw3_a_draft_filter_still_shows_no_drafts(world):
    create_draft(world)
    res = as_user(world, world.staff).get(LIST, params={"approval_state": "draft"})
    assert res.status_code in (200, 422), res.text
    if res.status_code == 200:
        assert res.json()["data"] == []


def test_rw3_approved_only_returns_approved_and_staff_projects(world):
    pend = pending(world, title="PICK PENDING")
    rej = pending(world, title="PICK REJECTED")
    assert reject(world, rej).status_code == 200
    ok = pending(world, title="PICK APPROVED")
    assert approve(world, ok).status_code == 200
    staff_project = project(world.db, world.company_id, "PICK STAFF", code="PRJ-ZZT-P1")

    ids = set(_ids(as_user(world, world.staff).get(LIST, params={"approved_only": "true", "limit": 100})))
    assert {ok, staff_project.id} <= ids
    assert pend not in ids and rej not in ids


def test_rw3_the_total_counts_the_pending_and_rejected_rows(world):
    before = as_user(world, world.staff).get(LIST).json()["pagination"]["total"]
    pending(world, title="COUNT PENDING")
    rej = pending(world, title="COUNT REJECTED")
    reject(world, rej)
    create_draft(world)
    after = as_user(world, world.staff).get(LIST).json()["pagination"]["total"]
    assert after == before + 2


def test_rw3_a_pending_row_is_found_by_title_search_but_has_no_code_to_match(world):
    pend = pending(world, title="MARIGOLD SQUARE REGISTRATION")
    c = as_user(world, world.staff)
    assert pend in _ids(c.get(LIST, params={"query": "marigold"}))
    assert pend not in _ids(c.get(LIST, params={"query": "None"}))


def test_rw3_sorting_by_project_code_survives_null_codes(world):
    pending(world, title="SORT PENDING")
    project(world.db, world.company_id, "SORT STAFF", code="PRJ-ZZT-SORT")
    for direction in ("asc", "desc"):
        res = as_user(world, world.staff).get(LIST, params={"sort": "project_code", "dir": direction})
        assert res.status_code == 200, res.text


def test_rw3_the_detail_of_a_pending_project_carries_the_registration_metadata(world):
    existing = project(world.db, world.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-D1")
    world.semantic.append((existing.id, 0.93))
    rid = pending(world, title="CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU", mukim="Tebrau")
    res = as_user(world, world.staff).get(f"{STAFF}/{rid}")
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["id"] == rid
    assert d["approval_state"] == "pending"
    assert d["project_code"] is None
    assert d["submitted_at"]
    assert d["reject_reason"] is None
    assert d["developer_name"] is None  # no developer PARTY yet: the typed name is separate
    assert d["mukim"] == "Tebrau" and d["state"] == "Johor"
    reg = d["registration"]
    assert reg["sales_agent_name"] == "Aminah Example"
    assert reg["sales_agent_name"] != world.agent_a.sales_agent
    assert reg["distributor_name"] == "Example Distribution Sdn Bhd"
    assert reg["customer_name"]
    assert reg["your_ref"] == "REF-ZZT-1"
    assert reg["type_of_building"] == "Office"
    assert reg["developer_name"] == "Example Developer Sdn Bhd"
    assert reg["main_contractor_name"] == "Example Builders Sdn Bhd"
    assert reg["architect_name"] == "Example Architects"
    assert d["possible_duplicates"] == [
        {"project_id": existing.id, "project_code": "PRJ-ZZT-D1", "title": existing.title}
    ]


def test_rw3_a_staff_project_detail_has_no_registration_block_and_no_duplicates(world):
    staff_project = project(world.db, world.company_id, "PLAIN STAFF TOWER", code="PRJ-ZZT-D2")
    world.semantic.append((staff_project.id, 0.99))
    d = as_user(world, world.staff).get(f"{STAFF}/{staff_project.id}").json()
    assert d["approval_state"] is None
    assert d["registration"] is None
    assert d["possible_duplicates"] == []


def test_rw3_no_duplicate_is_an_empty_list_and_a_decided_project_is_not_checked_again(world):
    existing = project(world.db, world.company_id, "KILANG BETA", code="PRJ-ZZT-D3")
    rid = pending(world)
    assert as_user(world, world.staff).get(f"{STAFF}/{rid}").json()["possible_duplicates"] == []
    world.semantic.append((existing.id, 0.99))
    assert approve(world, rid).status_code == 200
    assert as_user(world, world.staff).get(f"{STAFF}/{rid}").json()["possible_duplicates"] == []


def test_rw3_a_rejected_detail_carries_the_reason_for_the_crm(world):
    rid = pending(world)
    reject(world, rid, "Already registered by Bakar")
    d = as_user(world, world.staff).get(f"{STAFF}/{rid}").json()
    assert d["approval_state"] == "rejected"
    assert d["reject_reason"] == "Already registered by Bakar"
    assert d["decided_at"]


# ------------------------------------------------------------------ RW5 approve


def _template_with_task(world, name="Spec in the finish"):
    from app.models.projects import ProjectTemplate, ProjectTemplateTask
    from app.services.project_seed_service import seed_default_task_graph

    seed_default_task_graph(world.db)
    kind = project_type(world.db, world.company_id, "Office")
    template = ProjectTemplate(id=uid(), company_id=world.company_id, type_id=kind.id, name="Office template")
    world.db.add(template)
    world.db.flush()
    world.db.add(
        ProjectTemplateTask(id=uid(), company_id=world.company_id, template_id=template.id, name=name)
    )
    world.db.flush()
    return template


def test_rw5_a_coordinator_without_manage_approves_and_the_project_gets_a_ppf_code_stage_and_owner(world):
    from app.models.projects import Project

    stages = funnel(world.db)
    rid = pending(world, title="  CADANGAN   BLOK   BETA ")
    assert registration(world, rid).status_id is None
    assert MANAGE not in world.perms[world.coordinator]
    dev = developer(world.db, world.company_id, "Example Developer Sdn Bhd")

    res = as_user(world, world.coordinator).post(
        approve_url(rid),
        json={"title": "  CADANGAN   BLOK   BETA ", "developer_party_id": dev.id, "owner_user_id": world.applicant_user},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    code = ppf_code(5)
    assert out["id"] == rid
    assert out["approval_state"] == "approved"
    assert out["project_code"] == code
    assert out["status_key"] == "registered"

    world.db.expire_all()
    made = world.db.get(Project, rid)
    assert made.project_code == code
    assert made.approval_state == "approved"
    assert made.title == "CADANGAN BLOK BETA"
    assert made.normalised_title == "cadangan blok beta"
    assert made.developer_party_id == dev.id
    assert made.status_id == stages["registered"].id
    assert made.outcome == "open"
    assert made.owner_user_id == world.applicant_user
    assert made.decided_at is not None
    assert made.decided_by == world.coordinator
    assert rule_next_value(world.db, world.rule_id) == 6


def test_rw5_state_and_mukim_land_on_the_profile(world):
    rid = pending(world)
    res = approve(world, rid, state="Selangor", mukim="Petaling")
    assert res.status_code == 200, res.text
    profile = profile_of(world, rid)
    assert (profile.state, profile.mukim) == ("Selangor", "Petaling")
    # the legacy fields the approver does not touch survive the approval
    assert profile.your_ref == "REF-ZZT-1"
    assert profile.sales_agent_id == world.agent_a.id


def test_rw5_the_template_checklist_lands_with_the_approval(world):
    from app.models.projects import ProjectTask

    template = _template_with_task(world)
    rid = pending(world)
    res = approve(world, rid, template_id=template.id)
    assert res.status_code == 200, res.text
    world.db.expire_all()
    names = [t.name for t in world.db.query(ProjectTask).filter(ProjectTask.project_id == rid).all()]
    assert names == ["Spec in the finish"]


def test_rw5_a_pending_project_has_no_template_tasks_before_approve(world):
    from app.models.projects import ProjectTask

    rid = pending(world)
    assert world.db.query(ProjectTask).filter(ProjectTask.project_id == rid).count() == 0


def test_rw5_the_portal_detail_shows_the_code_after_approve(world):
    rid = pending(world)
    assert approve(world, rid).status_code == 200
    portal = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert portal["status"] == "approved"
    assert portal["reference"] == ppf_code(5)
    assert portal["is_draft"] is False
    items = as_contact(world, world.a).get(f"/api/v1/public/portal/submissions", params={"type": "project_registration"}).json()["items"]
    assert next(i for i in items if i["id"] == rid)["ppf_no"] == ppf_code(5)


def test_rw5_without_the_permission_approve_and_reject_are_403(world):
    rid = pending(world)
    c = as_user(world, world.staff)
    assert c.post(approve_url(rid), json=approve_body(world, rid)).status_code == 403
    assert c.post(reject_url(rid), json={"reason": "no"}).status_code == 403
    row = registration(world, rid)
    assert row.approval_state == "pending" and row.project_code is None
    assert rule_next_value(world.db, world.rule_id) == 5


def test_rw5_approve_without_a_developer_party_is_422_and_draws_no_number(world):
    rid = pending(world)
    res = as_user(world, world.approver).post(approve_url(rid), json={})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_registration_developer_required"
    row = registration(world, rid)
    assert row.approval_state == "pending" and row.project_code is None
    assert rule_next_value(world.db, world.rule_id) == 5


def test_rw5_approve_works_with_an_empty_body_once_the_developer_was_picked_on_the_project(world):
    """The header's Approve button sends no form: the approver picked the developer on the edit
    page (RW9), so the project already carries it."""
    rid = pending(world)
    dev = developer(world.db, world.company_id, "Example Developer Sdn Bhd")
    put = as_user(world, world.coordinator).put(f"{STAFF}/{rid}", json={"developer_party_id": dev.id})
    assert put.status_code == 200, put.text
    res = as_user(world, world.coordinator).post(approve_url(rid), json={})
    assert res.status_code == 200, res.text
    assert res.json()["project_code"] == ppf_code(5)
    assert registration(world, rid).developer_party_id == dev.id


def test_rw5_approve_or_reject_a_project_that_is_not_pending_is_409(world):
    c = as_user(world, world.approver)
    done = pending(world)
    assert approve(world, done).status_code == 200
    rejected = pending(world)
    assert reject(world, rejected).status_code == 200
    draft = create_draft(world)["id"]
    staff_project = project(world.db, world.company_id, "NOT PENDING STAFF", code="PRJ-ZZT-NP")

    for rid in (done, rejected, draft, staff_project.id):
        a = c.post(approve_url(rid), json=approve_body(world, rid))
        assert a.status_code == 409, (rid, a.text)
        assert a.json()["code"] == "project_registration_not_pending"
        r = c.post(reject_url(rid), json={"reason": "again"})
        assert r.status_code == 409, (rid, r.text)
        assert r.json()["code"] == "project_registration_not_pending"
    assert registration(world, draft).approval_state == "draft"
    assert registration(world, staff_project.id).approval_state is None


def test_rw5_an_unknown_or_malformed_id_is_404(world):
    c = as_user(world, world.approver)
    assert c.post(approve_url(uid()), json={}).status_code == 404
    assert c.post(approve_url("not-a-uuid"), json={}).status_code == 404
    assert c.post(reject_url(uid()), json={"reason": "x"}).status_code == 404


def test_b6_a_blocking_spelling_clash_never_blocks_an_approval(world):
    from app.services.project_clash_service import find_clashes

    dev = developer(world.db, world.company_id, "Setia Example Group")
    existing = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev)
    rid = pending(world, title="Setia Alam Ph 3B")
    clashes = find_clashes(world.db, company_id=world.company_id, developer_party_id=dev.id, title="Setia Alam Ph 3B")
    assert any(cand.blocks and cand.project_id == existing.id for cand in clashes)  # the staff route would refuse
    res = approve(world, rid, developer_party_id=dev.id)
    assert res.status_code == 200, res.text
    assert res.json()["approval_state"] == "approved"


# ------------------------------------------------------------------ RW6 exact duplicate


def test_rw6_an_exact_developer_and_title_repeat_is_409_naming_the_project_and_changes_nothing(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    existing = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, code="PPF2609001")
    rid = pending(world, title="  SETIA ALAM   phase 3b ")
    before = project_count(world)

    res = approve(world, rid, developer_party_id=dev.id)
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["code"] == "project_registration_exact_duplicate"
    assert "PPF2609001" in body["message"]
    assert body["details"]["existing_project"] == {
        "project_id": existing.id,
        "project_code": "PPF2609001",
        "title": "Setia Alam Phase 3B",
    }
    assert project_count(world) == before
    row = registration(world, rid)
    assert row.approval_state == "pending" and row.project_code is None and row.status_id is None
    assert row.decided_at is None and row.decided_by is None
    assert rule_next_value(world.db, world.rule_id) == 5  # the refused attempt drew no number


def test_rw6_the_project_can_be_approved_after_the_title_changes(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev)
    rid = pending(world, title="Setia Alam Phase 3B")
    assert approve(world, rid, developer_party_id=dev.id).status_code == 409
    second = approve(world, rid, developer_party_id=dev.id, title="Setia Alam Phase 3B (Block C)")
    assert second.status_code == 200, second.text
    assert second.json()["project_code"] == ppf_code(5)
    assert registration(world, rid).title == "Setia Alam Phase 3B (Block C)"


def test_rw6_a_pending_project_with_the_same_developer_and_title_does_not_block_an_approval(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Tower Gamma", developer_party=dev, approval_state="pending")
    rid = pending(world, title="Tower Gamma")
    res = approve(world, rid, developer_party_id=dev.id)
    assert res.status_code == 200, res.text


def test_rw6_two_approved_projects_with_the_same_developer_and_title_stay_impossible(world):
    from sqlalchemy.exc import IntegrityError

    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Tower Delta", developer_party=dev, approval_state="approved", code="PPF2601050")
    with pytest.raises(IntegrityError):
        with world.db.begin_nested():
            project(world.db, world.company_id, "Tower Delta", developer_party=dev, code="PPF2601051")


# ------------------------------------------------------------------ RW7 reject


def test_rw7_reject_needs_a_reason(world):
    rid = pending(world)
    c = as_user(world, world.approver)
    for reason in ("", "   "):
        res = c.post(reject_url(rid), json={"reason": reason})
        assert res.status_code == 422, (reason, res.text)
    assert c.post(reject_url(rid), json={}).status_code == 422
    assert registration(world, rid).approval_state == "pending"


def test_rw7_reject_marks_it_rejected_keeps_it_listed_and_draws_no_number(world):
    rid = pending(world)
    res = reject(world, rid, "Already registered by Bakar", user=world.coordinator)
    assert res.status_code == 200, res.text
    assert res.json()["approval_state"] == "rejected"
    assert res.json()["reject_reason"] == "Already registered by Bakar"
    row = registration(world, rid)
    assert row.approval_state == "rejected"
    assert row.reject_reason == "Already registered by Bakar"
    assert row.decided_at is not None and row.decided_by == world.coordinator
    assert row.project_code is None and row.status_id is None
    assert _rows(world)[rid]["approval_state"] == "rejected"
    assert rule_next_value(world.db, world.rule_id) == 5


def test_rw7_the_portal_shows_the_reason_and_lets_the_contact_edit_and_resubmit(world):
    rid = pending(world)
    reject(world, rid, "Already registered by Bakar")

    c = as_contact(world, world.a)
    d = c.get(f"{SUB}/{rid}").json()
    assert d["status"] == "rejected"
    assert d["reject_reason"] == "Already registered by Bakar"
    assert d["is_draft"] is True

    edit = c.put(
        f"{SUB}/{rid}",
        json={"fields": {"title": "CADANGAN BLOK BETA FASA 2", "state": "Johor", "developer_name": "Example Developer Sdn Bhd"}},
    )
    assert edit.status_code == 200, edit.text
    assert registration(world, rid).title == "CADANGAN BLOK BETA FASA 2"
    again = submit(world, rid)
    assert again.status_code == 200, again.text
    # RESUBMITTED-STATUS (owner, 27 Oct): a submit answering a rejection is a resubmit.
    assert again.json()["status"] == "resubmitted"
    row = registration(world, rid)
    assert row.approval_state == "resubmitted"
    assert row.reject_reason is None
    assert row.decided_at is None and row.decided_by is None
    assert c.get(f"{SUB}/{rid}").json()["reject_reason"] is None
    assert _rows(world)[rid]["approval_state"] == "resubmitted"


def test_rw7_a_rejected_project_can_be_approved_only_after_it_is_resubmitted(world):
    rid = pending(world)
    reject(world, rid)
    assert approve(world, rid).status_code == 409
    submit(world, rid)
    assert approve(world, rid).status_code == 200


# ------------------------------------------------------------------ RW9 who may edit a pending project


def test_rw9_an_approver_without_manage_may_edit_a_pending_project_and_pick_the_developer(world):
    rid = pending(world)
    dev = developer(world.db, world.company_id, "Example Developer Sdn Bhd")
    res = as_user(world, world.coordinator).put(
        f"{STAFF}/{rid}", json={"title": "CADANGAN BLOK BETA PHASE TWO", "developer_party_id": dev.id}
    )
    assert res.status_code == 200, res.text
    row = registration(world, rid)
    assert row.developer_party_id == dev.id
    assert row.title == "CADANGAN BLOK BETA PHASE TWO"
    assert row.normalised_title == "cadangan blok beta phase two"
    assert row.approval_state == "pending" and row.project_code is None


def test_rw9_the_owner_linked_user_may_edit_it_too(world):
    rid = pending(world, world.third)  # owner = linked_staff, who holds no approve grant
    assert registration(world, rid).owner_user_id == world.linked_staff
    res = as_user(world, world.linked_staff).put(f"{STAFF}/{rid}", json={"mukim": "Tebrau"})
    assert res.status_code == 200, res.text
    assert profile_of(world, rid).mukim == "Tebrau"


def test_rw9_anyone_else_is_403(world):
    rid = pending(world)
    res = as_user(world, world.staff).put(f"{STAFF}/{rid}", json={"mukim": "Tebrau"})
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_not_editable"
    assert profile_of(world, rid).mukim == "Kulai"


def test_rw9_the_approve_right_does_not_open_a_staff_project(world):
    staff_project = project(world.db, world.company_id, "SOMEONE ELSES TOWER", code="PRJ-ZZT-E1", owner=world.owner)
    res = as_user(world, world.coordinator).put(f"{STAFF}/{staff_project.id}", json={"mukim": "Tebrau"})
    assert res.status_code == 403, res.text


def test_rw9_can_edit_in_the_payload_follows_the_same_rule(world):
    rid = pending(world, world.third)
    flags = {}
    for name in ("coordinator", "linked_staff", "staff"):
        d = as_user(world, getattr(world, name)).get(f"{STAFF}/{rid}").json()
        flags[name] = d["can_edit"]
    assert flags == {"coordinator": True, "linked_staff": True, "staff": False}
    row = _rows(world)[rid]
    assert row["can_edit"] is False  # the list was read as `staff`

    # The approve grant opens a PENDING project only: not a staff project, not an approved
    # or a rejected one (review round 3: `or may_approve` alone must not survive).
    staff_project = project(world.db, world.company_id, "CAN EDIT STAFF", code="PRJ-ZZT-CE1", owner=world.owner)
    ok = pending(world, title="CAN EDIT APPROVED")
    assert approve(world, ok).status_code == 200
    rej = pending(world, title="CAN EDIT REJECTED")
    assert reject(world, rej).status_code == 200
    c = as_user(world, world.coordinator)
    for other in (staff_project.id, ok, rej):
        assert c.get(f"{STAFF}/{other}").json()["can_edit"] is False, other
    listed = {r["id"]: r for r in c.get(LIST, params={"limit": 100}).json()["data"]}
    assert listed[rid]["can_edit"] is True
    for other in (staff_project.id, ok, rej):
        assert listed[other]["can_edit"] is False, other


def test_rw9_once_approved_the_approve_right_alone_no_longer_edits_it(world):
    rid = pending(world)
    assert approve(world, rid, owner_user_id=world.applicant_user).status_code == 200
    res = as_user(world, world.coordinator).put(f"{STAFF}/{rid}", json={"mukim": "Tebrau"})
    assert res.status_code == 403, res.text


# ------------------------------------------------------------------ S9 owner assignment (on projects)


def _approve(world, rid, **over):
    return approve(world, rid, **over)


def test_s9_the_applicant_may_own_it_without_the_manage_grant(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    assert _approve(world, rid, owner_user_id=world.applicant_user).status_code == 200


def test_s9_another_owner_needs_the_manage_grant(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_owner_assign_forbidden"
    assert registration(world, rid).approval_state == "pending"


def test_s9_a_manager_may_pick_another_active_user_of_the_company(world):
    world.perms[world.approver].add(MANAGE)
    grant(world.db, world.owner, "projects.projects.view", world.company_id)
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 200, res.text
    assert registration(world, rid).owner_user_id == world.owner


def test_s9_an_owner_with_no_access_to_the_company_is_422(world):
    from app.models.company import UserCompany

    world.perms[world.approver].add(MANAGE)
    world.db.query(UserCompany).filter_by(user_id=world.owner).delete()
    world.db.flush()
    rid = pending(world)
    assert _approve(world, rid, owner_user_id=world.owner).status_code == 422
    assert registration(world, rid).approval_state == "pending"


def test_s9_an_inactive_owner_is_422(world):
    from app.models.user import User

    world.perms[world.approver].add(MANAGE)
    grant(world.db, world.owner, "projects.projects.view", world.company_id)
    world.db.get(User, world.owner).status = "inactive"
    world.db.flush()
    rid = pending(world)
    assert _approve(world, rid, owner_user_id=world.owner).status_code == 422


def test_s9_without_an_applicant_the_owner_defaults_to_the_approver(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world, world.b)  # no linked CRM user
    body = approve_body(world, rid)
    body.pop("owner_user_id", None)
    res = as_user(world, world.approver).post(approve_url(rid), json=body)
    assert res.status_code == 200, res.text
    assert registration(world, rid).owner_user_id == world.approver


def test_s9_with_no_owner_sent_the_applicant_owns_it(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    body = approve_body(world, rid)
    body.pop("owner_user_id", None)
    assert as_user(world, world.approver).post(approve_url(rid), json=body).status_code == 200
    assert registration(world, rid).owner_user_id == world.applicant_user


def test_r2_an_ineligible_applicant_falls_back_to_the_approver_without_manage(world):
    from app.models.user import User

    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    world.db.get(User, world.applicant_user).status = "inactive"
    world.db.flush()
    assert _approve(world, rid, owner_user_id=world.applicant_user).status_code == 200
    assert registration(world, rid).owner_user_id == world.approver


def test_r2_another_owner_keeps_its_rules_when_the_applicant_is_ineligible(world):
    from app.models.user import User

    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    world.db.get(User, world.applicant_user).status = "inactive"
    world.db.flush()
    assert _approve(world, rid, owner_user_id=world.owner).status_code == 403


# ------------------------------------------------------------------ S10 cross-company ids


def test_s10_a_party_type_or_template_of_another_company_is_422(world):
    rid = pending(world)
    foreign_dev = developer(world.db, world.other_company, "Foreign Developer")
    foreign_arch = developer(world.db, world.other_company, "Foreign Architect", "architect")
    foreign_contractor = developer(world.db, world.other_company, "Foreign Builder", "main_contractor")
    foreign_type = project_type(world.db, world.other_company, "Foreign Type")
    c = as_user(world, world.approver)
    for over in (
        {"developer_party_id": foreign_dev.id},
        {"architect_party_id": foreign_arch.id},
        {"main_contractor_party_id": foreign_contractor.id},
        {"type_id": foreign_type.id},
        {"template_id": uid()},
    ):
        res = c.post(approve_url(rid), json=approve_body(world, rid, **over))
        assert res.status_code == 422, (over, res.status_code, res.text)
    assert registration(world, rid).approval_state == "pending"
    assert rule_next_value(world.db, world.rule_id) == 5


# ------------------------------------------------------------------ S6 row lock


def test_s6_approve_and_reject_read_the_project_with_a_row_lock(world):
    from sqlalchemy import event

    a, b = pending(world), pending(world)
    seen: list = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        text_ = statement.lstrip().upper().replace('"', "")
        if text_.startswith("SELECT") and "FOR UPDATE" in text_ and "PROJECTS.PROJECTS" in text_:
            seen.append(text_)

    engine = world.db.get_bind()
    event.listen(engine, "before_cursor_execute", spy)
    try:
        assert approve(world, a).status_code == 200
        assert seen, "approve must lock the project row it decides"
        seen.clear()
        assert reject(world, b).status_code == 200
        assert seen, "reject must lock the project row it decides"
    finally:
        event.remove(engine, "before_cursor_execute", spy)


# ------------------------------------------------------------------ C4 numbering


def test_c4_submitted_and_rejected_projects_draw_no_number(world):
    create_draft(world)
    rid = pending(world)
    assert rule_next_value(world.db, world.rule_id) == 5
    reject(world, rid, "no")
    assert rule_next_value(world.db, world.rule_id) == 5
    assert registration(world, rid).project_code is None


def test_c4_approving_twice_draws_two_consecutive_numbers(world):
    one, two = pending(world, title="FIRST TOWER"), pending(world, title="SECOND TOWER")
    assert approve(world, one).json()["project_code"] == ppf_code(5)
    assert approve(world, two).json()["project_code"] == ppf_code(6)


# ------------------------------------------------------------------ B10 staff registration unchanged


def test_b10_staff_direct_registration_still_refuses_a_blocking_clash(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    from ._sample_request_seed import make_customer

    from ._lead_governs_register_support import staff_lead

    customer_id = make_customer(world.db, world.company_id).id
    lead_a = staff_lead(world.db, world.company_id, world.staff, customer_id)
    lead_b = staff_lead(world.db, world.company_id, world.staff, customer_id)
    world.db.commit()
    c = as_user(world, world.staff)
    first = c.post(
        f"{STAFF}/",
        json={"title": "Setia Alam Phase 3B", "developer_party_id": dev.id, "customer_id": customer_id,
              "lead_id": lead_a},
    )
    assert first.status_code == 201, first.text
    assert first.json()["approval_state"] is None
    assert first.json()["project_code"] == ppf_code(5)
    second = c.post(
        f"{STAFF}/",
        json={"title": "setia alam ph 3b", "developer_party_id": dev.id, "customer_id": customer_id,
              "lead_id": lead_b},
    )
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "project_already_registered"


def test_b10_skip_clash_check_is_opt_in_at_the_service(world):
    from app.services.error_handler import AppException
    from app.services.project_service import register_project

    dev = developer(world.db, world.company_id, "Setia Example Group")
    kw = dict(company_id=world.company_id, actor_user_id=world.owner, developer_party_id=dev.id)
    register_project(world.db, title="Setia Alam Phase 3B", **kw)
    with pytest.raises(AppException) as exc:
        register_project(world.db, title="setia alam ph 3b", **kw)
    assert exc.value.status_code == 409
    made = register_project(world.db, title="setia alam ph 4b", skip_clash_check=True, **kw)
    assert made.project_code


# ------------------------------------------------------------------ E1 project fields


def test_e1_state_and_mukim_on_register_get_and_update(world):
    from ._sample_request_seed import make_customer

    from ._lead_governs_register_support import staff_lead

    customer_id = make_customer(world.db, world.company_id).id
    lead_id = staff_lead(world.db, world.company_id, world.staff, customer_id)
    world.db.commit()
    c = as_user(world, world.staff)
    made = c.post(
        f"{STAFF}/",
        json={"title": "ZZT FIELDS TOWER", "state": "Selangor", "mukim": "Petaling",
              "customer_id": customer_id, "lead_id": lead_id},
    )
    assert made.status_code == 201, made.text
    assert (made.json()["state"], made.json()["mukim"]) == ("Selangor", "Petaling")
    pid = made.json()["id"]
    got = c.get(f"{STAFF}/{pid}").json()
    assert (got["state"], got["mukim"]) == ("Selangor", "Petaling")
    upd = c.put(f"{STAFF}/{pid}", json={"state": "Johor", "mukim": "Tebrau"})
    assert upd.status_code == 200, upd.text
    assert (upd.json()["state"], upd.json()["mukim"]) == ("Johor", "Tebrau")


def test_e1_a_project_without_them_returns_nulls(world):
    from ._sample_request_seed import make_customer

    from ._lead_governs_register_support import staff_lead

    customer_id = make_customer(world.db, world.company_id).id
    lead_id = staff_lead(world.db, world.company_id, world.staff, customer_id)
    world.db.commit()
    made = as_user(world, world.staff).post(
        f"{STAFF}/", json={"title": "ZZT PLAIN TOWER", "customer_id": customer_id, "lead_id": lead_id}
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert "state" in body and body["state"] is None
    assert "mukim" in body and body["mukim"] is None


# ------------------------------------------------------------------ F2 decision notices


def test_f2_approve_and_reject_notify_the_linked_crm_user(world):
    ok = pending(world)
    world.sent.clear()
    assert approve(world, ok).status_code == 200
    assert {user for user, _t in world.sent} == {world.applicant_user}

    no = pending(world)
    world.sent.clear()
    assert reject(world, no).status_code == 200
    assert {user for user, _t in world.sent} == {world.applicant_user}


def test_f2_no_linked_user_means_no_error_and_nobody_notified(world):
    rid = pending(world, world.b)
    world.sent.clear()
    assert approve(world, rid).status_code == 200
    other = pending(world, world.b)
    world.sent.clear()
    assert reject(world, other).status_code == 200
    assert world.sent == []


def test_f2_the_approved_notice_names_the_code_and_links_to_the_project(world):
    rid = pending(world)
    world.sent_kw.clear()
    approve(world, rid)
    kw = next(k for k in world.sent_kw if k["type"] == "project_registration_approved")
    assert ppf_code(5) in kw["title"]
    assert "None" not in kw["title"] and "None" not in kw["body"]
    assert kw["data"]["link"] == f"/project-sales/{rid}"


def test_f2_the_rejected_notice_links_to_nothing_stale(world):
    rid = pending(world)
    world.sent_kw.clear()
    reject(world, rid)
    kw = next(k for k in world.sent_kw if k["type"] == "project_registration_rejected")
    assert "None" not in kw["title"] and "None" not in kw["body"]
    assert "registrations" not in str(kw["data"])


# ------------------------------------------------------------------ N12 drafts


def test_n12_a_contacts_unsent_drafts_are_in_no_list_whatever_the_filter(world):
    draft = create_draft(world)["id"]
    sent = pending(world)
    for params in ({}, {"approval_state": "pending"}, {"approved_only": "true"}, {"limit": 100}):
        ids = _ids(as_user(world, world.staff).get(LIST, params=params))
        assert draft not in ids, params
    assert sent in _ids(as_user(world, world.staff).get(LIST))
