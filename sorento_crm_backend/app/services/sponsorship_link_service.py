"""Linking a sponsorship form to a registered project (UAC Group F, AC-F3 to AC-F7).

ONE form, not two (AC-F3). `purchase_requests` gains a nullable `project_id`; every
sponsorship that exists today keeps working with none, and `project_title` stays as the
display fallback (AC-F6).

The rollout is per CONTACT (AC-F4), and that is the whole design rather than a hedge:
Sorento wants to require a registered project from the salespeople they have briefed
without breaking the form for everybody else on the same morning. So the flag decides
whether a project is REQUIRED. It never decides whether a link may be WRONG -- a
sponsorship attached to somebody else's project corrupts that project's spend rollup
either way, so ownership is checked for flagged and unflagged contacts alike.

Everything here is enforced server-side. The portal is a public surface reached with a
token, and the browser is not a trust boundary.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import Integer, extract, func
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany
from app.models.procurement import PurchaseRequestHeader
from app.models.projects import Project, ProjectPurchaseOrder
from app.services.error_handler import AppException

SPONSORSHIP_TYPE = "sponsorship_form"
_CENTS = Decimal("0.01")


def contact_company_ids(db: Session, *, contact: RespondContact) -> List[str]:
    # str(), not the raw scalar: psycopg2 returns uuid.UUID for a UUID column while the
    # ORM stores the id as a string, and a bare `in` comparison silently misses.
    return [
        str(row[0])
        for row in db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == contact.id)
        .all()
    ]


def projects_for_contact(
    db: Session, *, contact: RespondContact, query: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """What the picker offers (AC-F4a).

    Every row names its company, because a contact mapped to two of them cannot otherwise
    tell two similarly-named phases apart. Read WITHOUT the company scope filter on
    purpose: the scope for a portal request is the CONTACT's company set, which is a
    different question from "which company is the logged-in user acting as".
    """
    company_ids = contact_company_ids(db, contact=contact)
    if not company_ids:
        return []

    from app.models.base import company_scope

    from app.services.project_service import approved_projects

    with company_scope(db, frozenset(company_ids)):
        # A portal registration still waiting for approval is not a project to attach
        # anything to yet (PROJECT-REG-PORTAL R4).
        rows = approved_projects(
            db.query(Project, Company.name)
            .join(Company, Company.id == Project.company_id)
            .filter(Project.company_id.in_(company_ids))
        )
        if query and query.strip():
            like = f"%{query.strip().lower()}%"
            rows = rows.filter(
                func.lower(Project.title).like(like)
                | func.lower(Project.name).like(like)
                | func.lower(Project.project_code).like(like)
            )
        rows = rows.order_by(Project.created_at.desc()).limit(limit).all()

    return [
        {
            "id": project.id,
            "project_code": project.project_code,
            "title": project.title,
            "name": project.name,
            "company_id": project.company_id,
            "company_name": company_name,
        }
        for project, company_name in rows
    ]


def _not_yours() -> AppException:
    return AppException(
        status_code=422,
        message=(
            "That project is not one of yours. Pick a project from the list, "
            "which shows the ones registered under your company."
        ),
        code="sponsorship_project_not_permitted",
    )


def _owned_company_ids(db: Session, *, contact: Optional[RespondContact], project_id: str) -> List[str]:
    """The ownership half (any approval state): the project belongs to one of the contact's
    companies. Returns those companies; refuses otherwise. A contact linked to no company (or
    none at all) is told THAT, so nobody hunts for a project problem an admin has to fix."""
    company_ids = contact_company_ids(db, contact=contact) if contact is not None else []
    if not company_ids:
        raise AppException(
            status_code=422,
            message=(
                "Your contact is not linked to any company yet, so no project can be "
                "attached. Ask the Sorento team to link your company first."
            ),
            code="sponsorship_contact_no_company",
        )
    from uuid import UUID

    from app.models.base import company_scope

    try:
        UUID(str(project_id))
    except (TypeError, ValueError):
        raise _not_yours()
    with company_scope(db, frozenset(company_ids)):
        owner = db.query(Project.company_id).filter(Project.id == str(project_id)).scalar()
    if owner is None or str(owner) not in company_ids:
        raise _not_yours()
    return company_ids


def assert_contact_may_link(
    db: Session,
    *,
    contact: Optional[RespondContact],
    project_id: Optional[str],
    current: Optional[str] = None,
    code: str,
) -> None:
    """THE check for a contact linking a record to a project (PROJECT-RELATED-RECORDS AC-C3):
    portal create, draft save, submit and revise, the portal new product application and the
    external stock inquiry all call this one. Ownership first, so another company's project reads
    as "not one of yours"; then the record's own "not approved yet" (`assert_linkable_project`,
    `code`). Re-saving the link a record already has is not a change."""
    if not project_id or str(project_id) == str(current or ""):
        return
    company_ids = _owned_company_ids(db, contact=contact, project_id=str(project_id))
    from app.models.base import company_scope

    from app.services.project_service import assert_linkable_project

    with company_scope(db, frozenset(company_ids)):
        assert_linkable_project(db, str(project_id), current, code=code)


def assert_project_requirement(
    db: Session, *, contact: Optional[RespondContact], project_id: Optional[str]
) -> None:
    """The gate (AC-F4, AC-F5).

    Two separate refusals, worded differently on purpose:

  - nothing picked while flagged -> "register it on the web first", because that is the
      action, and it is not guessable from "a project is required";
  - picked something that is not theirs -> named as an ownership problem, and when the
      contact is linked to no company at all, named as THAT instead, so the user does not
      go hunting for a project problem when an admin has to link their company.
    """
    if contact is None:
        return

    if project_id:
        company_ids = _owned_company_ids(db, contact=contact, project_id=str(project_id))
        from app.models.base import company_scope

        from app.services.project_service import approved_projects

        with company_scope(db, frozenset(company_ids)):
            project = approved_projects(db.query(Project).filter(Project.id == project_id)).first()
        if project is None:
            raise _not_yours()
        return

    if getattr(contact, "requires_registered_project", False):
        raise AppException(
            status_code=422,
            message=(
                "This sponsorship has to name a registered project. If it is not in the "
                "list, register the project on the web first and then submit this form."
            ),
            code="sponsorship_project_required",
        )


# ---------------------------------------------------------------------- reading


def list_sponsorships(db: Session, *, project_id: str) -> List[Dict[str, Any]]:
    """Sponsorship forms linked to one project.

    Filtered to `sponsorship_form`: a purchase request against the same project is not
    sponsorship spend, and mixing the two would double-count it in the rollup that reads
    the same rows.
    """
    rows = (
        db.query(PurchaseRequestHeader)
        .filter(
            PurchaseRequestHeader.project_id == project_id,
            PurchaseRequestHeader.request_type == SPONSORSHIP_TYPE,
        )
        .order_by(PurchaseRequestHeader.request_date.desc().nullslast())
        .all()
    )
    return [
        {
            "id": row.id,
            "request_number": row.request_number,
            "request_date": row.request_date,
            "status": row.status,
            "approval_status": getattr(row, "approval_status", None),
            "customer_name": row.customer_name,
            "project_title": row.project_title,
            "sponsor_subject": row.sponsor_subject,
            "sponsor_subject_other": row.sponsor_subject_other,
            "total_project_value": row.total_project_value,
            "purpose": row.purpose,
        }
        for row in rows
    ]


def sponsorship_rollup(db: Session, *, project_id: str, clause: Any = None) -> Dict[str, Any]:
    """AC-F7, per project AND per year.

    Per year as well, because "how much have we spent sponsoring this development" and
    "how much did we spend on sponsorship in 2026" are two different management questions
    and only the second one justifies next year's budget.

    `clause` narrows the forms counted (a `view_own` reader: `own_scope.request_clause`, the
    Related tab's own rule, PROJECT-RELATED-RECORDS AC-B2).
    """
    extra = [clause] if clause is not None else []
    total, count = (
        db.query(
            func.coalesce(func.sum(PurchaseRequestHeader.total_project_value), 0),
            func.count(PurchaseRequestHeader.id),
        )
        .filter(
            PurchaseRequestHeader.project_id == project_id,
            PurchaseRequestHeader.request_type == SPONSORSHIP_TYPE,
            *extra,
        )
        .first()
    ) or (0, 0)

    year_rows = (
        db.query(
            extract("year", PurchaseRequestHeader.request_date).label("year"),
            func.coalesce(func.sum(PurchaseRequestHeader.total_project_value), 0),
            func.count(PurchaseRequestHeader.id),
        )
        .filter(
            PurchaseRequestHeader.project_id == project_id,
            PurchaseRequestHeader.request_type == SPONSORSHIP_TYPE,
            PurchaseRequestHeader.request_date.isnot(None),
            *extra,
        )
        .group_by("year")
        .order_by("year")
        .all()
    )

    return {
        "project_id": project_id,
        "total": Decimal(total or 0).quantize(_CENTS),
        "form_count": int(count or 0),
        "by_year": [
            {
                "year": int(row[0]),
                "total": Decimal(row[1] or 0).quantize(_CENTS),
                "form_count": int(row[2] or 0),
            }
            for row in year_rows
        ],
    }


def sponsorship_conversion(db: Session, *, company_id: str) -> Dict[str, Any]:
    """AC-F7's second half: did the sponsorship turn into a PO?

    Counted per PROJECT rather than per form, because two sponsorships on one development
    that later issues one PO is one conversion, not two -- and counting it twice would
    make the rate look better the more we spent.

    ``rate`` is None rather than 0 when nothing was sponsored: 0% reads as "we sponsor and
    never win", which is a different and much worse statement.
    """
    # Scoped through PROJECTS, not through the form: `purchase_requests` has no
    # company_id of its own, and the company that matters is the one whose project was
    # sponsored anyway.
    sponsored = {
        str(row[0])
        for row in db.query(PurchaseRequestHeader.project_id)
        .join(Project, Project.id == PurchaseRequestHeader.project_id)
        .filter(
            PurchaseRequestHeader.request_type == SPONSORSHIP_TYPE,
            PurchaseRequestHeader.project_id.isnot(None),
            Project.company_id == company_id,
        )
        .distinct()
        .all()
    }
    if not sponsored:
        return {
            "sponsored_projects": 0,
            "converted_projects": 0,
            "rate": None,
            "sponsored_spend": Decimal("0.00"),
        }

    converted = {
        str(row[0])
        for row in db.query(ProjectPurchaseOrder.project_id)
        .filter(ProjectPurchaseOrder.project_id.in_(list(sponsored)))
        .distinct()
        .all()
    }
    spend = (
        db.query(func.coalesce(func.sum(PurchaseRequestHeader.total_project_value), 0))
        .filter(
            PurchaseRequestHeader.request_type == SPONSORSHIP_TYPE,
            PurchaseRequestHeader.project_id.in_(list(sponsored)),
        )
        .scalar()
    ) or 0

    rate = (
        Decimal(len(converted)) / Decimal(len(sponsored)) * Decimal("100")
    ).quantize(_CENTS)
    return {
        "sponsored_projects": len(sponsored),
        "converted_projects": len(converted),
        "rate": rate,
        "sponsored_spend": Decimal(spend).quantize(_CENTS),
    }
