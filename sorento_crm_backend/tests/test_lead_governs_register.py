"""LEAD-GOVERNS-REGISTER Phase 2 red tests: UAC B (lead API), E (project API), F (qualify).

UAC: documentation/plans/projects/lead-governs-register-acceptance-criteria.md.
A lead must carry a customer (B); a project must come from a lead and takes the lead's
customer (E); qualify carries the customer across (F). Edit holder = `v2.owner` (view + edit).
Submit-only salesperson paths live in `test_lead_governs_register_rbac.py` (E6, H).
"""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._lead_governs_register_support import (
    LEADS,
    LIST,
    STAFF,
    customer_count,
    lead_row,
    new_customer,
    profile_of,
    project_of,
    projects_titled,
    reload_lead,
    title,
)
from ._project_register_v2_support import as_user, v2  # noqa: F401
from ._project_registration_support import project as seed_project

# ------------------------------------------------------------------ B. lead API


def test_b1_a_lead_without_a_customer_is_refused(v2):
    res = as_user(v2, v2.owner).post(LEADS, json={"title": title("Lead")})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "lead_customer_required"


def test_b1_a_lead_with_a_customer_is_created(v2):
    res = as_user(v2, v2.owner).post(
        LEADS, json={"title": title("Lead"), "customer_id": v2.customer.id}
    )
    assert res.status_code == 201, res.text
    assert res.json()["customer_id"] == v2.customer.id


def test_b2_new_customer_alone_is_refused_and_creates_no_customer(v2):
    before = customer_count(v2)
    res = as_user(v2, v2.owner).post(
        LEADS,
        json={"title": title("Lead"), "new_customer": {"customer_name": "CONTOH Inline Buyer"}},
    )
    assert res.status_code == 422, res.text
    assert customer_count(v2) == before


def test_b3_the_customer_may_change_to_another_existing_customer(v2):
    other = new_customer(v2)
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{LEADS}/{lead.id}", json={"customer_id": other.id})
    assert res.status_code == 200, res.text
    assert reload_lead(v2, lead.id).customer_id == other.id


def test_b3_clearing_the_customer_of_a_lead_that_has_one_is_refused(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{LEADS}/{lead.id}", json={"customer_id": None})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "lead_customer_required"
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_b3_a_lead_that_never_had_a_customer_can_still_be_updated(v2):
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{LEADS}/{lead.id}", json={"notes": "Site visit booked"})
    assert res.status_code == 200, res.text
    row = reload_lead(v2, lead.id)
    assert row.notes == "Site visit booked"
    assert row.customer_id is None


# ------------------------------------------------------------------ E. project API (edit holder)


def _register(w, **body):
    return as_user(w, w.owner).post(LIST, json=body)


def test_e1_registering_without_a_lead_is_refused_and_creates_no_project(v2):
    name = title("NoLead")
    res = _register(v2, title=name, customer_id=v2.customer.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_required"
    assert projects_titled(v2, name) == 0


def test_e2_the_project_takes_the_customer_of_its_lead(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    name = title("FromLead")
    res = _register(v2, title=name, lead_id=lead.id)
    assert res.status_code == 201, res.text
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id


def test_e2_an_equal_customer_in_the_request_is_accepted(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    res = _register(v2, title=title("Equal"), lead_id=lead.id, customer_id=v2.customer.id)
    assert res.status_code == 201, res.text
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id


def test_e2_a_different_customer_than_the_leads_is_refused_and_nothing_changes(v2):
    other = new_customer(v2)
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    name = title("Mismatch")
    res = _register(v2, title=name, lead_id=lead.id, customer_id=other.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_not_lead_customer"
    assert projects_titled(v2, name) == 0
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_e3_a_lead_without_a_customer_needs_one_on_the_request(v2):
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    name = title("NeedsCustomer")
    res = _register(v2, title=name, lead_id=lead.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_required"
    assert projects_titled(v2, name) == 0


def test_e3_the_picked_customer_is_stored_and_fills_the_empty_lead(v2):
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    res = _register(v2, title=title("FillsLead"), lead_id=lead.id, customer_id=v2.customer.id)
    assert res.status_code == 201, res.text
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_e5_a_lead_already_linked_to_a_project_is_409(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    first = _register(v2, title=title("First"), lead_id=lead.id, customer_id=v2.customer.id)
    assert first.status_code == 201, first.text
    second = _register(v2, title=title("Second"), lead_id=lead.id, customer_id=v2.customer.id)
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "lead_already_linked"


def test_e4_changing_the_lead_sets_the_customer_of_the_new_lead(v2):
    other = new_customer(v2)
    first = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    second = lead_row(v2, customer_id=other.id, owner=v2.owner)
    made = _register(v2, title=title("Switch"), lead_id=first.id, customer_id=v2.customer.id)
    assert made.status_code == 201, made.text
    pid = made.json()["id"]

    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"lead_id": second.id})
    assert res.status_code == 200, res.text
    assert project_of(v2, pid).lead_id == second.id
    assert profile_of(v2, pid).customer_id == other.id


def test_e4_changing_to_a_lead_with_another_customer_than_requested_is_refused(v2):
    other = new_customer(v2)
    third = new_customer(v2)
    first = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    second = lead_row(v2, customer_id=other.id, owner=v2.owner)
    pid = _register(
        v2, title=title("SwitchBad"), lead_id=first.id, customer_id=v2.customer.id
    ).json()["id"]

    res = as_user(v2, v2.owner).put(
        f"{STAFF}/{pid}", json={"lead_id": second.id, "customer_id": third.id}
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_not_lead_customer"
    assert project_of(v2, pid).lead_id == first.id
    assert profile_of(v2, pid).customer_id == v2.customer.id


def _give_customer(w, project_id, customer_id):
    from app.models.projects import ProjectSalesProfile

    w.db.add(ProjectSalesProfile(project_id=project_id, customer_id=customer_id))
    w.db.commit()


def test_e4_linking_a_customerless_lead_fills_its_empty_customer_from_the_project(v2):
    old = seed_project(v2.db, v2.company_id, title("Filler"), owner=v2.owner)
    _give_customer(v2, old.id, v2.customer.id)
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{old.id}", json={"lead_id": lead.id})
    assert res.status_code == 200, res.text
    assert project_of(v2, old.id).lead_id == lead.id
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_e4_linking_never_overwrites_a_lead_customer_that_is_set(v2):
    other = new_customer(v2)
    old = seed_project(v2.db, v2.company_id, title("Keeper"), owner=v2.owner)
    _give_customer(v2, old.id, v2.customer.id)
    lead = lead_row(v2, customer_id=other.id, owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{old.id}", json={"lead_id": lead.id})
    assert res.status_code == 200, res.text
    assert reload_lead(v2, lead.id).customer_id == other.id
    assert profile_of(v2, old.id).customer_id == other.id


def test_e4_an_edit_without_a_lead_change_leaves_the_stored_customer(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    pid = _register(
        v2, title=title("Keep"), lead_id=lead.id, customer_id=v2.customer.id
    ).json()["id"]
    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"title": title("Renamed")})
    assert res.status_code == 200, res.text
    assert profile_of(v2, pid).customer_id == v2.customer.id
    assert project_of(v2, pid).lead_id == lead.id


def test_e4_an_old_project_without_a_lead_still_saves_without_one(v2):
    old = seed_project(v2.db, v2.company_id, title("Old"), owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{old.id}", json={"title": title("Old renamed")})
    assert res.status_code == 200, res.text
    assert project_of(v2, old.id).lead_id is None


# ------------------------------------------------------------------ F. qualify


def test_f1_qualifying_a_lead_with_a_customer_gives_the_project_that_customer(v2):
    lead = lead_row(v2, customer_id=v2.customer.id, owner=v2.owner)
    res = as_user(v2, v2.owner).post(f"{LEADS}/{lead.id}/qualify", json={"title": title("Q")})
    assert res.status_code == 201, res.text
    profile = profile_of(v2, res.json()["id"])
    assert profile is not None, "qualify wrote no sales profile"
    assert profile.customer_id == v2.customer.id


def test_f1_a_lead_without_a_customer_qualifies_as_before(v2):
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    res = as_user(v2, v2.owner).post(f"{LEADS}/{lead.id}/qualify", json={"title": title("Q")})
    assert res.status_code == 201, res.text
    profile = profile_of(v2, res.json()["id"])
    assert profile is None or profile.customer_id is None


def test_e4_a_later_customer_pick_without_a_lead_change_fills_the_empty_lead(v2):
    old = seed_project(v2.db, v2.company_id, title("LinkedEmpty"), owner=v2.owner)
    lead = lead_row(v2, customer_id=None, owner=v2.owner)
    old.lead_id = lead.id
    v2.db.commit()
    res = as_user(v2, v2.owner).put(f"{STAFF}/{old.id}", json={"customer_id": v2.customer.id})
    assert res.status_code == 200, res.text
    assert profile_of(v2, old.id).customer_id == v2.customer.id
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id
