"""Public user submission portal endpoints (no CRM login).

Auth: 7-day portal token. Token travels in either:
- ``X-Portal-Token`` header
- ``token`` query parameter

When a token expires the contact requests an OTP via ``POST /request-otp`` and
exchanges the code for a fresh token via ``POST /verify-otp``.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalToken
from app.models.resources import Attachment, AttachmentType
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import handle_validation_error
from app.services.portal_service import (
    PORTAL_ATTACHMENT_TYPE_CODE,
    PortalAuthError,
    PortalService,
    SUPPORTED_TYPES,
)
from app.services.s3_service import S3Service

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_portal_token(
    db: Session,
    header_token: Optional[str],
    query_token: Optional[str],
) -> PortalToken:
    raw = (header_token or query_token or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal token is required.",
        )
    try:
        return PortalService(db).resolve_token(raw)
    except PortalAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e


def get_portal_token(
    x_portal_token: Annotated[Optional[str], Header(alias="X-Portal-Token")] = None,
    token: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
) -> PortalToken:
    return _resolve_portal_token(db, x_portal_token, token)


# ---------- OTP ----------


class OtpRequestPayload(BaseModel):
    contact_id: str
    space_id: str


class OtpVerifyPayload(BaseModel):
    contact_id: str
    space_id: str
    code: str = Field(..., min_length=4, max_length=10)


class OtpResponse(BaseModel):
    sent_to: Optional[str]
    expires_at: str


class TokenResponse(BaseModel):
    token: str
    expires_at: str


@router.post("/request-otp", response_model=OtpResponse)
def portal_request_otp(payload: OtpRequestPayload, db: Session = Depends(get_db)):
    return PortalService(db).request_otp(payload.contact_id, payload.space_id)


@router.post("/verify-otp", response_model=TokenResponse)
def portal_verify_otp(payload: OtpVerifyPayload, db: Session = Depends(get_db)):
    token = PortalService(db).verify_otp(payload.contact_id, payload.space_id, payload.code)
    return TokenResponse(token=token.token, expires_at=token.expires_at.isoformat())


# ---------- Contact ----------


class PortalMeResponse(BaseModel):
    contact_id: str
    space_id: str
    name: Optional[str]
    phone_number: Optional[str]
    expires_at: str


@router.get("/me", response_model=PortalMeResponse)
def portal_me(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    contact = PortalService(db).get_contact(token)
    return PortalMeResponse(
        contact_id=token.contact_id,
        space_id=token.space_id,
        name=contact.name or " ".join(filter(None, [contact.first_name, contact.last_name])).strip() or None,
        phone_number=contact.phone_number,
        expires_at=token.expires_at.isoformat(),
    )


# ---------- Submissions ----------


class SubmissionPayload(BaseModel):
    fields: dict
    products: Optional[list[dict]] = None  # purchase_request / sponsorship_form


def _flatten_payload(payload: SubmissionPayload) -> dict:
    body = dict(payload.fields or {})
    if payload.products is not None:
        body["products"] = payload.products
    return body


def _check_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in SUPPORTED_TYPES:
        raise handle_validation_error(f"Unsupported submission type: {kind!r}.")
    return k


@router.get("/submissions")
def portal_list_submissions(
    type: str = Query(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return {"items": PortalService(db).list_submissions(token, _check_kind(type))}


@router.get("/submissions/{kind}/{submission_id}")
def portal_get_submission(
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    detail = PortalService(db).get_submission(token, _check_kind(kind), submission_id)
    detail["attachments"] = _list_attachments_for(db, _entity_type_for(kind), submission_id)
    return detail


@router.post("/submissions/{kind}")
def portal_create_draft(
    payload: SubmissionPayload,
    kind: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return PortalService(db).create_or_update_draft(
        token, _check_kind(kind), _flatten_payload(payload)
    )


@router.put("/submissions/{kind}/{submission_id}")
def portal_update_draft(
    payload: SubmissionPayload,
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return PortalService(db).create_or_update_draft(
        token, _check_kind(kind), _flatten_payload(payload), submission_id
    )


@router.post("/submissions/{kind}/{submission_id}/submit")
def portal_submit(
    kind: str = Path(...),
    submission_id: str = Path(...),
    payload: Optional[SubmissionPayload] = Body(default=None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    body = _flatten_payload(payload) if payload else None
    return PortalService(db).submit_draft(
        token, _check_kind(kind), submission_id, body
    )


# ---------- Attachments ----------


def _entity_type_for(kind: str) -> str:
    """Sponsorship form shares the purchase_request entity_type for attachments."""
    return "purchase_request" if kind == "sponsorship_form" else kind


def _ext(filename: Optional[str], content_type: Optional[str]) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower().strip()
    if content_type and "/" in content_type:
        return content_type.split("/", 1)[1].split(";", 1)[0].strip().lower()
    return ""


def _check_quota(
    db: Session,
    attachment_type: AttachmentType,
    entity_type: str,
    entity_id: str,
    incoming_size: int,
    incoming_ext: str,
) -> None:
    allowed_exts = {
        e.strip().lower().lstrip(".")
        for e in (attachment_type.allowed_extensions or "").split(",")
        if e.strip()
    }
    if allowed_exts and incoming_ext not in allowed_exts:
        raise handle_validation_error(
            f"Unsupported file type. Allowed: {', '.join(sorted(allowed_exts))}."
        )
    max_bytes = (attachment_type.max_file_size_mb or 0) * 1024 * 1024
    if max_bytes and incoming_size > max_bytes:
        raise handle_validation_error(
            f"File exceeds {attachment_type.max_file_size_mb} MB limit."
        )
    if attachment_type.max_count_per_entity is not None:
        existing = (
            db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == entity_type,
                EntityAttachmentLink.entity_id == entity_id,
            )
            .count()
        )
        if existing >= attachment_type.max_count_per_entity:
            raise handle_validation_error(
                f"Attachment limit reached ({attachment_type.max_count_per_entity})."
            )


def _list_attachments_for(db: Session, entity_type: str, entity_id: str) -> list[dict]:
    rows = (
        db.query(EntityAttachmentLink, Attachment)
        .join(Attachment, Attachment.id == EntityAttachmentLink.attachment_id)
        .filter(
            EntityAttachmentLink.entity_type == entity_type,
            EntityAttachmentLink.entity_id == entity_id,
        )
        .order_by(EntityAttachmentLink.sort_order.asc().nulls_last(), EntityAttachmentLink.created_at.asc())
        .all()
    )
    out: list[dict] = []
    for link, att in rows:
        out.append(
            {
                "link_id": str(link.id),
                "attachment_id": str(att.id),
                "filename": att.original_filename,
                "size": att.file_size_bytes,
                "url": att.file_path,
                "uploaded_at": att.uploaded_at.isoformat() if att.uploaded_at else None,
            }
        )
    return out


@router.get("/attachments")
def portal_list_attachments(
    kind: str = Query(...),
    submission_id: str = Query(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    k = _check_kind(kind)
    # Ensures the contact owns this submission.
    PortalService(db).get_submission(token, k, submission_id)
    return {"items": _list_attachments_for(db, _entity_type_for(k), submission_id)}


@router.post("/attachments")
async def portal_upload_attachment(
    kind: Annotated[str, Form()],
    submission_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File(...)],
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    portal = PortalService(db)
    k = _check_kind(kind)
    portal.get_submission(token, k, submission_id)  # ownership check
    attachment_type = portal.get_portal_attachment_type()

    contents = await file.read()
    incoming_size = len(contents)
    extension = _ext(file.filename, file.content_type)
    _check_quota(
        db,
        attachment_type,
        _entity_type_for(k),
        submission_id,
        incoming_size,
        extension,
    )

    safe_ext = f".{extension}" if extension else ""
    s3_key = f"portal/{token.contact_id}/{uuid.uuid4()}{safe_ext}"
    try:
        S3Service().upload_file(contents, s3_key, content_type=file.content_type)
    except Exception as e:  # noqa: BLE001
        logger.warning("Portal attachment upload failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="File upload failed. Please try again.",
        ) from e

    service = EntityAttachmentService(db)
    link = service.create_attachment_and_link(
        entity_type=_entity_type_for(k),
        entity_id=submission_id,
        file_url=s3_key,
        file_name=file.filename or os.path.basename(s3_key),
        file_size_bytes=incoming_size,
        attachment_type_code=PORTAL_ATTACHMENT_TYPE_CODE,
        created_by=None,
    )
    db.commit()
    db.refresh(link)
    attachment = db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
    return {
        "link_id": str(link.id),
        "attachment_id": str(link.attachment_id),
        "filename": attachment.original_filename if attachment else file.filename,
        "size": incoming_size,
        "url": attachment.file_path if attachment else s3_key,
    }


@router.delete("/attachments/{link_id}")
def portal_delete_attachment(
    link_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    link = (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.id == link_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    portal = PortalService(db)
    raw_kind = link.entity_type
    # sponsorship_form attachments live under entity_type=purchase_request; verify ownership against either type.
    if raw_kind == "purchase_request":
        owns = False
        for k in ("purchase_request", "sponsorship_form"):
            try:
                portal.get_submission(token, k, link.entity_id)
                owns = True
                break
            except HTTPException:
                continue
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    else:
        portal.get_submission(token, raw_kind, link.entity_id)

    EntityAttachmentService(db).delete_link(link_id)
    db.commit()
    return {"deleted": True}
