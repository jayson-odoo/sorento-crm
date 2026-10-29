"""Shared seeds for the LEAD-GOVERNS-REGISTER suites (UAC B, E, F, H).

Builds on the PROJECT-REGISTER-V2 `v2` world (users, perms, one company, one customer). Leads are
inserted straight into the database so a test can pin `owner_user_id`, `created_by` and
`customer_id` independently of what the API would allow. Every name is invented.
"""
from __future__ import annotations

import uuid

from ._project_register_v2_support import LIST, STAFF, title
from ._sample_request_seed import make_customer

LEADS = "/api/v1/project-sales/leads"


def lead_row(w, *, customer_id=None, owner=None, created_by=None, name: str | None = None):
    """A lead row straight in the database; returns the ORM row."""
    from app.models.projects import ProjectLead
    from app.services.project_clash_service import normalise_project_title

    text = name or f"CONTOH Lead {uuid.uuid4().hex}"
    row = ProjectLead(
        id=str(uuid.uuid4()),
        company_id=w.company_id,
        lead_code=f"ZZT-L{uuid.uuid4().hex[:12]}",
        title=text,
        normalised_title=normalise_project_title(text),
        customer_id=customer_id,
        owner_user_id=owner,
        created_by=created_by or owner,
        outcome="open",
    )
    w.db.add(row)
    # Committed: the app shares this session and rolls it back on a refusal, which would
    # otherwise wipe the seed before the test reads it again.
    w.db.commit()
    return row


def staff_lead(db, company_id, user, customer_id):
    """A lead of `user` carrying `customer_id`, flushed (the caller commits). For older suites
    whose world is not the v2 one; returns the lead id."""
    from app.models.projects import ProjectLead
    from app.services.project_clash_service import normalise_project_title

    text = f"CONTOH Lead {uuid.uuid4().hex}"
    row = ProjectLead(
        id=str(uuid.uuid4()),
        company_id=company_id,
        lead_code=f"ZZT-L{uuid.uuid4().hex[:12]}",
        title=text,
        normalised_title=normalise_project_title(text),
        customer_id=customer_id,
        owner_user_id=user,
        created_by=user,
        outcome="open",
    )
    db.add(row)
    db.flush()
    return row.id


def new_customer(w):
    return make_customer(w.db, w.company_id)


def reload_lead(w, lead_id: str):
    from app.models.projects import ProjectLead

    w.db.expire_all()
    return w.db.get(ProjectLead, lead_id)


def profile_of(w, project_id: str):
    from app.models.projects import ProjectSalesProfile

    w.db.expire_all()
    return w.db.get(ProjectSalesProfile, project_id)


def project_of(w, project_id: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, project_id)


def projects_titled(w, text: str) -> int:
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.query(Project).filter(Project.title == text).count()


def customer_count(w) -> int:
    from app.models.order import Customer

    w.db.expire_all()
    return w.db.query(Customer).count()


def ids_of(res) -> set:
    return {row["id"] for row in res.json()["data"]}


__all__ = [
    "LEADS", "LIST", "STAFF", "title", "lead_row", "staff_lead", "new_customer", "reload_lead", "profile_of",
    "project_of", "projects_titled", "customer_count", "ids_of",
]
