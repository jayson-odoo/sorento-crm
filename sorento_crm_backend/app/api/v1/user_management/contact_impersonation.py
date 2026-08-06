"""Admin → contact portal impersonation routes.

Lets an admin enter the public submission portal as a contact without going
through the OTP verification step. The minted portal token is marked verified
at issuance, so it bypasses the OTP gate in ``PortalService.resolve_token``.

Audit / created_by / updated_by on anything the admin does inside the portal
remain the real admin via ``set_audit_context`` (the portal write paths use
the same audit context as the rest of the app for these endpoints).
"""
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_real_user
from app.models.access import RespondContact
from app.models.impersonation import ContactImpersonationSession
from app.models.portal import PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.audit_service import log_audit
from app.services.error_handler import handle_not_found
from app.services.portal_service import PORTAL_TOKEN_TTL, PortalService
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)

router = APIRouter()


class StartContactImpersonationRequest(BaseModel):
    contact_id: str


class TargetContactSummary(BaseModel):
    id: str
    name: Optional[str]
    phone_number: Optional[str]
    space_id: str


class ContactImpersonationSessionResponse(BaseModel):
    session_id: str
    started_at: datetime
    portal_url: str
    target_contact: TargetContactSummary


def _ensure_admin(db: Session, real_user: dict) -> None:
    role_slugs = UserPermissionService(db).get_user_role_slugs(real_user["id"])
    admin_set = {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}
    if not (role_slugs & admin_set):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can impersonate contacts.",
        )


def _resolve_contact_and_space(db: Session, contact_id: str) -> tuple[RespondContact, str]:
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)
    if not contact.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no workspace; cannot impersonate.",
        )
    workspace = (
        db.query(RespondWorkspace)
        .filter(RespondWorkspace.id == contact.workspace_id)
        .first()
    )
    if workspace is None or not workspace.space_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no workspace; cannot impersonate.",
        )
    return contact, workspace.space_id


def _serialize(
    session_row: ContactImpersonationSession,
    contact: RespondContact,
    space_id: str,
    portal_url: str,
) -> ContactImpersonationSessionResponse:
    name = contact.name or " ".join(
        filter(None, [contact.first_name, contact.last_name])
    ).strip() or None
    return ContactImpersonationSessionResponse(
        session_id=session_row.id,
        started_at=session_row.started_at,
        portal_url=portal_url,
        target_contact=TargetContactSummary(
            id=contact.id,
            name=name,
            phone_number=contact.phone_number,
            space_id=space_id,
        ),
    )


@router.post("/start", response_model=ContactImpersonationSessionResponse)
def start_contact_impersonation(
    body: StartContactImpersonationRequest,
    request: Request,
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
) -> ContactImpersonationSessionResponse:
    _ensure_admin(db, real_user)
    target_id = (body.contact_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="contact_id is required")

    contact, space_id = _resolve_contact_and_space(db, target_id)

    # End any prior active session so the partial unique index never blocks.
    prior = (
        db.query(ContactImpersonationSession)
        .filter(
            ContactImpersonationSession.admin_user_id == real_user["id"],
            ContactImpersonationSession.ended_at.is_(None),
        )
        .all()
    )
    for prev in prior:
        prev.ended_at = datetime.utcnow()
        prev_token = (
            db.query(PortalToken)
            .filter(PortalToken.id == prev.portal_token_id)
            .first()
        )
        if prev_token is not None and prev_token.revoked_at is None:
            prev_token.revoked_at = datetime.utcnow()

    now = datetime.utcnow()
    token_row = PortalToken(
        token=secrets.token_urlsafe(48),
        contact_id=contact.id,
        space_id=space_id,
        expires_at=now + PORTAL_TOKEN_TTL,
        verified_at=now,
        # Excluded from the sliding 30-day TTL and kept out of localStorage on
        # the FE (the ?impersonation=1 marker below routes it to sessionStorage).
        is_impersonation=True,
    )
    db.add(token_row)
    db.flush()

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session_row = ContactImpersonationSession(
        admin_user_id=real_user["id"],
        target_contact_id=contact.id,
        space_id=space_id,
        portal_token_id=token_row.id,
        started_ip=ip,
        started_user_agent=(ua or "")[:500] or None,
    )
    db.add(session_row)
    db.flush()

    log_audit(
        db,
        entity_type="contact_impersonation_session",
        entity_id=session_row.id,
        action="CREATE",
        user_id=real_user["id"],
        description="contact_impersonation_start",
        new_values={
            "admin_user_id": real_user["id"],
            "target_contact_id": contact.id,
            "space_id": space_id,
        },
        ip_address=ip,
    )
    db.commit()
    db.refresh(session_row)
    db.refresh(token_row)

    base = (app_settings.frontend_base_url or "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    portal_url = (
        f"{base}/portal?token={token_row.token}&impersonation=1"
        if base
        else f"/portal?token={token_row.token}&impersonation=1"
    )

    return _serialize(session_row, contact, space_id, portal_url)


@router.post("/stop")
def stop_contact_impersonation(
    request: Request,
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
):
    session_row = (
        db.query(ContactImpersonationSession)
        .filter(
            ContactImpersonationSession.admin_user_id == real_user["id"],
            ContactImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if not session_row:
        return {"ended": False}
    session_row.ended_at = datetime.utcnow()
    token_row = (
        db.query(PortalToken)
        .filter(PortalToken.id == session_row.portal_token_id)
        .first()
    )
    if token_row is not None and token_row.revoked_at is None:
        token_row.revoked_at = datetime.utcnow()
    db.flush()
    log_audit(
        db,
        entity_type="contact_impersonation_session",
        entity_id=session_row.id,
        action="UPDATE",
        user_id=real_user["id"],
        description="contact_impersonation_end",
        new_values={
            "admin_user_id": real_user["id"],
            "target_contact_id": session_row.target_contact_id,
            "ended_at": session_row.ended_at.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"ended": True, "session_id": session_row.id}


@router.get("/current", response_model=Optional[ContactImpersonationSessionResponse])
def current_contact_impersonation(
    request: Request,
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
):
    session_row = (
        db.query(ContactImpersonationSession)
        .filter(
            ContactImpersonationSession.admin_user_id == real_user["id"],
            ContactImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if not session_row:
        return None
    contact = (
        db.query(RespondContact)
        .filter(RespondContact.id == session_row.target_contact_id)
        .first()
    )
    token_row = (
        db.query(PortalToken)
        .filter(PortalToken.id == session_row.portal_token_id)
        .first()
    )
    if contact is None or token_row is None:
        return None
    base = (app_settings.frontend_base_url or "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    portal_url = (
        f"{base}/portal?token={token_row.token}&impersonation=1"
        if base
        else f"/portal?token={token_row.token}&impersonation=1"
    )
    return _serialize(session_row, contact, session_row.space_id, portal_url)
