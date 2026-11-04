"""AGENTIC-UNIFY PR 4, slice 1: the projects route narrows a `.view_own` panel user to their own rows (AC-2).

The panel's read is the shared key plus `X-Staff-User: <user id>` (`tests/test_staff_read_identity.py`). The
shared key's act-as user here is a superadmin, the case where a route that did NOT run as the staff member would
show every project. Real app, real route, real RBAC rows, real session; every row is seeded here.

This pins existing route behaviour (projects and complaints `view_own` narrowing, the active company on a
staff read) so the tool's `own_permission` rests on a
measured fact. It is expected to pass before the coder starts.
"""
from __future__ import annotations

import uuid

from datetime import date

from app.models.complaints import Complaint
from app.models.projects import Project
from tests._own_scope_support import contact as mk_contact
from tests.test_staff_read_identity import SORENTO, env, mk_company, mk_user  # noqa: F401  (env is a fixture)

PROJECTS = "/api/v1/project-sales/projects/"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"


def _project(db, owner: str, tag: str) -> str:
    code = f"ZZT-OWN-{tag}-{uuid.uuid4().hex[:6]}"
    db.add(
        Project(
            id=str(uuid.uuid4()),
            company_id=SORENTO,
            project_code=code,
            title=f"ZZT Project {code}",
            normalised_title=f"zzt project {code.lower()}",
            owner_user_id=owner,
        )
    )
    db.flush()
    return code


def _codes(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"] if isinstance(body, dict) else body
    return {r["project_code"] for r in rows}


def test_AC2_a_view_own_staff_member_gets_only_their_own_projects_through_the_real_route(env):
    db = env.db
    own_user = mk_user(db, "own", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    other_user = mk_user(db, "other", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    mine = _project(db, own_user, "MINE")
    theirs = _project(db, other_user, "THEIRS")
    db.flush()

    got = _codes(env.client.get(PROJECTS, headers=env.ident(own_user)))
    assert mine in got
    assert theirs not in got, "a view_own staff member read another user's project"


def test_AC2_control_a_view_holder_through_the_same_route_sees_both(env):
    db = env.db
    viewer = mk_user(db, "viewer", perms=[VIEW], companies=(SORENTO,), last_active=SORENTO)
    owner_a = mk_user(db, "a", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    owner_b = mk_user(db, "b", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    first = _project(db, owner_a, "A")
    second = _project(db, owner_b, "B")
    db.flush()

    got = _codes(env.client.get(PROJECTS, headers=env.ident(viewer)))
    assert {first, second} <= got


# ------------------------------------------------------------------ complaints: view_own through the real route

COMPLAINTS = "/api/v1/complaints-management/complaints/"
C_VIEW = "complaint_management.complaints.view"
C_OWN = "complaint_management.complaints.view_own"


def _complaint(db, tag: str, owner_contact) -> str:
    number = f"ZZT-CMP-{tag}-{uuid.uuid4().hex[:6]}"
    db.add(
        Complaint(
            id=str(uuid.uuid4()),
            complaint_number=number,
            customer_name=f"ZZT Customer {tag}",
            status="processed_by_cs",
            complaint_date=date(2026, 6, 2),
            contact_id=str(owner_contact.id),
        )
    )
    db.flush()
    return number


def _numbers(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"] if isinstance(body, dict) else body
    return {r["complaint_number"] for r in rows}


def test_AC2_a_view_own_staff_member_gets_only_the_complaints_their_contact_submitted(env):
    db = env.db
    mine_contact, other_contact = mk_contact(db, "mine"), mk_contact(db, "other")
    staff = mk_user(db, "cown", perms=[C_OWN], companies=(SORENTO,), last_active=SORENTO, contact_id=mine_contact.id)
    mine = _complaint(db, "MINE", mine_contact)
    theirs = _complaint(db, "THEIRS", other_contact)
    db.flush()

    got = _numbers(env.client.get(COMPLAINTS, headers=env.ident(staff)))
    assert mine in got
    assert theirs not in got, "a view_own staff member read a complaint their contact did not submit"


def test_AC2_control_a_complaints_view_holder_through_the_same_route_sees_both(env):
    db = env.db
    a, b = mk_contact(db, "a"), mk_contact(db, "b")
    viewer = mk_user(db, "cview", perms=[C_VIEW], companies=(SORENTO,), last_active=SORENTO)
    first, second = _complaint(db, "A", a), _complaint(db, "B", b)
    db.flush()

    got = _numbers(env.client.get(COMPLAINTS, headers=env.ident(viewer)))
    assert {first, second} <= got


# ------------------------------------------------------------------ AC-6: a staff read covers the active company only


def _project_in(db, company_id: str, tag: str, owner: str) -> str:
    code = f"ZZT-CO-{tag}-{uuid.uuid4().hex[:6]}"
    db.add(
        Project(
            id=str(uuid.uuid4()),
            company_id=company_id,
            project_code=code,
            title=f"ZZT Project {code}",
            normalised_title=f"zzt project {code.lower()}",
            owner_user_id=owner,
        )
    )
    db.flush()
    return code


def test_AC6_a_staff_projects_read_returns_only_the_active_companys_rows(env):
    """Projects carry `company_id`. A staff member granted both companies reads the active one only."""
    db = env.db
    staff = mk_user(db, "two", perms=[VIEW], companies=(SORENTO, env.co_b), last_active=SORENTO)
    here = _project_in(db, SORENTO, "A", staff)
    there = _project_in(db, env.co_b, "B", staff)
    db.flush()

    got = _codes(env.client.get(PROJECTS, headers=env.ident(staff)))
    assert here in got
    assert there not in got, "a staff read returned a project of a company that is not the active one"


def test_AC6_complaints_have_no_company_column_so_a_staff_read_is_not_company_scoped(env):
    """Measured, not assumed: `complaints` has no `company_id` (`app/models/complaints.py`), so the route returns
    the same complaints whichever company the staff member is working in. The UAC's 'active company only' holds
    for projects; for complaints it is a fact of the table, pinned here so a change is seen."""
    db = env.db
    contact_row = mk_contact(db, "any")
    number = _complaint(db, "GLOBAL", contact_row)
    in_a = mk_user(db, "ca", perms=[C_VIEW], companies=(SORENTO,), last_active=SORENTO)
    in_b = mk_user(db, "cb", perms=[C_VIEW], companies=(env.co_b,), last_active=env.co_b)
    db.flush()

    assert number in _numbers(env.client.get(COMPLAINTS, headers=env.ident(in_a)))
    assert number in _numbers(env.client.get(COMPLAINTS, headers=env.ident(in_b)))


# ------------------------------------------------------------------ the buyer's phone and main contact (security review)

CUSTOMERS_VIEW = "order_management.customers.view"
PROJECT_DETAIL = "/api/v1/project-sales/projects/"


def _project_with_a_buyer_and_main_contact(env):
    """A project whose buyer has an office phone and a main contact with a name."""
    from app.models.order import CustomerContact
    from tests.test_staff_read_identity import _project_with_a_customer

    project = _project_with_a_customer(env, "0312345678")
    from app.models.projects import ProjectSalesProfile

    customer_id = env.db.query(ProjectSalesProfile.customer_id).filter(ProjectSalesProfile.project_id == project.id).scalar()
    env.db.add(
        CustomerContact(
            id=str(uuid.uuid4()), customer_id=customer_id, full_name="ZZT Main Contact", phone="0399999999",
            contact_role="main", company_id=SORENTO,
        )
    )
    env.db.flush()
    return project


def _row(env, user, project):
    listed = env.client.get(PROJECTS, params={"limit": 100}, headers=env.ident(user))
    assert listed.status_code == 200, listed.text[:300]
    (row,) = [r for r in listed.json()["data"] if r["id"] == project.id]
    detail = env.client.get(f"{PROJECT_DETAIL}{project.id}", headers=env.ident(user))
    assert detail.status_code == 200, detail.text[:300]
    return row, detail.json()


def test_SEC_a_panel_read_without_the_customers_slug_shows_no_phone_and_no_main_contact(env):
    env.use_actas(perms=[VIEW, CUSTOMERS_VIEW])
    project = _project_with_a_buyer_and_main_contact(env)
    staff = mk_user(env.db, "nocust", perms=[VIEW], companies=(SORENTO,), last_active=SORENTO)
    for body in _row(env, staff, project):
        assert body["customer_phone"] is None and body["customer_attn"] is None, body
        assert "ZZT Main Contact" not in str(body)


def test_SEC_a_panel_read_with_the_customers_slug_shows_the_phone_and_the_main_contact(env):
    env.use_actas(perms=[VIEW, CUSTOMERS_VIEW])
    project = _project_with_a_buyer_and_main_contact(env)
    staff = mk_user(env.db, "cust", perms=[VIEW, CUSTOMERS_VIEW], companies=(SORENTO,), last_active=SORENTO)
    for body in _row(env, staff, project):
        assert body["customer_phone"] == "0312345678", body
        assert body["customer_attn"] == "ZZT Main Contact", body
