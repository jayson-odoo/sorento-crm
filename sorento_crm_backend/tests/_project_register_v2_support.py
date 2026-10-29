"""Shared world for the PROJECT-REGISTER-V2 suites (Phase 2, red-first).

UAC: documentation/plans/projects/project-register-v2-acceptance-criteria.md.

Unlike `_project_registration_support.world`, this fixture does NOT replace
`NotificationService.create_with_channel_preferences`: the owner wants the notification and
`notification_deliveries` ROWS asserted (UAC J), so the real service runs and only the queue
hand-off (`enqueue_job`) is swallowed. Nothing is ever sent: the email half is checked by
running the delivery job's own helper with the outbox `enqueue` recorded.

Contract assumptions the tests bind (the UAC leaves the wire shape of the salesperson path open;
change them HERE and every J test follows):

- A submit-only user registers with `POST /projects/` and the body flag `submit`: false (default)
  saves a draft, true submits for approval.
- An existing draft or rejected registration is submitted with `POST /projects/{id}/submit`.

Every name is invented (Sales A, Sales B, Manager M, CONTOH ...). Everything is seeded here.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be the first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import (
    ALL,
    APPROVE,
    MANAGE,
    MARKER,
    STAFF,
    _install,
    _restore,
    active_user,
    agent,
    as_contact,
    as_user,
    contact,
    debtor,
    developer,
    grant,
    project,
    project_type,
    stub_semantic,
    uid,
)
from ._sample_request_seed import make_customer, second_company, sorento

__all__ = [
    "ALL", "APPROVE", "MANAGE", "STAFF", "LIST", "AI_EXTRACT", "SUBMIT", "VIEW", "VIEW_OWN", "EDIT",
    "as_contact", "as_user", "developer", "project", "project_type", "uid", "v2",
    "title", "register_body", "seed_lead", "save_draft", "submit_new", "submit_existing", "approve_as_manager",
    "reject_as_manager", "notes", "channels_of", "approved_project", "email_jobs",
]

LIST = f"{STAFF}/"
AI_EXTRACT = f"{STAFF}/ai-extract"
SUBMIT = "projects.registrations.submit"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"
EDIT = "projects.projects.edit"
PARTIES_VIEW = "projects.parties.view"
PARTIES_EDIT = "projects.parties.edit"


def title(stem: str = "Tower") -> str:
    """Unique per call: the clash matcher blocks near-duplicate titles under one developer."""
    return f"CONTOH {stem} {uuid.uuid4().hex}"


@pytest.fixture
def v2(monkeypatch):
    """One Postgres schema, one company scope, the real notification service.

    users: owner (Sales A, view+edit+parties), sales_b, sales_c (view+edit), manager (Manager M:
    manage+approve+edit), manager2 (Manager N: manage only, by role), ex_manager (inactive, manage
    by role), approver (approve + view, NOT manage), viewer_own (view_own only), sub_a (submit +
    view_own, linked to portal contact `a` and its sales agent, ALSO an approver by role so the
    "except the submitter" rule is visible), sub_b (submit + view_own, NO linked contact),
    nobody (no permission), root (every permission).
    """
    from fastapi.testclient import TestClient

    from app.models.base import company_scope
    from app.models.user import User, UserStatus
    from app.services import project_seed_service, queue_service

    stub_semantic(monkeypatch)
    hand_offs: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: hand_offs.append((a, k)))

    with blank_session() as db:
        company_id = sorento(db)
        other_company = second_company(db)
        project_seed_service.run(db, company_id=company_id)

        names = {
            "owner": "Sales A", "sales_b": "Sales B", "sales_c": "Sales C", "manager": "Manager M",
            "manager2": "Manager N", "ex_manager": "Manager X", "approver": "Approver P",
            "viewer_own": "Viewer Q", "sub_a": "Submitter A", "sub_b": "Submitter B",
            "nobody": "Nobody R", "root": "Root S",
        }
        u = {key: active_user(db, f"{MARKER} {name}") for key, name in names.items()}

        # Real role grants: the notification recipient queries read these, not the patched set.
        grant(db, u["owner"], VIEW, company_id)
        grant(db, u["sales_b"], VIEW, company_id)
        grant(db, u["sales_c"], VIEW, company_id)
        grant(db, u["manager"], MANAGE, company_id)
        grant(db, u["manager"], APPROVE, company_id)
        grant(db, u["manager2"], MANAGE, company_id)
        grant(db, u["ex_manager"], MANAGE, company_id)
        db.get(User, u["ex_manager"]).status = UserStatus.INACTIVE.value
        grant(db, u["approver"], APPROVE, company_id)
        grant(db, u["sub_a"], SUBMIT, company_id)
        grant(db, u["sub_a"], APPROVE, company_id)
        grant(db, u["sub_b"], SUBMIT, company_id)
        grant(db, u["viewer_own"], VIEW_OWN, company_id)
        grant(db, u["nobody"], "zzt.unrelated", company_id)

        a = contact(db, company_id, name=f"{MARKER} contact a")
        agent_a = agent(db, a, person_label="Aminah Example", description="Aminah desk")
        db.get(User, u["sub_a"]).respond_contact_id = a
        debtor_a = debtor(db, company_id, agent_a)
        b = contact(db, company_id, name=f"{MARKER} contact b")
        third = contact(db, company_id, name=f"{MARKER} contact c")
        debtor_b = debtor(db, company_id, agent(db, b, person_label="Bakar Example", description="Bakar desk"))
        debtor_third = debtor(db, company_id, agent(db, third, person_label="Cahaya Example", description="Cahaya desk"))
        customer = make_customer(db, company_id)
        foreign_customer = make_customer(db, other_company)
        db.commit()

        base_view = {VIEW, EDIT}
        perms = {
            u["owner"]: {*base_view, PARTIES_VIEW, PARTIES_EDIT},
            u["sales_b"]: set(base_view),
            u["sales_c"]: set(base_view),
            u["manager"]: {*base_view, MANAGE, APPROVE},
            u["manager2"]: {*base_view, MANAGE},
            u["ex_manager"]: {*base_view, MANAGE},
            u["approver"]: {VIEW, APPROVE},
            u["viewer_own"]: {VIEW_OWN},
            u["sub_a"]: {SUBMIT, VIEW_OWN},
            u["sub_b"]: {SUBMIT, VIEW_OWN},
            u["nobody"]: set(),
            u["root"]: ALL,
        }
        state = {"contact": a, "user": u["root"]}
        originals = _install(db, perms, {}, state)
        try:
            with company_scope(db, frozenset({company_id})):
                with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                    yield SimpleNamespace(
                        c=client, db=db, state=state, perms=perms, hand_offs=hand_offs,
                        company_id=company_id, other_company=other_company,
                        customer=customer, foreign_customer=foreign_customer,
                        a=a, b=b, third=third, agent_a=agent_a, debtor_a=debtor_a,
                        debtor_b=debtor_b, debtor_third=debtor_third,
                        applicant_user=u["sub_a"], names=names, **u,
                    )
        finally:
            _restore(originals)


# ------------------------------------------------------------------ bodies and calls


def seed_lead(w, user: str, customer_id=None):
    """A lead of `user`'s own, straight in the database (LEAD-GOVERNS-REGISTER E1: a register
    call needs a lead). It has NO customer unless one is given, so the register body's own
    `customer_id` is the one the project stores and the lead then takes (E3)."""
    from app.models.projects import ProjectLead
    from app.services.project_clash_service import normalise_project_title

    text = f"CONTOH Lead {uuid.uuid4().hex}"
    row = ProjectLead(
        id=uid(),
        company_id=w.company_id,
        lead_code=f"ZZT-L{uuid.uuid4().hex[:12]}",
        title=text,
        normalised_title=normalise_project_title(text),
        customer_id=customer_id,
        owner_user_id=user,
        created_by=user,
        outcome="open",
    )
    w.db.add(row)
    w.db.flush()
    return row


def register_body(w, *, user: str | None = None, no_lead: bool = False, **over) -> dict:
    """A register body. Unless `no_lead` or an explicit `lead_id`, it carries a fresh lead of
    `user` (default: the staff owner), so the project can be registered under the lead rule."""
    body = {"title": title(), "customer_id": w.customer.id}
    body.update(over)
    if not no_lead and "lead_id" not in body:
        body["lead_id"] = seed_lead(w, user or w.owner).id
    return {k: v for k, v in body.items() if v is not None}


def save_draft(w, user: str, **over):
    body = register_body(w, user=user, **over)
    body["submit"] = False
    return as_user(w, user).post(LIST, json=body)


def submit_new(w, user: str, **over):
    body = register_body(w, user=user, **over)
    body["submit"] = True
    return as_user(w, user).post(LIST, json=body)


def submit_existing(w, user: str, project_id: str, body: dict | None = None):
    return as_user(w, user).post(f"{STAFF}/{project_id}/submit", json=body or {})


def approve_as_manager(w, project_id: str, owner: str | None = None, **over):
    dev = developer(w.db, w.company_id, f"CONTOH Dev {uid()[:6]}")
    body = {"developer_party_id": dev.id}
    if owner:
        body["owner_user_id"] = owner
    body.update(over)
    return as_user(w, w.manager).post(f"{STAFF}/{project_id}/approve", json=body)


def reject_as_manager(w, project_id: str, reason: str = "Already registered"):
    return as_user(w, w.manager).post(f"{STAFF}/{project_id}/reject", json={"reason": reason})


def approved_project(w, *, owner: str | None = None, ttl: str | None = None, dev=None):
    """A staff project (approved, coded) straight in the database."""
    return project(
        w.db, w.company_id, ttl or title("Estate"), owner=owner or w.owner, developer_party=dev
    )


# ------------------------------------------------------------------ notification rows


def notes(w, project_id: str, kind: str | None = None) -> list:
    """Notification rows about a project, optionally of one type, oldest first."""
    from app.models.notification import Notification

    w.db.expire_all()
    q = w.db.query(Notification).filter(
        Notification.source_entity_type == "project",
        Notification.source_entity_id == str(project_id),
    )
    if kind:
        q = q.filter(Notification.type == kind)
    return q.order_by(Notification.created_at, Notification.id).all()


def channels_of(w, notification) -> set:
    from app.models.notification import NotificationDelivery

    w.db.expire_all()
    return {
        d.channel
        for d in w.db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notification.id
        )
    }


def email_jobs(w, monkeypatch, notification) -> list:
    """Run the delivery job's email step for one notification with the outbox `enqueue`
    recorded instead of called: an outbox hand-off is asserted, nothing is sent."""
    from app.models.notification import NotificationDelivery
    from app.models.user import User
    from app.services import email_outbox_service
    from app.tasks import notification_tasks

    recorded: list = []
    monkeypatch.setattr(
        email_outbox_service, "enqueue", lambda db, **kw: recorded.append(kw) or str(uuid.uuid4())
    )
    user = w.db.get(User, notification.user_id)
    deliveries = (
        w.db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == "email",
            NotificationDelivery.status == "pending",
        )
        .all()
    )
    for delivery in deliveries:
        notification_tasks._enqueue_email_for_delivery(w.db, notification, user, delivery, "zzt-event")
    return recorded
