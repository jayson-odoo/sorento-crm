"""PS-REGISTER-CHECK-FIRST UAC L2-L5: registration has no lead.

A lead_id sent on register / submit is ignored: no project.lead_id, and the lead's outcome,
qualified_at and status are untouched. Customer is still required to submit.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._lead_governs_register_support import (
    LIST,
    STAFF,
    lead_row,
    profile_of,
    project_of,
    reload_lead,
    title,
)
from ._project_register_v2_support import as_user, submit_existing, v2  # noqa: F401


def _snapshot(lead):
    return (lead.outcome, lead.qualified_at, getattr(lead, "status_id", None))


# ------------------------------------------------------------------ L2 staff


def test_ac_l2_staff_register_without_lead_id_is_201_with_no_lead(v2):
    res = as_user(v2, v2.owner).post(LIST, json={"title": title("L2"), "customer_id": v2.customer.id})
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id is None
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id


def test_ac_l4_staff_register_with_a_lead_id_links_nothing_and_leaves_the_lead(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    before = _snapshot(lead)
    res = as_user(v2, v2.owner).post(
        LIST, json={"title": title("L4"), "customer_id": v2.customer.id, "lead_id": lead.id}
    )
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id is None
    assert _snapshot(reload_lead(v2, lead.id)) == before


def test_ac_l2_the_project_customer_is_the_one_sent_not_the_leads(v2):
    from ._lead_governs_register_support import new_customer

    other = new_customer(v2)
    lead = lead_row(v2, customer_id=other.id, owner=v2.owner)
    res = as_user(v2, v2.owner).post(
        LIST, json={"title": title("L2c"), "customer_id": v2.customer.id, "lead_id": lead.id}
    )
    assert res.status_code == 201, res.text
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id


def test_ac_l2_staff_register_still_needs_a_customer(v2):
    res = as_user(v2, v2.owner).post(LIST, json={"title": title("L2n")})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_required"


# ------------------------------------------------------------------ L3 / L4 submit-only


def _sub(w, **body):
    return as_user(w, w.sub_a).post(LIST, json={"title": title("L3"), **body})


def test_ac_l3_submit_only_draft_without_a_lead_saves(v2):
    res = _sub(v2, submit=False)
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id is None


def test_ac_l3_submit_only_submit_without_a_lead_goes_pending(v2):
    res = _sub(v2, submit=True, customer_id=v2.customer.id)
    assert res.status_code == 201, res.text
    row = project_of(v2, res.json()["id"])
    assert row.approval_state == "pending" and row.lead_id is None


def test_ac_l3_crm_register_service_needs_no_lead_but_a_customer(v2):
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    row = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=v2.sub_a,
        payload={"title": title("L3s"), "customer_id": v2.customer.id}, submit=True,
    )
    assert row.approval_state == "pending" and row.lead_id is None
    with pytest.raises(AppException) as exc:
        svc.crm_register(
            v2.db, company_id=v2.company_id, user_id=v2.sub_a,
            payload={"title": title("L3x")}, submit=True,
        )
    assert exc.value.code == "project_customer_required"


def test_ac_l3_crm_submit_needs_no_lead_but_a_customer(v2):
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    sub = {"projects.registrations.submit"}
    ok = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=v2.sub_a,
        payload={"title": title("L3d"), "customer_id": v2.customer.id}, submit=False,
    )
    v2.db.flush()
    svc.crm_submit(v2.db, ok, user_id=v2.sub_a, payload={}, permissions=sub)
    assert ok.approval_state == "pending"

    bare = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=v2.sub_a, payload={"title": title("L3e")}, submit=False
    )
    v2.db.flush()
    with pytest.raises(AppException) as exc:
        svc.crm_submit(v2.db, bare, user_id=v2.sub_a, payload={}, permissions=sub)
    assert exc.value.code == "project_customer_required"


def test_ac_l4_submit_with_a_lead_id_leaves_the_lead_unchanged(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_a)
    before = _snapshot(lead)
    res = _sub(v2, submit=True, customer_id=v2.customer.id, lead_id=lead.id)
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id is None
    assert _snapshot(reload_lead(v2, lead.id)) == before


def test_ac_l4_submitting_a_draft_with_a_lead_id_leaves_the_lead_unchanged(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_a)
    before = _snapshot(lead)
    pid = _sub(v2, submit=False, customer_id=v2.customer.id).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid, {"lead_id": lead.id})
    assert res.status_code == 200, res.text
    assert project_of(v2, pid).lead_id is None
    assert _snapshot(reload_lead(v2, lead.id)) == before


# ------------------------------------------------------------------ L5 editing keeps a held lead


def test_ac_l5_editing_a_project_that_has_a_lead_keeps_it_when_no_lead_id_is_sent(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    from ._project_registration_support import project as seed_project

    row = seed_project(v2.db, v2.company_id, title("L5"), owner=v2.owner)
    row.lead_id = lead.id
    v2.db.commit()
    pid = row.id
    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"title": title("L5 renamed")})
    assert res.status_code == 200, res.text
    assert project_of(v2, pid).lead_id == lead.id


# ------------------------------------------------------------------ L5 an edit ignores lead_id too


def _linked(w, lead):
    from ._project_registration_support import project as seed_project
    from app.models.projects import ProjectSalesProfile

    row = seed_project(w.db, w.company_id, title("L5e"), owner=w.owner)
    w.db.add(ProjectSalesProfile(project_id=row.id, customer_id=w.customer.id))
    row.lead_id = lead.id
    w.db.commit()
    return row.id


def test_ac_l5_put_with_a_different_lead_id_changes_nothing_about_the_leads(v2):
    from ._lead_governs_register_support import new_customer

    other_customer = new_customer(v2)
    first = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    second = lead_row(v2, customer_id=None, owner=v2.owner)
    before = (_snapshot(first), first.customer_id, _snapshot(second), second.customer_id)
    pid = _linked(v2, first)
    res = as_user(v2, v2.owner).put(
        f"{STAFF}/{pid}", json={"lead_id": second.id, "customer_id": other_customer.id}
    )
    assert res.status_code == 200, res.text
    assert project_of(v2, pid).lead_id == first.id
    assert profile_of(v2, pid).customer_id == other_customer.id
    a, b = reload_lead(v2, first.id), reload_lead(v2, second.id)
    assert (_snapshot(a), a.customer_id, _snapshot(b), b.customer_id) == before


def test_ac_l5_put_with_a_customer_other_than_the_linked_leads_is_not_refused(v2):
    from ._lead_governs_register_support import new_customer

    other_customer = new_customer(v2)
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    pid = _linked(v2, lead)
    res = as_user(v2, v2.owner).put(
        f"{STAFF}/{pid}", json={"lead_id": lead.id, "customer_id": other_customer.id}
    )
    assert res.status_code == 200, res.text
    assert profile_of(v2, pid).customer_id == other_customer.id
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_ac_l5_a_customer_pick_on_an_edit_never_fills_the_linked_leads_empty_customer(v2):
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    pid = _linked(v2, lead)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"customer_id": v2.customer.id})
    assert res.status_code == 200, res.text
    assert reload_lead(v2, lead.id).customer_id is None
