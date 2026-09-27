"""Identity S3 (#1280): who a WhatsApp contact is, and what a linked user's
sign-in looks like from the outside.

Contract: documentation/plans/identity/s3-contract.md sections 1.1 and 1.7. The
functions here are reads only - they create nothing and list nothing beyond
what they are asked about (AC-40, AC-44).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session


def is_salesperson_contact(db: Session, contact_id: str) -> bool:
    """True when the contact is offered in the "Requested by / Salesperson"
    picker (a market segment with ``is_requestor_selectable``), or is tied to
    a sales agent (Q1, owner ruling 26 Sep 2026 23:45 MYT)."""
    from app.models.access import MarketSegment, respond_contact_market_segments
    from app.models.sales_agent import SalesAgent

    segment_hit = (
        db.query(respond_contact_market_segments.c.contact_id)
        .join(
            MarketSegment,
            MarketSegment.code == respond_contact_market_segments.c.segment_code,
        )
        .filter(
            respond_contact_market_segments.c.contact_id == contact_id,
            MarketSegment.is_requestor_selectable.is_(True),
        )
        .first()
    )
    if segment_hit is not None:
        return True

    agent_hit = db.query(SalesAgent.id).filter(SalesAgent.contact_id == contact_id).first()
    return agent_hit is not None


def suggested_role_slug(db: Session, contact_id: str) -> str:
    """Which role the Add user form should pre-select for this contact."""
    return "salesperson" if is_salesperson_contact(db, contact_id) else "portal_user"


def sign_in_summary(db: Session, user) -> dict:
    """The five S3 1.7 fields for `GET /users/{id}` and `GET /users/me`.

    Read by BOTH manual dict builders in `app.api.v1.user_management.users` -
    a field added here reaches neither response unless each one lists it too
    (LESSONS 93-style gotcha for hand-built dicts).
    """
    from app.models.access import RespondContact
    from app.models.auth import VerificationToken
    from app.models.user_session import UserSession
    from app.services.phone_utils import normalize_msisdn

    linked_contact: Optional[dict] = None
    phone_differs = False
    if user.respond_contact_id:
        contact = (
            db.query(RespondContact)
            .filter(RespondContact.id == user.respond_contact_id)
            .first()
        )
        if contact is not None:
            linked_contact = {
                "id": contact.id,
                "name": contact.name,
                "phone_number": contact.phone_number,
            }
            # A user with no phone at all also counts as differing (S3 1.7).
            phone_differs = normalize_msisdn(user.contact_number) != normalize_msisdn(
                contact.phone_number
            )

    last_session = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .order_by(UserSession.created_at.desc())
        .first()
    )
    last_sign_in_method = last_session.auth_method if last_session else None

    needs_invitation = False
    if user.email and not user.password:
        ever_invited = (
            db.query(VerificationToken.identifier)
            .filter(VerificationToken.identifier == user.id)
            .first()
        )
        needs_invitation = ever_invited is None

    return {
        "phone_verified_at": user.phone_verified_at,
        "linked_contact": linked_contact,
        "phone_differs_from_contact": phone_differs,
        "last_sign_in_method": last_sign_in_method,
        "needs_invitation": needs_invitation,
    }


def linked_user_summary(db: Session, contact_id: str) -> Optional[dict]:
    """The user linked to this contact, for `GET /contacts/{id}` (S3 1.7).

    None when nobody is linked, or (by the route not calling this at all) when
    the caller lacks `user_management.users.view`.
    """
    from app.models.access import RespondContact
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.services.phone_utils import normalize_msisdn

    user = db.query(User).filter(User.respond_contact_id == contact_id).first()
    if user is None:
        return None
    contact_phone = (
        db.query(RespondContact.phone_number).filter(RespondContact.id == contact_id).scalar()
    )
    roles = (
        db.query(UserRole)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == UserRole.id)
        .filter(UserRoleAssignment.user_id == user.id)
        .all()
    )
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "status": user.status,
        "has_password": user.password is not None,
        "roles": [{"id": r.id, "name": r.name} for r in roles],
        # Fix round 2, S3: the WhatsApp code goes to the user's own phone, so
        # "Signs in by WhatsApp code" is true only while it equals the contact's.
        # Same rule as `sign_in_summary`: no phone at all also differs.
        "phone_differs_from_contact": normalize_msisdn(user.contact_number)
        != normalize_msisdn(contact_phone)
        or not normalize_msisdn(user.contact_number),
    }


def linked_user_map(db: Session, contact_ids: list[str]) -> dict[str, dict]:
    """One batched query: ``{contact_id: {"id", "name"}}`` for a whole page of
    contacts (S3 1.7 - "one batched query per page, never per row")."""
    from app.models.user import User

    if not contact_ids:
        return {}
    rows = (
        db.query(User.respond_contact_id, User.id, User.name)
        .filter(User.respond_contact_id.in_(contact_ids))
        .all()
    )
    return {row[0]: {"id": row[1], "name": row[2]} for row in rows}
