"""PROJECT-REG-PORTAL rework fix round 3 (reviewer, security and browser findings), red-first.

Each block names the finding it pins: 4 linked-project validators (purchase request, complaint),
6 the embedding backfill, 7 (S1) machine callers never read an unapproved project, 8 (S2) only a
manager deletes an unapproved one, 9 (N1) PUT checks the company of every id, 10 (N2) a draft is
nobody's read, 11 (N3) no takeover request on an unapproved project, 14 the rejected label, 16 the
sort order of nullable columns.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    LIST,
    STAFF,
    approve,
    as_user,
    create_draft,
    developer,
    pending,
    project,
    project_type,
    reject,
    world,  # noqa: F401  (fixture)
)

MACHINE = ("api_key", "integration_api_key", "connector")


def _as_machine(world, auth_method: str):
    from app.dependencies import get_current_user_or_api_key

    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": world.staff,
        "email": f"{world.staff}@zzt.test",
        "auth_method": auth_method,
    }
    return world.c


# ------------------------------------------------------------------ 4 linked-project validators


def _purchase_request(world, project_id):
    from app.models.procurement import PurchaseRequestHeader

    row = PurchaseRequestHeader(
        request_type="purchase_request",
        status="draft",
        contact_id=world.a,
        space_id="zzt-space",
        project_id=project_id,
        customer_name="zzt customer",
        portal_draft_at=datetime.utcnow(),
    )
    world.db.add(row)
    world.db.flush()
    return row


def test_4_a_portal_purchase_request_naming_an_unapproved_project_is_refused_on_submit(world):
    from ._project_registration_support import as_contact

    for state in ("pending", "rejected"):
        hidden = project(world.db, world.company_id, f"PR target {state}", approval_state=state)
        row = _purchase_request(world, hidden.id)
        res = as_contact(world, world.a).post(f"/api/v1/public/portal/submissions/purchase_request/{row.id}/submit")
        assert res.status_code == 422, (state, res.status_code, res.text)
        assert res.json()["code"] == "purchase_request_project_not_approved"


def test_4_the_same_submit_with_an_approved_project_is_not_refused_for_approval(world):
    from ._project_registration_support import as_contact

    ok = project(world.db, world.company_id, "PR target approved", approval_state="approved", code="PPF2601061")
    row = _purchase_request(world, ok.id)
    res = as_contact(world, world.a).post(f"/api/v1/public/portal/submissions/purchase_request/{row.id}/submit")
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("code") != "purchase_request_project_not_approved", res.text


def test_4_a_staff_complaint_cannot_be_created_or_updated_onto_an_unapproved_project(world):
    from app.schemas.complaints import ComplaintCreate, ComplaintUpdate
    from app.services.complaints_service import ComplaintService
    from app.services.error_handler import AppException

    hidden = project(world.db, world.company_id, "Complaint target pending", approval_state="pending")
    ok = project(world.db, world.company_id, "Complaint target approved", approval_state="approved", code="PPF2601062")
    service = ComplaintService(world.db)
    with pytest.raises(AppException) as exc:
        service.create_complaint(ComplaintCreate(project_id=hidden.id, defect_description="zzt crack"))
    assert exc.value.detail["code"] == "complaint_project_not_approved"

    made = service.create_complaint(ComplaintCreate(project_id=ok.id, defect_description="zzt crack"))
    with pytest.raises(AppException) as exc:
        service.update_complaint(str(made.id), ComplaintUpdate(project_id=hidden.id))
    assert exc.value.detail["code"] == "complaint_project_not_approved"
    # re-saving the link it already has is fine
    service.update_complaint(str(made.id), ComplaintUpdate(project_id=ok.id, defect_description="zzt crack 2"))


# ------------------------------------------------------------------ 6 embedding backfill


def test_6_the_project_backfill_reads_approved_and_staff_projects_only(world):
    from app.services.embedding_backfill_service import EmbeddingBackfillService

    staff_project = project(world.db, world.company_id, "Backfill staff", code="PRJ-ZZT-BF1")
    ok = project(world.db, world.company_id, "Backfill approved", approval_state="approved", code="PPF2601063")
    hidden = [project(world.db, world.company_id, f"Backfill {s}", approval_state=s) for s in ("draft", "pending", "rejected")]
    ids = {row["id"] for row in EmbeddingBackfillService(world.db)._fetch_rows(source="project", limit=10000, offset=0)}
    assert {staff_project.id, ok.id} <= ids
    assert not ids & {h.id for h in hidden}


# ------------------------------------------------------------------ 7 (S1) machine callers


@pytest.mark.parametrize("auth_method", MACHINE)
def test_7_a_machine_caller_gets_404_for_an_unapproved_project(world, auth_method):
    rid = pending(world)
    rej = pending(world, title="MACHINE REJECTED")
    assert reject(world, rej).status_code == 200
    ok = project(world.db, world.company_id, "MACHINE APPROVED", approval_state="approved", code="PPF2601064")
    c = _as_machine(world, auth_method)
    assert c.get(f"{STAFF}/{rid}").status_code == 404
    assert c.get(f"{STAFF}/{rej}").status_code == 404
    assert c.get(f"{STAFF}/{ok.id}").status_code == 200


# ------------------------------------------------------------------ 8 (S2) delete


def test_8_an_approver_without_manage_cannot_delete_an_unapproved_project(world):
    rid = pending(world)
    world.perms[world.coordinator].add("projects.projects.delete")
    res = as_user(world, world.coordinator).delete(f"{STAFF}/{rid}")
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_delete_forbidden"
    from ._project_registration_support import registration

    assert registration(world, rid) is not None


def test_8_a_manager_may_delete_an_unapproved_project(world):
    rid = pending(world)
    world.perms[world.approver].add("projects.projects.delete")
    res = as_user(world, world.approver).delete(f"{STAFF}/{rid}")
    assert res.status_code == 200, res.text


# ------------------------------------------------------------------ 9 (N1) company refs on PUT


def test_9_put_refuses_a_party_or_type_of_another_company(world):
    staff_project = project(world.db, world.company_id, "REFS TOWER", code="PRJ-ZZT-RF1", owner=world.root)
    foreign_dev = developer(world.db, world.other_company, "Foreign Developer")
    foreign_arch = developer(world.db, world.other_company, "Foreign Architect", "architect")
    foreign_type = project_type(world.db, world.other_company, "Foreign Type")
    own = developer(world.db, world.company_id, "Own Developer")
    world.db.commit()  # a refused PUT rolls the shared session back
    c = as_user(world, world.root)
    for body in (
        {"developer_party_id": foreign_dev.id},
        {"architect_party_id": foreign_arch.id},
        {"type_id": foreign_type.id},
    ):
        res = c.put(f"{STAFF}/{staff_project.id}", json=body)
        assert res.status_code == 422, (body, res.status_code, res.text)
    assert c.put(f"{STAFF}/{staff_project.id}", json={"developer_party_id": own.id}).status_code == 200


def test_9_put_on_a_pending_project_checks_the_company_too(world):
    rid = pending(world)
    foreign_dev = developer(world.db, world.other_company, "Foreign Developer")
    res = as_user(world, world.coordinator).put(f"{STAFF}/{rid}", json={"developer_party_id": foreign_dev.id})
    assert res.status_code == 422, res.text


# ------------------------------------------------------------------ 10 (N2) drafts


def test_10_a_draft_is_404_to_staff(world):
    draft = create_draft(world)["id"]
    for user in (world.staff, world.approver, world.root):
        assert as_user(world, user).get(f"{STAFF}/{draft}").status_code == 404, user


# ------------------------------------------------------------------ 11 (N3) takeover


@pytest.mark.parametrize("kind", ["join", "dispute"])
def test_11_no_takeover_request_on_an_unapproved_project(world, kind):
    rid = pending(world, world.third)  # owner = linked_staff, so staff is not the owner
    res = as_user(world, world.staff).post(f"{STAFF}/{rid}/takeover-requests", json={"kind": kind, "reason": "mine"})
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_not_approved"


# ------------------------------------------------------------------ 14 the rejected label


def test_14_project_label_names_a_rejected_project_rejected():
    from app.services.project_service import project_label

    assert project_label(SimpleNamespace(project_code=None, approval_state="rejected")) == "Rejected"
    assert project_label(SimpleNamespace(project_code=None, approval_state="pending")) == "Awaiting approval"
    assert project_label(SimpleNamespace(project_code="PPF2601001", approval_state="approved")) == "PPF2601001"


def test_14_the_not_editable_refusal_on_a_rejected_project_says_rejected(world):
    rid = pending(world)
    assert reject(world, rid).status_code == 200
    res = as_user(world, world.staff).put(f"{STAFF}/{rid}", json={"mukim": "x"})
    assert res.status_code == 403
    assert "Rejected" in res.json()["message"] and "None" not in res.json()["message"]


# ------------------------------------------------------------------ 16 sort order


def _order(world, **params):
    res = as_user(world, world.staff).get(LIST, params={"limit": 200, **params})
    assert res.status_code == 200, res.text
    return [r["id"] for r in res.json()["data"]]


def test_16_a_null_activity_date_sorts_first_descending_as_it_always_did(world):
    dated = project(world.db, world.company_id, "SORT DATED", code="PRJ-ZZT-SD1")
    dated.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=1)
    undated = project(world.db, world.company_id, "SORT UNDATED", code="PRJ-ZZT-SD2")
    world.db.flush()
    order = _order(world, sort="last_meaningful_activity_at", dir="desc")
    assert order.index(undated.id) < order.index(dated.id)
    order = _order(world, sort="last_meaningful_activity_at", dir="asc")
    assert order.index(dated.id) < order.index(undated.id)


def test_16_a_project_with_no_code_sorts_last_either_way(world):
    rid = pending(world, title="SORT NO CODE")
    coded = project(world.db, world.company_id, "SORT CODED", code="PRJ-ZZT-SC1")
    for direction in ("asc", "desc"):
        order = _order(world, sort="project_code", dir=direction)
        assert order.index(coded.id) < order.index(rid), direction


# ------------------------------------------------------------------ security re-check: drafts on every staff route


def test_10b_a_draft_is_404_on_every_staff_route_even_for_a_manager(world):
    from ._project_registration_support import registration

    draft = create_draft(world)["id"]
    world.perms[world.approver].add("projects.projects.delete")
    c = as_user(world, world.approver)  # holds projects.projects.manage
    assert c.put(f"{STAFF}/{draft}", json={"mukim": "x"}).status_code == 404
    assert c.delete(f"{STAFF}/{draft}").status_code == 404
    assert c.get(f"{STAFF}/{draft}/collaborators").status_code == 404
    assert c.get(f"{STAFF}/{draft}/takeover-requests").status_code == 404
    assert registration(world, draft).approval_state == "draft"


def test_10b_the_portal_still_reads_and_deletes_its_own_draft(world):
    from ._project_registration_support import SUB, as_contact

    draft = create_draft(world)["id"]
    c = as_contact(world, world.a)
    assert c.get(f"{SUB}/{draft}").status_code == 200
    assert c.delete(f"{SUB}/{draft}").status_code == 204
