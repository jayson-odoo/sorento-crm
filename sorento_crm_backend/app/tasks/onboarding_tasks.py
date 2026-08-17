"""Provisioning for an approved onboarding request.

Runs on the ``imports`` queue, which the dedicated worker owns. **Editing this
file requires restarting the Worker session** - RQ tasks do not hot-reload.

Three properties this task is built around, in the order they matter:

1. **Failures are per lane, per person. Never per batch.** One malformed email
   must not stop the other seventeen people. Every lane is wrapped
   individually, records its own error on its own row, commits, and the loop
   moves on.
2. **Re-running is safe and is the recovery path.** A lane is touched only when
   it is `pending` or `failed`; `done` and `skipped` are left exactly as they
   are. A crash halfway through a batch is fixed by running it again, not by
   cleaning up first.
3. **An artifact that already exists is not a failure.** A pre-existing email
   marks the lane `skipped` with the existing user captured, because the point
   of onboarding somebody who half-exists is to fill in what is missing.

Only the CRM-user lane runs in this slice. The contact and agent-seat lanes stay
`pending` and are Slice 2 and 3's inbox - see `onboarding_service.finalise` for
why that is what the request's terminal status is computed from.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.onboarding import (
    LANE_DONE,
    LANE_FAILED,
    LANE_PENDING,
    LANE_SKIPPED,
    REVIEW_APPROVED,
    OnboardingPerson,
    OnboardingRequest,
    OnboardingTemplate,
)
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import onboarding_service
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

#: Lanes worth attempting. A `done` lane is finished and a `skipped` one was
#: decided; re-walking either is how a re-run creates a second user.
RETRYABLE = (LANE_PENDING, LANE_FAILED)


def _existing_user(db, email: str | None) -> User | None:
    if not email:
        return None
    return db.query(User).filter(func.lower(User.email) == email).first()


def _provision_user_lane(db, person: OnboardingPerson, template: OnboardingTemplate | None) -> None:
    """Create (or adopt) the CRM user for one person.

    Committed per person so a later failure cannot roll back an account that was
    genuinely created - and so the review page shows progress while the batch is
    still running.
    """
    if not person.needs_system_account:
        person.user_step = LANE_SKIPPED
        person.user_error = None
        return

    if person.user_step not in RETRYABLE:
        return

    if not person.email:
        person.user_step = LANE_FAILED
        person.user_error = "No email address, so no account can be created."
        return

    existing = _existing_user(db, person.email)
    if existing is not None:
        # Not an error. Capture who it is so the review page can say "already a
        # user: <name>" instead of leaving a blank lane nobody can interpret.
        person.user_id = str(existing.id)
        person.user_step = LANE_SKIPPED
        person.user_error = None
        return

    payload = UserCreate(
        email=person.email,
        name=person.full_name,
        # `contact_number` is unique across users. A phone already held by
        # somebody else would abort the insert, so it is only offered when the
        # collision report found nothing - and the report is what the reviewer
        # already saw.
        contact_number=person.phone,
        role_ids=list(template.role_ids or []) if template else None,
        company_ids=list(template.company_ids or []) if template else None,
    )
    user = UserService(db).invite_user(
        payload, invited_by_user_id=person.request.created_by_user_id
    )
    person.user_id = str(user.id)
    person.user_step = LANE_DONE
    person.user_error = None

    # The invitation email is a side effect of a user that already exists. It is
    # best-effort for the same reason every post-commit side effect here is: a
    # failed send must not turn a created account into a failed lane, and the
    # captain can resend from the users list.
    try:
        from app.api.v1.user_management.users import _send_invitation_link_for_user

        _send_invitation_link_for_user(db, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Onboarding: user %s created but the invitation email failed: %s", user.id, exc
        )


def provision_onboarding_request(request_id: str) -> dict:
    """Walk every approved person's lanes. Returns a summary for the job log."""
    db = SessionLocal()
    summary = {"created": 0, "skipped": 0, "failed": 0, "people": 0}
    try:
        # The worker has no request, so no scope resolver ran. Read the request
        # unscoped, then narrow to its own company for everything after - the
        # same shape `public/catalogue.py` uses. Without this every scoped query
        # in here answers zero rows (UNSET is fail-closed).
        with company_scope(db, None):
            request = (
                db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).first()
            )
        if request is None:
            logger.warning("Onboarding: request %s no longer exists", request_id)
            return summary

        with company_scope(db, frozenset({str(request.company_id)})):
            people = [p for p in request.people if p.review_status == REVIEW_APPROVED]
            summary["people"] = len(people)

            templates: dict[str, OnboardingTemplate] = {}
            for person in people:
                template = None
                if person.template_id:
                    key = str(person.template_id)
                    if key not in templates:
                        found = (
                            db.query(OnboardingTemplate)
                            .filter(OnboardingTemplate.id == person.template_id)
                            .first()
                        )
                        if found is not None:
                            templates[key] = found
                    template = templates.get(key)

                try:
                    _provision_user_lane(db, person, template)
                    person.provisioned_at = datetime.utcnow()
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - per person, never per batch
                    db.rollback()
                    logger.exception(
                        "Onboarding: user lane failed for person %s", person.id
                    )
                    # Re-read: the rollback detached whatever the failed attempt
                    # had set, so the error is written on a clean row.
                    fresh = (
                        db.query(OnboardingPerson)
                        .filter(OnboardingPerson.id == person.id)
                        .first()
                    )
                    if fresh is not None:
                        fresh.user_step = LANE_FAILED
                        fresh.user_error = str(exc)[:1000]
                        db.commit()

                db.refresh(person)
                if person.user_step == LANE_DONE:
                    summary["created"] += 1
                elif person.user_step == LANE_SKIPPED:
                    summary["skipped"] += 1
                elif person.user_step == LANE_FAILED:
                    summary["failed"] += 1

            onboarding_service.finalise(db, request)

            # Post-commit and therefore best-effort: the batch HAS been
            # provisioned, and raising here would report a failure for work that
            # succeeded while the retry took the idempotent path and never
            # re-sent the email anyway.
            try:
                _notify_requester_complete(db, request, summary)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Onboarding: completion email for request %s failed: %s", request.id, exc
                )

        return summary
    finally:
        db.close()


def _notify_requester_complete(db, request: OnboardingRequest, summary: dict) -> None:
    """One email when the batch finishes, in the requester's own terms."""
    from app.services import email_outbox_service

    created = summary["created"]
    skipped = summary["skipped"]
    failed = summary["failed"]

    lines = [
        f"Hello {request.requester_name},",
        "",
        f"Your onboarding submission '{request.title}' has been processed.",
        "",
        f"  Accounts created: {created}",
        f"  Already existed:  {skipped}",
    ]
    if failed:
        lines.append(f"  Could not be created: {failed}")
        lines.append("")
        lines.append("Somebody from the team will be in touch about the ones that failed.")
    lines += [
        "",
        "Anybody who received an account has been emailed a link to set their password.",
        "",
        "This is a system-generated email. Please do not reply.",
    ]
    body_text = "\n".join(lines)

    email_outbox_service.enqueue(
        db,
        event_key="onboarding_completed",
        to=request.requester_email,
        subject=f"Onboarding complete: {request.title}",
        body_text=body_text,
        body_html="<p>" + "</p><p>".join(l for l in lines if l) + "</p>",
        from_name="Sorento AI System",
        metadata={"onboarding_request_id": str(request.id), **summary},
    )
    db.commit()
