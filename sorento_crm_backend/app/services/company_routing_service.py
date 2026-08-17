"""Routing-company resolution for assignment (next-assignee, team-members).

DELIBERATELY separate from ``app/services/company_scope_resolver.py``. Both answer
"which company does this contact belong to", with OPPOSITE empty-case semantics:

    company_scope_resolver   unknown / untagged contact -> frozenset() -> 0 rows
    this module              unknown / untagged contact -> Sorento     -> still routes

The scope resolver protects data (fail closed). This one picks an assignee, and an
assignment that fails closed is a conversation nobody answers. Merging them - or
teaching the scope resolver to resolve by phone - would make every untagged contact
unroutable. See the UAC's D6 / AC-A6.

Resolution order (AC-A1), first hit wins:
    1. an explicit ``company_code`` in the request body (override, D3)
    2. the contact's single ``respond_contact_companies`` row
    3. the default company (Sorento)

A contact in MORE than one company resolves to no company at step 2 and falls to the
default, flagged ``ambiguous`` - never an arbitrary pick (AC-A3).
"""
from __future__ import annotations

import logging
import uuid
from typing import NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany
from app.models.respond_workspace import RespondWorkspace

logger = logging.getLogger(__name__)

# Sorento. The incumbent: every pre-multi-company row belongs to it, and it is where
# an unknown / untagged / ambiguous contact routes.
DEFAULT_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


class RoutingCompany(NamedTuple):
    company_id: str
    company_code: Optional[str]
    source: str  # "body" | "contact" | "default"
    ambiguous: bool = False


def _company_by_id(db: Session, company_id: str) -> Optional[Company]:
    """The company with this id, or None when the id is unknown or malformed.

    The uuid is validated in Python BEFORE the query on purpose: handing Postgres a
    non-uuid string raises, and a raised error aborts the caller's whole transaction
    - so a typo in an n8n field would take out the request rather than falling
    through to the next resolution step.
    """
    wanted = (company_id or "").strip()
    if not wanted:
        return None
    try:
        uuid.UUID(wanted)
    except (AttributeError, TypeError, ValueError):
        logger.info("routing-company: malformed company_id=%r -> ignored", wanted)
        return None
    return db.query(Company).filter(Company.id == wanted).first()


def _company_by_code(db: Session, code: str) -> Optional[Company]:
    wanted = (code or "").strip()
    if not wanted:
        return None
    return (
        db.query(Company)
        .filter(Company.code.ilike(wanted))
        .first()
    )


def _company_code_for_id(db: Session, company_id: str) -> Optional[str]:
    row = db.query(Company.code).filter(Company.id == str(company_id)).first()
    return str(row[0]) if row else None


def find_routing_contact(
    db: Session,
    *,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[RespondContact]:
    """Locate the contact by Respond.io id, internal id, or phone (AC-A2).

    The single "who is this contact" lookup for routing. Company resolution and
    market-segment resolution both use it, so a phone-only call and an id-only call
    for the same contact resolve identically on BOTH axes - the alternative is two
    lookups that disagree.

    ``space_id`` only ever narrows a respond_io_id lookup; it is not required, so a
    caller that omits it still resolves (there is one live workspace today).
    """
    ref = (contact_id or "").strip()
    if ref:
        q = db.query(RespondContact).filter(RespondContact.respond_io_id == ref)
        sid = (space_id or "").strip()
        if sid:
            q = q.join(
                RespondWorkspace, RespondWorkspace.id == RespondContact.workspace_id
            ).filter(RespondWorkspace.space_id == sid)
        contact = q.first()
        if contact is not None:
            return contact
        # n8n sends the Respond.io id, but internal callers pass respond_contacts.id.
        contact = db.query(RespondContact).filter(RespondContact.id == ref).first()
        if contact is not None:
            return contact

    raw_phone = (phone or "").strip()
    if raw_phone:
        # Reuse the integration lookup's candidate list so phone resolution here agrees
        # with the SLA-tracking lookup the same request already does.
        from app.services.sla_service import _respond_contact_phone_lookup_candidates

        candidates = _respond_contact_phone_lookup_candidates(raw_phone)
        if candidates:
            return (
                db.query(RespondContact)
                .filter(RespondContact.phone_number.in_(candidates))
                .first()
            )
    return None


def _contact_company_ids(
    db: Session,
    *,
    contact_id: Optional[str],
    space_id: Optional[str],
    phone: Optional[str],
) -> list[str]:
    contact = find_routing_contact(
        db, contact_id=contact_id, space_id=space_id, phone=phone
    )
    if contact is None:
        return []
    rows = (
        db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == str(contact.id))
        .all()
    )
    return sorted({str(r[0]) for r in rows})


def _default(db: Session, *, ambiguous: bool = False) -> RoutingCompany:
    return RoutingCompany(
        company_id=DEFAULT_COMPANY_ID,
        company_code=_company_code_for_id(db, DEFAULT_COMPANY_ID),
        source="default",
        ambiguous=ambiguous,
    )


def company_for_contact(
    db: Session,
    *,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> str:
    """The company id an entity's contact routes to, coalesced to Sorento (AC-E4).

    Form SLA's company source. Complaints, purchase requests, sponsorship forms and
    stock inquiries all carry a contact; tickets carry none and therefore always get
    the default. A contact in more than one company gets the default too - the same
    "never pick arbitrarily" rule as conversation routing.
    """
    return resolve_routing_company(
        db, contact_id=contact_id, space_id=space_id, phone=phone
    ).company_id


def resolve_routing_company(
    db: Session,
    *,
    company_id: Optional[str] = None,
    company_code: Optional[str] = None,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> RoutingCompany:
    """Resolve the company an assignment should route to. Never raises (AC-J1).

    Precedence: an explicit ``company_id`` > an explicit ``company_code`` > the
    contact > the default. n8n's spine already resolved the product and therefore
    knows the company id, so letting it say so directly saves a lookup that can
    disagree; both explicit forms report ``source="body"``.

    Every failure - unknown id, unknown code, unknown contact, untagged contact, a
    database error - degrades to the default company so routing continues.
    """
    try:
        company = _company_by_id(db, company_id)
        if company is not None:
            return RoutingCompany(
                company_id=str(company.id),
                company_code=str(company.code),
                source="body",
            )
        if (company_id or "").strip():
            logger.info(
                "routing-company: unknown company_id=%r -> falling through", company_id
            )

        wanted_code = (company_code or "").strip()
        if wanted_code:
            company = _company_by_code(db, wanted_code)
            if company is not None:
                return RoutingCompany(
                    company_id=str(company.id),
                    company_code=str(company.code),
                    source="body",
                )
            logger.info(
                "routing-company: unknown company_code=%r -> default", wanted_code
            )

        company_ids = _contact_company_ids(
            db, contact_id=contact_id, space_id=space_id, phone=phone
        )
        if len(company_ids) == 1:
            cid = company_ids[0]
            return RoutingCompany(
                company_id=cid,
                company_code=_company_code_for_id(db, cid),
                source="contact",
            )
        if len(company_ids) > 1:
            logger.info(
                "routing-company: contact belongs to %d companies (contact_id=%r "
                "phone=%r) -> default, flagged ambiguous",
                len(company_ids),
                contact_id,
                phone,
            )
            return _default(db, ambiguous=True)

        return _default(db)
    except Exception:
        logger.warning(
            "routing-company: resolution failed (contact_id=%r phone=%r) -> default",
            contact_id,
            phone,
            exc_info=True,
        )
        return RoutingCompany(
            company_id=DEFAULT_COMPANY_ID,
            company_code=None,
            source="default",
        )
