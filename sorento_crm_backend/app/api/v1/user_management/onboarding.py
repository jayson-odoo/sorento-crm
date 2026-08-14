"""Onboarding requests, review and approval (the captain's side).

Permissions follow the Edition-approval convention: `.view` reads, `.add`
creates and sends the link, `.edit` writes and administers templates, `.delete`
deletes, and `.approve` is its own slug because approving is what creates real
users with real access.

`DELETE` is a hard delete - people cascade with the request - matching the
product standard that a delete named "delete" deletes.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.models.company import Company
from app.models.onboarding import REVIEW_APPROVED, REVIEW_ON_HOLD, REVIEW_REJECTED
from app.models.onboarding import OnboardingRequest
from app.models.user import User
from app.dependencies import require_permission
from app.schemas.onboarding import (
    ApproveResultOut,
    CaptureTemplateIn,
    PersonPatchIn,
    RejectIn,
    RequestCreateIn,
    RequestDetailOut,
    RequestSummaryOut,
    TemplateOut,
    TemplateWriteIn,
)
from app.services import onboarding_service
from app.services.onboarding_serializers import (
    person_out,
    public_template_option,
    template_out,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _company_name(db: Session, company_id: Optional[str]) -> str:
    if not company_id:
        return ""
    company = db.query(Company).filter(Company.id == company_id).first()
    return getattr(company, "name", None) or ""


def _intake_url(request: OnboardingRequest) -> Optional[str]:
    """The link the captain copies into WhatsApp himself.

    The token is in the PATH, not a query string, so the URL survives being
    pasted into a chat, bookmarked and re-opened - which is what a multi-use,
    edit-over-several-days link has to survive.
    """
    base = (app_settings.frontend_base_url or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/onboarding/{request.token}"


def _summary(db: Session, request: OnboardingRequest) -> RequestSummaryOut:
    people = list(request.people)
    return RequestSummaryOut(
        id=str(request.id),
        title=request.title,
        company_name=_company_name(db, request.company_id),
        requester_name=request.requester_name,
        requester_email=request.requester_email,
        status=request.status_key,
        people_count=len(people),
        approved_count=sum(1 for p in people if p.review_status == REVIEW_APPROVED),
        rejected_count=sum(1 for p in people if p.review_status == REVIEW_REJECTED),
        submitted_at=request.submitted_at,
        created_at=request.created_at,
        expires_at=request.expires_at,
        revoked_at=request.revoked_at,
    )


def _detail(db: Session, request: OnboardingRequest) -> RequestDetailOut:
    collisions = onboarding_service.collisions_for(db, request)
    reviewer = None
    if request.reviewed_by_user_id:
        user = db.query(User).filter(User.id == request.reviewed_by_user_id).first()
        reviewer = (user.name or user.email) if user else None

    base = _summary(db, request)
    return RequestDetailOut(
        **base.model_dump(),
        reviewer_note=request.reviewer_note,
        requester_note=request.requester_note,
        reviewed_by_name=reviewer,
        provisioned_at=request.provisioned_at,
        source_file_name=request.source_file_name,
        templates=[
            public_template_option(t)
            for t in onboarding_service.list_templates(db, active_only=True)
        ],
        people=[
            person_out(db, p, collisions=collisions.get(str(p.id), []))
            for p in request.people
        ],
        intake_url=_intake_url(request),
    )


# --- requests -----------------------------------------------------------------


@router.get("/requests", response_model=list[RequestSummaryOut])
def list_requests(
    query: Optional[str] = Query(default=None),
    status_key: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_permission("user_management.onboarding.view")),
    db: Session = Depends(get_db),
):
    return [
        _summary(db, r)
        for r in onboarding_service.list_requests(db, status_key=status_key, query=query)
    ]


@router.post("/requests", response_model=RequestDetailOut, status_code=201)
def create_request(
    payload: RequestCreateIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.add")),
    db: Session = Depends(get_db),
):
    request = onboarding_service.create_request(
        db,
        company_id=payload.company_id,
        title=payload.title,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        requester_phone=payload.requester_phone,
        expiry_days=payload.expiry_days,
        user_id=current_user["id"],
    )
    return _detail(db, request)


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.view")),
    db: Session = Depends(get_db),
):
    return _detail(db, onboarding_service.get_request(db, request_id))


@router.delete("/requests/{request_id}", status_code=204)
def delete_request(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.delete")),
    db: Session = Depends(get_db),
):
    """Hard delete. People cascade with it."""
    request = onboarding_service.get_request(db, request_id)
    db.delete(request)
    db.commit()


@router.post("/requests/{request_id}/send", response_model=RequestDetailOut)
def send_request(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.add")),
    db: Session = Depends(get_db),
):
    request = onboarding_service.send_request(db, request_id, user_id=current_user["id"])
    # Post-commit: the link is live whether or not the email lands, and the
    # captain can always copy `intake_url` out of the response.
    try:
        _email_intake_link(db, request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Onboarding: intake link email for %s failed: %s", request.id, exc)
    return _detail(db, request)


@router.post("/requests/{request_id}/revoke", response_model=RequestDetailOut)
def revoke_request(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    return _detail(db, onboarding_service.revoke(db, request_id))


@router.post("/requests/{request_id}/regenerate-token", response_model=RequestDetailOut)
def regenerate_token(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    return _detail(db, onboarding_service.regenerate_token(db, request_id))


@router.post("/requests/{request_id}/start-review", response_model=RequestDetailOut)
def start_review(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    return _detail(
        db, onboarding_service.start_review(db, request_id, user_id=current_user["id"])
    )


@router.post("/requests/{request_id}/reject", response_model=RequestDetailOut)
def reject_request(
    request_id: str,
    payload: RejectIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.approve")),
    db: Session = Depends(get_db),
):
    return _detail(
        db,
        onboarding_service.reject_request(
            db, request_id, reason=payload.reason, user_id=current_user["id"]
        ),
    )


@router.post("/requests/{request_id}/approve", response_model=ApproveResultOut)
def approve_request(
    request_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.approve")),
    db: Session = Depends(get_db),
):
    """Approve the batch and queue provisioning.

    The enqueue happens AFTER the transition commits: a job that starts against
    an uncommitted status reads the request as still `in_review` and does
    nothing. A second approve never reaches here - the status graph refuses the
    edge, which is what makes double-clicking safe rather than merely unlikely.
    """
    request = onboarding_service.approve(db, request_id, user_id=current_user["id"])
    queued = sum(1 for p in request.people if p.review_status == REVIEW_APPROVED)

    job_id = None
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.onboarding_tasks import provision_onboarding_request

        job = enqueue_job(provision_onboarding_request, str(request.id), queue_name="imports")
        job_id = job.id
    except Exception:  # noqa: BLE001
        # The transition has ALREADY committed. Raising here would report a
        # failure for an approval that happened, and the retry would then be
        # refused by the graph (processing has no incoming edge from
        # in_review's predecessor). The request sits in `processing`, the job is
        # idempotent, and `job_id: null` is the signal that it needs requeueing.
        logger.exception("Onboarding: could not queue provisioning for %s", request.id)

    return ApproveResultOut(status=request.status_key, job_id=job_id, queued_people=queued)


# --- people -------------------------------------------------------------------


@router.put("/requests/{request_id}/people/{person_id}", response_model=RequestDetailOut)
def update_person(
    request_id: str,
    person_id: str,
    payload: PersonPatchIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    request = onboarding_service.get_request(db, request_id)
    onboarding_service.update_person(
        db, person_id, payload.model_dump(exclude_unset=True)
    )
    db.refresh(request)
    return _detail(db, request)


@router.post("/requests/{request_id}/people/{person_id}/keep", response_model=RequestDetailOut)
def keep_person(
    request_id: str,
    person_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    request = onboarding_service.get_request(db, request_id)
    onboarding_service.set_person_verdict(db, person_id, verdict=REVIEW_APPROVED)
    db.refresh(request)
    return _detail(db, request)


@router.post("/requests/{request_id}/people/{person_id}/hold", response_model=RequestDetailOut)
def hold_person(
    request_id: str,
    person_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    request = onboarding_service.get_request(db, request_id)
    onboarding_service.set_person_verdict(db, person_id, verdict=REVIEW_ON_HOLD)
    db.refresh(request)
    return _detail(db, request)


@router.post("/requests/{request_id}/people/{person_id}/reject", response_model=RequestDetailOut)
def reject_person(
    request_id: str,
    person_id: str,
    payload: RejectIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    """A reason is required, and it is required HERE as well as in the dialog."""
    request = onboarding_service.get_request(db, request_id)
    onboarding_service.set_person_verdict(
        db, person_id, verdict=REVIEW_REJECTED, reason=payload.reason
    )
    db.refresh(request)
    return _detail(db, request)


# --- templates ----------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    current_user: dict = Depends(require_permission("user_management.onboarding.view")),
    db: Session = Depends(get_db),
):
    return [template_out(t) for t in onboarding_service.list_templates(db)]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateWriteIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    return template_out(
        onboarding_service.create_template(db, payload.model_dump(), user_id=current_user["id"])
    )


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: str,
    payload: TemplateWriteIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    return template_out(
        onboarding_service.update_template(db, template_id, payload.model_dump(exclude_unset=True))
    )


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    current_user: dict = Depends(require_permission("user_management.onboarding.delete")),
    db: Session = Depends(get_db),
):
    onboarding_service.delete_template(db, template_id)


@router.post("/templates/capture-from-user/{user_id}", response_model=TemplateOut, status_code=201)
def capture_template(
    user_id: str,
    payload: CaptureTemplateIn,
    current_user: dict = Depends(require_permission("user_management.onboarding.edit")),
    db: Session = Depends(get_db),
):
    """Turn one existing user's roles and companies into a named template."""
    return template_out(
        onboarding_service.capture_template_from_user(
            db, user_id, name=payload.name, actor_user_id=current_user["id"]
        )
    )


# --- notifications ------------------------------------------------------------


def _email_intake_link(db: Session, request: OnboardingRequest) -> None:
    url = _intake_url(request)
    if not url:
        logger.warning(
            "Onboarding: FRONTEND_BASE_URL is unset, so no intake link could be emailed "
            "for request %s. Copy `intake_url` from the API response instead.",
            request.id,
        )
        return

    from app.services import email_outbox_service

    expires = request.expires_at.strftime("%d %b %Y")
    body_text = (
        f"Hello {request.requester_name},\n\n"
        "Sorento asks you to submit your team for onboarding. Open the link below, "
        "upload your existing list or type the names in, and submit it once.\n\n"
        f"{url}\n\n"
        f"The link works until {expires} and you can come back to it as often as you like "
        "until you submit.\n\n"
        "This is a system-generated email. Please do not reply."
    )
    body_html = (
        f"<p>Hello {request.requester_name},</p>"
        "<p>Sorento asks you to submit your team for onboarding. Open the link below, "
        "upload your existing list or type the names in, and submit it once.</p>"
        f'<p><a href="{url}">{url}</a></p>'
        f"<p>The link works until {expires} and you can come back to it as often as you "
        "like until you submit.</p>"
        "<p><em>This is a system-generated email. Please do not reply.</em></p>"
    )
    email_outbox_service.enqueue(
        db,
        event_key="onboarding_intake_link",
        to=request.requester_email,
        subject=f"Submit your team for onboarding: {request.title}",
        body_text=body_text,
        body_html=body_html,
        from_name="Sorento AI System",
        metadata={"onboarding_request_id": str(request.id)},
    )
    db.commit()
