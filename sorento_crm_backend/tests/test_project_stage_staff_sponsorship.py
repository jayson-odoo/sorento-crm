"""PROJECT-STAGE-ACTIONS: staff write a sponsorship form in the salesperson's form.

Plan: documentation/plans/project-sales/PLAN-project-stage-actions-11nov.md.

A project's Sponsorship stage opens the SAME form a salesperson fills in (the portal
SubmissionForm). For staff it saves through the staff create (a draft) and submits through
`POST /purchase-requests/{id}/submit`, which runs the portal's submit rules and side effects
(`PortalService.submit_staff_request`), on behalf of the project's salesperson: the project
carries that person's contact (`owner_contact_id`) for Requested by.

Harness: tests/_forms_chain_support.py (real routes on a blank Postgres scratch schema).
"""
from __future__ import annotations

from tests._forms_chain_support import (
    PR_BASE,
    SORENTO,
    contact,
    grant,
    trackers,
    sla_chain,
    user,
    world,  # noqa: F401  (fixture)
)

ADD = "procurement.sponsorship_forms.add"
VIEW = "procurement.sponsorship_forms.view"
PROJECTS = "/api/v1/project-sales/projects"


def _staff(w, *slugs):
    staff = user(w.db, "sponsorship staff")
    grant(w.db, staff, *slugs)
    w.db.commit()
    return staff


def _draft(w, staff, salesperson):
    res = w.as_user(staff).post(
        PR_BASE,
        json={
            "request_type": "sponsorship_form",
            "customer_name": "ZZT Example Trading",
            "pic": "Ann 012-0000000",
            "delivery_address": "1 Example Road",
            "project_title": "ZZT Tower",
            "requested_by_contact_id": salesperson,
            "contact_id": salesperson,
            "products": [
                {"item_code": "ZZT-TILE-1", "quantity": 4, "unit_price": 25, "total": 100},
            ],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "draft"
    return res.json()["id"]


def test_staff_submit_moves_the_draft_the_way_the_portal_submit_does(world):
    w = world
    salesperson = contact(w.db, name="project salesperson")
    staff = _staff(w, ADD, VIEW)
    rid = _draft(w, staff, salesperson)

    res = w.as_user(staff).post(f"{PR_BASE}/{rid}/submit")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"]
    assert body["request_number"]
    # On behalf of the salesperson: they are Requested by, and the form is theirs.
    assert body["requested_by_contact_id"] == salesperson
    assert body["contact_id"] == salesperson
    # Submitted with no date: it takes today's (Malaysia), so the project tab's "Requested" shows it.
    from datetime import datetime

    from app.utils.date_format import MY_TZ

    assert body["request_date"] == datetime.now(MY_TZ).date().isoformat()


def test_staff_submit_starts_the_form_sla_like_a_salesperson_submit(world):
    w = world
    sla_chain(w.db, "sponsorship_form", [dict(start_event="submit", resolve_event="voided")])
    salesperson = contact(w.db, name="sla salesperson")
    staff = _staff(w, ADD, VIEW)
    rid = _draft(w, staff, salesperson)

    assert w.as_user(staff).post(f"{PR_BASE}/{rid}/submit").status_code == 200

    assert trackers(w.db, "sponsorship_form", rid), "submit did not start the form SLA"


def test_staff_submit_needs_the_add_permission(world):
    w = world
    salesperson = contact(w.db, name="no-add salesperson")
    writer = _staff(w, ADD, VIEW)
    reader = _staff(w, VIEW)
    rid = _draft(w, writer, salesperson)

    res = w.as_user(reader).post(f"{PR_BASE}/{rid}/submit")

    assert res.status_code == 403, res.text


def test_staff_save_refuses_a_sponsorship_line_without_a_unit_price(world):
    """Stricter than a portal draft, and on purpose not loosened here: the staff create has
    always refused it (#1227). The form names the line ("Line 1: Unit price is required.")."""
    w = world
    salesperson = contact(w.db, name="price salesperson")
    staff = _staff(w, ADD, VIEW)

    res = w.as_user(staff).post(
        PR_BASE,
        json={
            "request_type": "sponsorship_form",
            "requested_by_contact_id": salesperson,
            "products": [{"item_code": "ZZT-TILE-1", "quantity": 4}],
        },
    )

    assert res.status_code == 422, res.text
    assert res.json()["detail"] == "line:0"


def test_staff_submit_only_submits_a_draft(world):
    w = world
    salesperson = contact(w.db, name="twice salesperson")
    staff = _staff(w, ADD, VIEW)
    rid = _draft(w, staff, salesperson)
    assert w.as_user(staff).post(f"{PR_BASE}/{rid}/submit").status_code == 200

    again = w.as_user(staff).post(f"{PR_BASE}/{rid}/submit")

    # The portal submit's own refusal (`handle_validation_error`), word for word.
    assert again.status_code == 400, again.text
    assert "status 'submitted'" in again.json()["message"]


def test_the_project_carries_its_salespersons_contact(world):
    from app.models.user import User
    from tests._project_registration_support import numbering_rule
    from tests._sample_request_seed import make_project

    w = world
    salesperson_contact = contact(w.db, name="owner contact")
    owner = user(w.db, "project owner")
    w.db.query(User).filter(User.id == owner).update({"respond_contact_id": salesperson_contact})
    grant(w.db, owner, "projects.projects.view", "projects.projects.edit")
    numbering_rule(w.db)
    project = make_project(w.db, SORENTO, owner)
    w.db.commit()

    res = w.as_user(owner).get(f"{PROJECTS}/{project.id}")

    assert res.status_code == 200, res.text
    assert res.json()["owner_contact_id"] == salesperson_contact
    # The contact's name, as the saved form's Requested by prints it, not the user's name.
    assert res.json()["owner_contact_name"].endswith("owner contact")


def test_staff_submit_refuses_a_salespersons_own_portal_draft(world):
    """Security review S1: their own draft is theirs to submit, and their contact's
    registered-project rule must not be skipped by a staff submit."""
    from tests._forms_chain_support import SUB

    w = world
    salesperson = contact(w.db, name="portal draft salesperson")
    staff = _staff(w, ADD, VIEW)
    w.db.commit()
    res = w.as_contact(salesperson).post(
        f"{SUB}/sponsorship_form",
        json={
            "fields": {"customer_name": "ZZT Example Trading", "requested_by_contact_id": salesperson},
            "products": [{"item_code": "ZZT-TILE-1", "quantity": 4, "unit_price": 25, "total": 100}],
        },
    )
    assert res.status_code == 200, res.text
    rid = res.json()["id"]

    refused = w.as_user(staff).post(f"{PR_BASE}/{rid}/submit")

    assert refused.status_code == 400, refused.text
    assert w.as_user(staff).get(f"{PR_BASE}/{rid}").json()["status"] == "draft"


def test_staff_submit_clears_an_approval_stamp_set_at_create(world):
    """Security review S2: the staff create accepts approval fields; a submitted form must
    reach the office with no approval on it."""
    w = world
    salesperson = contact(w.db, name="stamp salesperson")
    staff = _staff(w, ADD, VIEW)
    res = w.as_user(staff).post(
        PR_BASE,
        json={
            "request_type": "sponsorship_form",
            "customer_name": "ZZT Example Trading",
            "pic": "Ann 012-0000000",
            "delivery_address": "1 Example Road",
            "project_title": "ZZT Tower",
            "requested_by_contact_id": salesperson,
            "contact_id": salesperson,
            "approval_status": "approved",
            "approved_by": staff,
            "approval_signature_ref": "zzt-forged",
            "products": [{"item_code": "ZZT-TILE-1", "quantity": 4, "unit_price": 25, "total": 100}],
        },
    )
    assert res.status_code == 201, res.text
    rid = res.json()["id"]

    done = w.as_user(staff).post(f"{PR_BASE}/{rid}/submit")

    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "submitted"
    assert body["approval_status"] is None
    assert body.get("approval_signature_ref") is None
