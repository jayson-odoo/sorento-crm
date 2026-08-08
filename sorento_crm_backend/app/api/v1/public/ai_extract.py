"""Public (portal-token scoped) AI extract endpoints.

Reuses the same ``X-Portal-Token`` auth as ``/api/v1/public/portal/*`` and
the same per-tenant attachment quota (file size + extension whitelist).

Endpoints:

- ``GET  /api/v1/public/portal/ai-extract/schema?form_key=...`` — return the
  resolved schema + per-field guidance (lookup options, product hints) so the
  FE can show the user what fields will be attempted.
- ``POST /api/v1/public/portal/ai-extract`` — multipart, accepts ``form_key``
  + ``files`` (repeated). Returns a structured ``ExtractResult``.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.portal import PortalToken
from app.services.portal_intake_uploads import store_portal_upload
from app.services.ai_extract.extract_service import (
    AIExtractService,
    ExtractFile,
    ExtractResult,
)
from app.services.error_handler import handle_validation_error

logger = logging.getLogger(__name__)

router = APIRouter()


# Same constraints as the portal attachment quota; mirrored here so the
# extract endpoint is self-contained (and so we can include PDFs which the
# normal portal attachment table also accepts).
_MAX_FILES = 12
_MAX_TOTAL_BYTES = 150 * 1024 * 1024  # 150 MB (phone video clips)
_ALLOWED_EXTS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "pdf",
    "mp4",
    "mov",
    "webm",
    "m4v",
    "3gp",
    "txt",
}


def _ext(filename: str | None, mime: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower().strip()
    if mime and "/" in mime:
        return mime.split("/", 1)[1].split(";", 1)[0].strip().lower()
    return ""


@router.get("/ai-extract/schema")
def ai_extract_schema(
    form_key: Annotated[str, Query(min_length=1)],
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return AIExtractService(db).get_schema_with_guidance(form_key)
    except KeyError:
        raise handle_validation_error(f"Unknown form_key: {form_key}")


@router.post("/ai-extract", response_model=ExtractResult)
async def ai_extract(
    form_key: Annotated[str, Form(min_length=1)],
    files: Annotated[list[UploadFile], File(...)],
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> ExtractResult:
    if not files:
        raise handle_validation_error("Upload at least one file.")
    if len(files) > _MAX_FILES:
        raise handle_validation_error(
            f"Too many files; maximum is {_MAX_FILES} per extract request."
        )

    payload: list[ExtractFile] = []
    total = 0
    for f in files:
        ext = _ext(f.filename, f.content_type)
        if ext and ext not in _ALLOWED_EXTS:
            raise handle_validation_error(
                f"Unsupported file type: {f.filename}. Allowed: "
                f"{', '.join(sorted(_ALLOWED_EXTS))}."
            )
        data = await f.read()
        total += len(data)
        if total > _MAX_TOTAL_BYTES:
            raise handle_validation_error(
                "Combined file size exceeds 150 MB. Remove a file and try again."
            )
        payload.append(
            ExtractFile(
                filename=f.filename or f"upload.{ext or 'bin'}",
                mime=(f.content_type or "").lower(),
                data=data,
            )
        )

    # Store BEFORE extracting. The upload is evidence first and model input second: a
    # consumer who photographs a receipt has handed over the only proof of their purchase
    # date, and until now these bytes were read, sent to a model and dropped. Whether the
    # extractor recognises a receipt is a judgement about the file, never a reason to keep
    # or lose it - the ones it reads worst are exactly the ones a human most needs to see.
    stored = [
        store_portal_upload(
            db,
            contact_id=token.contact_id,
            filename=item.filename,
            content_type=item.mime,
            data=item.data,
        )
        for item in payload
    ]
    attachment_ids = [item.attachment_id for item in stored if item is not None]
    if attachment_ids:
        db.commit()

    service = AIExtractService(db)
    try:
        result = service.extract(
            form_key,
            payload,
            user_id=None,
            portal_contact_id=token.contact_id,
        )
    except KeyError:
        raise handle_validation_error(f"Unknown form_key: {form_key}")
    # Set after the call rather than threaded through the service: retention is the
    # endpoint's concern (it owns the request's files and its transaction), and the
    # extractor has no business knowing where its input was filed.
    result.attachment_ids = attachment_ids
    return result
