"""Shared seeding and harness for the PROJECT-REG-PORTAL suites (Phase 2, red-first).

Plan: documentation/plans/projects/PLAN-project-registration-portal-25oct.md (section REWORK,
R1-R14). UAC: documentation/plans/projects/project-registration-portal-acceptance-criteria.md
(section RW).

REWORK (owner ruling 25 Oct 17:50): a portal registration IS a `projects.projects` row
(`approval_state` draft / pending / rejected / approved, `project_code` NULL until Approve).
There is no registration table and no `/registrations` route: the CRM approves and rejects on
the project itself (`APPROVE_URL` / `REJECT_URL`). The portal submission id IS the project id.

Test support only: no implementation of the feature lives here. Everything is seeded
here, nothing is borrowed from existing rows (CI's database is empty). All names are
invented.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from ._pg_fixture import blank_session
from ._sample_request_seed import make_customer, make_user, second_company, sorento

MARKER = "zzt-prreg"
KIND = "project_registration"
PORTAL = "/api/v1/public/portal"
SUB = f"{PORTAL}/submissions/{KIND}"
STAFF = "/api/v1/project-sales/projects"
LIST = f"{STAFF}/"
#: The removed queue router (R11): every path under it must now be a 404.
OLD_CRM = f"{STAFF}/registrations"
APPROVE = "projects.registrations.approve"
MANAGE = "projects.projects.manage"


def approve_url(project_id: str) -> str:
    return f"{STAFF}/{project_id}/approve"


def reject_url(project_id: str) -> str:
    return f"{STAFF}/{project_id}/reject"


# D3 / A5: the stored fields, exactly.
FIELD_KEYS = {
    "title",
    "distributor_name",
    "customer_id",
    "customer_name",
    "type_of_building",
    "state",
    "mukim",
    "your_ref",
    "developer_name",
    "main_contractor_name",
    "architect_name",
}

ALL = "ALL"
STAFF_PERMS = {"projects.projects.view", "projects.projects.edit"}


def uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ stubs


def stub_semantic(monkeypatch, result=None) -> list:
    """Keep the meaning signal off the network and under the test's control. Returns the list
    `semantic_matches` answers with, `(project_id, cosine)` pairs: a test appends to it to say
    "the meaning signal names this project". Duplicates are named by meaning ONLY (audit round
    3), so this list is the only way a project becomes a possible duplicate in these suites.
    A module that does not exist yet is not an error here: the test's own import fails."""
    holder: list = list(result or [])
    try:
        from app.services import project_registration_service as svc
    except ImportError:
        return holder
    monkeypatch.setattr(svc, "semantic_matches", lambda db, **kw: list(holder))
    return holder


# ------------------------------------------------------------------ seeding


def numbering_rule(
    db,
    *,
    doc_type: str = "project",
    prefix: str = "PPF{yy}{mm}",
    digits: int = 3,
    next_value: int = 5,
    reset: str = "monthly",
    last_reset_key: str | None = "auto",
) -> str:
    """The `project` numbering rule (PPF for staff and queue registrations alike, owner ruling
    25 Oct: one register, one series). `last_reset_key` defaults to this month so a monthly rule
    does not reset itself to start_value on the first draw."""
    if last_reset_key == "auto":
        today = date.today()
        last_reset_key = f"{today.year}-{today.month:02d}" if reset == "monthly" else None
    rule_id = uid()
    db.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, "
            " start_value, reset_policy, last_reset_key) "
            "values (:id, 'project', true, :p, :d, :n, 1, :r, :k)"
        ),
        {"id": rule_id, "p": prefix, "d": digits, "n": next_value, "r": reset, "k": last_reset_key},
    )
    db.flush()
    return rule_id


def rule_next_value(db, rule_id: str) -> int:
    db.expire_all()
    return db.execute(
        text("select next_value from document_numbering_rules where id = :i"), {"i": rule_id}
    ).scalar()


def ppf_code(number: int, *, digits: int = 3) -> str:
    today = date.today()
    return f"PPF{today:%y%m}{str(number).zfill(digits)}"


def active_user(db, name: str) -> str:
    from app.models.user import User, UserStatus

    user_id = uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name, status=UserStatus.ACTIVE.value))
    db.flush()
    return user_id


def grant(db, user_id: str, slug: str, company_id: str) -> None:
    """Give `user_id` `slug` through a real role and a company link, the way RBAC resolves it
    (the holders query joins roles, permissions and user_companies)."""
    from app.models.company import UserCompany
    from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission

    permission = db.query(UserPermission).filter(UserPermission.slug == slug).first()
    if permission is None:
        permission = UserPermission(id=uid(), slug=slug, name=slug)
        db.add(permission)
    role = UserRole(id=uid(), slug=f"{MARKER}-{uid()[:10]}", name=f"{MARKER} {uid()[:10]}")
    db.add(role)
    db.flush()
    db.add(UserRolePermission(id=uid(), role_id=role.id, permission_id=permission.id))
    db.add(UserRoleAssignment(id=uid(), user_id=user_id, role_id=role.id))
    if not db.query(UserCompany).filter_by(user_id=user_id, company_id=company_id).first():
        db.add(UserCompany(id=uid(), user_id=user_id, company_id=company_id))
    db.flush()


def contact(db, company_id: str, *, granted: bool = True, name: str | None = None) -> str:
    from app.models.access import RespondContact

    from ._portal_grant import grant_portal_forms, link_contact_company

    row = RespondContact(
        id=uid(), phone_number=f"+60{uid().replace('-', '')[:9]}", name=name or f"{MARKER} contact"
    )
    db.add(row)
    db.flush()
    link_contact_company(db, row.id, company_id)
    if granted:
        grant_portal_forms(db, row.id, [KIND])
    return row.id


def agent(
    db,
    contact_id: str,
    *,
    code: str | None = None,
    person_label: str | None = "Aminah Example",
    description: str | None = "Aminah desk",
    active: bool = True,
):
    from app.models.sales_agent import SalesAgent

    row = SalesAgent(
        id=uid(),
        sales_agent=code or f"ZZP-{uid()[:8]}".upper(),
        description=description,
        person_label=person_label,
        is_active=active,
        contact_id=contact_id,
    )
    db.add(row)
    db.flush()
    return row


def debtor(db, company_id: str, agent_row=None):
    row = make_customer(db, company_id)
    if agent_row is not None:
        row.sales_agent_id = agent_row.id
        db.flush()
    return row


def developer(db, company_id: str, name: str, party_type: str = "developer"):
    from app.models.projects import ProjectParty

    row = ProjectParty(id=uid(), company_id=company_id, party_type=party_type, name=name)
    db.add(row)
    db.flush()
    return row


_AUTO = object()
UNAPPROVED = ("draft", "pending", "rejected")


def project(
    db,
    company_id: str,
    title: str,
    *,
    developer_party=None,
    code=_AUTO,
    outcome: str = "open",
    owner: str | None = None,
    mukim: str | None = None,
    state: str | None = None,
    approval_state: str | None = None,
    legacy: dict | None = None,
    status_id: str | None = None,
):
    """A project row straight into the database. `approval_state` None is a staff project;
    a draft / pending / rejected one has no code unless `code` is given (R2)."""
    from app.models.projects import Project, ProjectSalesProfile
    from app.services.project_clash_service import normalise_project_title

    if code is _AUTO:
        code = None if approval_state in UNAPPROVED else f"ZZT-{uid()[:8]}"
    extra = {"approval_state": approval_state} if approval_state is not None else {}
    row = Project(
        id=uid(),
        company_id=company_id,
        project_code=code,
        title=title,
        normalised_title=normalise_project_title(title),
        developer_party_id=developer_party.id if developer_party is not None else None,
        outcome=outcome,
        owner_user_id=owner,
        status_id=status_id,
        **extra,
    )
    db.add(row)
    db.flush()
    if mukim or state or legacy:
        db.add(ProjectSalesProfile(project_id=row.id, mukim=mukim, state=state, **(legacy or {})))
        db.flush()
    return row


def funnel(db) -> dict:
    """The default project funnel (registered is the initial rung), keyed by status key."""
    from app.models.status import Status
    from app.services.project_seed_service import seed_default_funnel

    seed_default_funnel(db)
    rows = db.query(Status).filter(Status.entity_type == "project", Status.scope_id.is_(None)).all()
    return {r.key: r for r in rows}


def project_type(db, company_id: str, name: str):
    from app.models.projects import ProjectType

    row = ProjectType(id=uid(), company_id=company_id, name=name, code=f"zzt-{uid()[:8]}")
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------------------ the world


def fields(customer_id: str | None = None, **over) -> dict:
    body = {
        "title": "CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI, JOHOR",
        "distributor_name": "Example Distribution Sdn Bhd",
        "customer_id": customer_id,
        "type_of_building": "Office",
        "state": "Johor",
        "mukim": "Kulai",
        "your_ref": "REF-ZZT-1",
        "developer_name": "Example Developer Sdn Bhd",
        "main_contractor_name": "Example Builders Sdn Bhd",
        "architect_name": "Example Architects",
    }
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


def _install(db, perms: dict, roles: dict, state: dict):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    from app.api.v1.public.portal import get_portal_token
    from app.models.portal import PortalToken

    def actor():
        uid_ = state["user"]
        return {"id": uid_, "email": f"{uid_}@zzt.test", "role": roles.get(uid_, "salesperson")}

    def has(self, user_id, slug):
        granted = perms.get(user_id, set())
        return granted == ALL or slug in granted

    def slugs(self, user_id):
        granted = perms.get(user_id, set())
        return set(STAFF_PERMS | {APPROVE, MANAGE}) if granted == ALL else set(granted)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = actor
    app.dependency_overrides[get_current_user_or_api_key] = actor
    app.dependency_overrides[apply_company_scope] = lambda: None
    app.dependency_overrides[get_portal_token] = lambda: PortalToken(
        id=uid(), contact_id=state["contact"], space_id="zzt-space"
    )

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
        UserPermissionService.check_user_has_any_permission,
        UserPermissionService.get_user_role_slugs,
    )
    UserPermissionService.check_user_has_permission = has
    UserPermissionService.get_user_permission_slugs = slugs
    UserPermissionService.check_user_has_any_permission = lambda self, uid_, ss: any(
        has(self, uid_, s) for s in ss
    )
    UserPermissionService.get_user_role_slugs = lambda self, uid_: (
        {roles[uid_]} if uid_ in roles else set()
    )
    return originals


def _restore(originals):
    from app.main import app
    from app.services.user_service import UserPermissionService

    (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
        UserPermissionService.check_user_has_any_permission,
        UserPermissionService.get_user_role_slugs,
    ) = originals
    app.dependency_overrides.clear()


@pytest.fixture
def world(monkeypatch):
    """Portal contacts + CRM users on one TestClient, one Postgres schema, one company scope.

    contacts: a (granted, agent), b (granted, its own agent), third (granted, agent, linked to the
    CRM user `linked_staff`), noagent (granted, no agent), ungranted. users: approver and
    applicant_user (both hold the approve grant; the latter is the CRM user linked to contact
    a), coordinator (approve + view + edit, NO manage: the Project Sales Coordinator),
    linked_staff (view + edit only, linked to contact c), staff (view + edit, cannot approve),
    root (every permission, manage included).
    """
    from fastapi.testclient import TestClient

    from app.main import app  # noqa: F401  MUST be the first app import (circular import)
    from app.models.base import company_scope
    from app.models.user import User
    from app.services.notification_service import NotificationService

    semantic = stub_semantic(monkeypatch)
    sent: list = []
    sent_kw: list = []

    def _record(self, **kw):
        sent.append((str(kw.get("user_id")), kw.get("type")))
        sent_kw.append(kw)

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _record)

    with blank_session() as db:
        company_id = sorento(db)
        other_company = second_company(db)
        rule_id = numbering_rule(db)

        owner = active_user(db, f"{MARKER} owner")
        approver = active_user(db, f"{MARKER} approver")
        applicant_user = active_user(db, f"{MARKER} applicant")
        staff = active_user(db, f"{MARKER} staff")
        coordinator = active_user(db, f"{MARKER} coordinator")
        linked_staff = active_user(db, f"{MARKER} linked staff")
        root = active_user(db, f"{MARKER} root")
        # The approver is a sales manager and the owner a salesperson of the company: the
        # approve route's owner rule (fix round 1, S9) needs both to hand a project to someone.
        grant(db, owner, "projects.projects.view", company_id)
        grant(db, approver, APPROVE, company_id)
        grant(db, applicant_user, APPROVE, company_id)
        grant(db, linked_staff, "projects.projects.view", company_id)

        a = contact(db, company_id, name=f"{MARKER} contact a")
        b = contact(db, company_id, name=f"{MARKER} contact b")
        c_contact = contact(db, company_id, name=f"{MARKER} contact c")
        noagent = contact(db, company_id, name=f"{MARKER} contact noagent")
        ungranted = contact(db, company_id, granted=False, name=f"{MARKER} contact ungranted")
        agent_a = agent(db, a, person_label="Aminah Example", description="Aminah desk")
        agent_b = agent(db, b, person_label="Bakar Example", description="Bakar desk")
        agent_c = agent(db, c_contact, person_label="Cahaya Example", description="Cahaya desk")
        db.get(User, applicant_user).respond_contact_id = a
        db.get(User, linked_staff).respond_contact_id = c_contact
        debtor_a = debtor(db, company_id, agent_a)
        debtor_b = debtor(db, company_id, agent_b)
        debtor_c = debtor(db, company_id, agent_c)
        db.commit()

        state = {"contact": a, "user": approver}
        perms = {
            approver: {APPROVE, "projects.projects.manage", *STAFF_PERMS},
            applicant_user: {APPROVE},
            coordinator: {APPROVE, *STAFF_PERMS},
            linked_staff: set(STAFF_PERMS),
            staff: set(STAFF_PERMS),
            owner: set(STAFF_PERMS),
            root: ALL,
        }
        originals = _install(db, perms, {}, state)
        try:
            with company_scope(db, frozenset({company_id})):
                with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                    yield SimpleNamespace(
                        c=client, db=db, state=state, sent=sent, sent_kw=sent_kw, perms=perms,
                        semantic=semantic,
                        company_id=company_id, other_company=other_company, rule_id=rule_id,
                        owner=owner, approver=approver, applicant_user=applicant_user, staff=staff,
                        coordinator=coordinator, linked_staff=linked_staff, root=root,
                        a=a, b=b, third=c_contact, noagent=noagent, ungranted=ungranted,
                        agent_a=agent_a, agent_b=agent_b, agent_third=agent_c,
                        debtor_a=debtor_a, debtor_b=debtor_b, debtor_third=debtor_c,
                    )
        finally:
            _restore(originals)


def field_values(detail: dict) -> dict:
    """The D3 values of a portal detail. The PLAN says "generic detail; `fields` = D3 keys":
    the existing generic details are FLAT (stock_inquiry, complaint) while the request body is
    `{fields}`. Either shape satisfies the contract, so read whichever the detail carries."""
    nested = detail.get("fields")
    return nested if isinstance(nested, dict) else detail


def as_contact(w, contact_id: str):
    w.state["contact"] = contact_id
    return w.c


def as_user(w, user_id: str):
    w.state["user"] = user_id
    return w.c


def create_draft(w, contact_id: str | None = None, **over) -> dict:
    who = contact_id or w.a
    own = {w.a: w.debtor_a.id, w.b: w.debtor_b.id, w.third: w.debtor_third.id}.get(who)
    body = fields(own, **over)
    res = as_contact(w, who).post(SUB, json={"fields": body})
    assert res.status_code == 200, res.text
    return res.json()


def submit(w, rid: str, contact_id: str | None = None, body: dict | None = None):
    c = as_contact(w, contact_id or w.a)
    return c.post(f"{SUB}/{rid}/submit", **({"json": {"fields": body}} if body else {}))


def pending(w, contact_id: str | None = None, **over) -> str:
    d = create_draft(w, contact_id, **over)
    res = submit(w, d["id"], contact_id)
    assert res.status_code == 200, res.text
    return d["id"]


def registration(w, rid: str):
    """The portal registration as stored: the `projects.projects` row with this id."""
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, rid)


def approve_body(w, rid: str, **over) -> dict:
    dev = developer(w.db, w.company_id, f"{MARKER} dev {uid()[:6]}")
    body = {
        "title": registration(w, rid).title,
        "developer_party_id": dev.id,
        "owner_user_id": w.owner,
    }
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


def approve(w, rid: str, user: str | None = None, **over):
    return as_user(w, user or w.approver).post(approve_url(rid), json=approve_body(w, rid, **over))


def reject(w, rid: str, reason: str = "not ours", user: str | None = None):
    return as_user(w, user or w.approver).post(reject_url(rid), json={"reason": reason})


def profile_of(w, rid: str):
    """The `projects.sales_profile` row that carries the portal-only legacy fields (R1)."""
    from app.models.projects import ProjectSalesProfile

    w.db.expire_all()
    return w.db.get(ProjectSalesProfile, rid)


def project_count(w) -> int:
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.query(Project).filter(Project.company_id == w.company_id).count()
