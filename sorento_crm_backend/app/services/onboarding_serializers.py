"""One serializer for the onboarding person row, used by both routers.

The public intake page and the captain's review page render the SAME grid, so
they must be handed the same row shape. Two serializers is how the two screens
start disagreeing about what a row said - the failure the shared FE component
exists to prevent, and it would be reintroduced here if each router built its
own dict.

The difference between the two callers is what they are ALLOWED to see, and that
is expressed by what gets passed in: the public caller passes no collisions.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.onboarding import OnboardingPerson, OnboardingTemplate
from app.models.user import User
from app.schemas.onboarding import (
    CollisionOut,
    PersonOut,
    PublicTemplateOption,
    TemplateOut,
)
from app.services.onboarding_service import Collision


def row_problems(person: OnboardingPerson) -> list[str]:
    """The row's complaints, recomputed from its current values.

    Recomputed rather than stored so that a reviewer who fixes a phone number
    sees the chip disappear on the next read. A stored problem list would keep
    complaining about a value nobody can find fault with any more, which is the
    fastest way to teach people to ignore the chips.
    """
    problems: list[str] = []
    if not person.email:
        problems.append("no email")
    if person.phone_raw and not person.phone:
        problems.append("phone not recognised")
    if not person.phone_raw:
        problems.append("no phone")
    return problems


def user_label(db: Session, person: OnboardingPerson) -> Optional[str]:
    """The name of the user this row produced or matched. Never an id."""
    if not person.user_id:
        return None
    user = db.query(User).filter(User.id == person.user_id).first()
    if user is None:
        return None
    return user.name or user.email


def person_out(
    db: Session,
    person: OnboardingPerson,
    *,
    collisions: Optional[list[Collision]] = None,
) -> PersonOut:
    return PersonOut(
        id=str(person.id),
        row_number=person.row_number,
        full_name=person.full_name,
        nick_name=person.nick_name,
        phone_raw=person.phone_raw,
        email_raw=person.email_raw,
        section_label=person.section_label,
        template_id=str(person.template_id) if person.template_id else None,
        requester_note=person.requester_note,
        reviewer_note=person.reviewer_note,
        needs_system_account=person.needs_system_account,
        needs_respond_contact=person.needs_respond_contact,
        needs_agent_seat=person.needs_agent_seat,
        review_status=person.review_status,
        rejection_reason=person.rejection_reason,
        problems=row_problems(person),
        collisions=[CollisionOut(kind=c.kind, label=c.label) for c in (collisions or [])],
        user_step=person.user_step,
        user_error=person.user_error,
        user_label=user_label(db, person),
        contact_step=person.contact_step,
        contact_error=person.contact_error,
        agent_step=person.agent_step,
        agent_error=person.agent_error,
    )


def public_template_option(template: OnboardingTemplate) -> PublicTemplateOption:
    """Labels only. See `app/schemas/onboarding.py` for why that is the point."""
    return PublicTemplateOption(
        id=str(template.id),
        name=template.name,
        description=template.description,
        default_needs_system_account=template.default_needs_system_account,
        default_needs_respond_contact=template.default_needs_respond_contact,
        default_needs_agent_seat=template.default_needs_agent_seat,
    )


def template_out(template: OnboardingTemplate) -> TemplateOut:
    return TemplateOut(
        id=str(template.id),
        name=template.name,
        description=template.description,
        is_active=template.is_active,
        role_ids=list(template.role_ids or []),
        company_ids=list(template.company_ids or []),
        access_agent_ids=list(template.access_agent_ids or []),
        captured_from_user_id=(
            str(template.captured_from_user_id) if template.captured_from_user_id else None
        ),
        default_needs_system_account=template.default_needs_system_account,
        default_needs_respond_contact=template.default_needs_respond_contact,
        default_needs_agent_seat=template.default_needs_agent_seat,
    )
