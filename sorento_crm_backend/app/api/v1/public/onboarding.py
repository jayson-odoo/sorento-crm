"""Public onboarding intake (no CRM login).

Auth: the per-request intake token, in either

- an ``X-Onboarding-Token`` header, or
- a ``token`` query parameter,

mirroring ``public/portal.py``'s ``get_portal_token``.

**No OTP, deliberately.** The contact portal fronts real CRM records, so it
verifies identity. What sits behind an intake token is the batch of names,
phones and emails the requester herself supplied - a leaked link exposes her own
submission and nothing else. Adding an OTP would buy no protection and would cost
the journey its "no account, no password" property.

The token is resolved with company scope OFF and everything after it runs inside
the request's own company scope, the same shape ``public/catalogue.py`` uses. A
public route has no session and therefore no resolved scope, and ``UNSET`` is
fail-closed, so without this every query in here returns zero rows.
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.company import Company
from app.models.onboarding import OnboardingRequest
from app.schemas.onboarding import (
    IntakeContextOut,
    ParseProblemOut,
    ParsedRowOut,
    ParseResultOut,
    PublicTemplateOption,
    SaveRowsIn,
    SubmitIn,
)
from app.services import onboarding_service
from app.services.onboarding_service import OnboardingAuthError
from app.services.onboarding_serializers import person_out, public_template_option

logger = logging.getLogger(__name__)

router = APIRouter()

#: Accepted upload shapes. `.xls` included because `sheet_rows` reads OLE2 too,
#: and a department head's phone list is as likely to be a 2003 workbook as not.
ALLOWED_EXTENSIONS = (".xlsx", ".xlsm", ".xls")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def get_onboarding_request(
    x_onboarding_token: Annotated[Optional[str], Header(alias="X-Onboarding-Token")] = None,
    token: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
) -> OnboardingRequest:
    raw = (x_onboarding_token or token or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="An onboarding link token is required.",
        )
    try:
        # Unscoped read: the token IS the authorisation, and the row it points at
        # is what tells us which company scope everything else should run in.
        with company_scope(db, None):
            request = onboarding_service.resolve_token(db, raw)
            # Touch the company while the scope is still open so the context
            # response can name it without a second unscoped read.
            _ = request.company_id
        return request
    except OnboardingAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e


def _company_name(db: Session, request: OnboardingRequest) -> str:
    company = db.query(Company).filter(Company.id == request.company_id).first()
    return getattr(company, "name", None) or "your company"


def _editable(request: OnboardingRequest) -> bool:
    return request.status_key in onboarding_service.REQUESTER_WRITABLE


def _context(db: Session, request: OnboardingRequest) -> IntakeContextOut:
    templates = [
        public_template_option(t)
        for t in onboarding_service.list_templates(db, active_only=True)
    ]
    return IntakeContextOut(
        title=request.title,
        company_name=_company_name(db, request),
        requester_name=request.requester_name,
        requester_email=request.requester_email,
        status=request.status_key,
        expires_at=request.expires_at,
        editable=_editable(request),
        requester_note=request.requester_note,
        templates=templates,
        # No collisions: what already exists in the CRM is the reviewer's
        # business, not the requester's.
        people=[person_out(db, p) for p in request.people],
    )


@router.get("/me", response_model=IntakeContextOut)
def onboarding_me(
    request: OnboardingRequest = Depends(get_onboarding_request),
    db: Session = Depends(get_db),
):
    """Everything the page needs, including the read-only view after submission."""
    with company_scope(db, frozenset({str(request.company_id)})):
        return _context(db, request)


@router.get("/templates", response_model=list[PublicTemplateOption])
def onboarding_templates(
    request: OnboardingRequest = Depends(get_onboarding_request),
    db: Session = Depends(get_db),
):
    with company_scope(db, frozenset({str(request.company_id)})):
        return [
            public_template_option(t)
            for t in onboarding_service.list_templates(db, active_only=True)
        ]


@router.post("/parse", response_model=ParseResultOut)
async def onboarding_parse(
    http_request: Request,
    file: UploadFile = File(...),
    request: OnboardingRequest = Depends(get_onboarding_request),
    db: Session = Depends(get_db),
):
    """Read a workbook into rows plus complaints. Writes nothing.

    Rate-limited per IP. This is unauthenticated-by-account compute that opens a
    spreadsheet, and the per-request token does not bound how often one link can
    be used - it is multi-use by design. Fail-open, like the portal's OTP limit:
    a broken limiter must not take the feature down.
    """
    from app.config import settings as app_settings
    from app.services import rate_limit

    ip = http_request.client.host if http_request.client else None
    gate = rate_limit.hit(
        "onboarding_parse",
        ip,
        limit=app_settings.rate_limit_onboarding_parse_max,
        window_seconds=app_settings.rate_limit_onboarding_parse_window_seconds,
    )
    if not gate.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many uploads. Please try again shortly.",
            headers={
                "Retry-After": str(
                    gate.retry_after_seconds
                    or app_settings.rate_limit_onboarding_parse_window_seconds
                )
            },
        )

    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload an Excel workbook (.xlsx, .xlsm or .xls).",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="That file is larger than 10 MB.",
        )

    from app.services import onboarding_reader

    with company_scope(db, frozenset({str(request.company_id)})):
        result = onboarding_reader.read_workbook(data, db=db)

    return ParseResultOut(
        rows=[
            ParsedRowOut(
                row_number=row.row_number,
                full_name=row.full_name,
                nick_name=row.nick_name,
                phone_raw=row.phone_raw,
                email_raw=row.email_raw,
                section_label=row.section_label,
                problems=row.problems,
            )
            for row in result.rows
        ],
        problems=[ParseProblemOut(row=p.row_number, reason=p.reason) for p in result.problems],
        unmapped_headers=result.unmapped_headers,
        missing_columns=result.missing_columns,
        total_rows=result.total_rows,
        sections=result.sections,
    )


@router.put("/rows", response_model=IntakeContextOut)
def onboarding_save_rows(
    payload: SaveRowsIn,
    request: OnboardingRequest = Depends(get_onboarding_request),
    db: Session = Depends(get_db),
):
    """Save the draft. Whole-list replace; refused once the batch is submitted."""
    with company_scope(db, frozenset({str(request.company_id)})):
        onboarding_service.replace_people(
            db, request, [row.model_dump() for row in payload.rows]
        )
        return _context(db, request)


@router.post("/submit", response_model=IntakeContextOut)
def onboarding_submit(
    payload: SubmitIn,
    request: OnboardingRequest = Depends(get_onboarding_request),
    db: Session = Depends(get_db),
):
    """Send the batch for review. The same link becomes the status page."""
    with company_scope(db, frozenset({str(request.company_id)})):
        if payload.requester_note is not None:
            request.requester_note = payload.requester_note.strip() or None
        onboarding_service.submit(db, request)

        # Post-commit and therefore best-effort on BOTH sides: the submission has
        # already landed, and a failed notification must not report a failure for
        # work that succeeded (the retry would take the idempotent path and never
        # re-send anyway).
        try:
            _notify_submission(db, request)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Onboarding: submission notifications for %s failed: %s", request.id, exc
            )

        return _context(db, request)


def _notify_submission(db: Session, request: OnboardingRequest) -> None:
    """Confirm to the requester, and put it in front of the captain."""
    from app.services import email_outbox_service
    from app.services.notification_service import NotificationService

    count = len(request.people)
    body = (
        f"Hello {request.requester_name},\n\n"
        f"We have received your onboarding submission '{request.title}' "
        f"with {count} {'person' if count == 1 else 'people'}.\n\n"
        "Somebody will review it and you will get one more email when it is done. "
        "Your original link now shows the status of each person.\n\n"
        "This is a system-generated email. Please do not reply."
    )
    email_outbox_service.enqueue(
        db,
        event_key="onboarding_submitted",
        to=request.requester_email,
        subject=f"Received: {request.title}",
        body_text=body,
        from_name="Sorento AI System",
        metadata={"onboarding_request_id": str(request.id), "people": count},
    )

    # In-app for whoever asked for the batch, and for whoever is already on it.
    recipients = {
        str(uid)
        for uid in (request.created_by_user_id, request.reviewed_by_user_id)
        if uid
    }
    for user_id in recipients:
        NotificationService(db).create_with_channel_preferences(
            user_id=user_id,
            type="onboarding_submitted",
            title="Onboarding submission received",
            body=(
                f"{request.requester_name} submitted {count} "
                f"{'person' if count == 1 else 'people'} for '{request.title}'."
            ),
            data={"onboarding_request_id": str(request.id)},
            send_in_app=True,
            send_email=False,
            send_web_push=False,
        )
    db.commit()
