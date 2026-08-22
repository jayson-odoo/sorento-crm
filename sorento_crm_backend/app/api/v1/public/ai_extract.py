"""Public (portal-token scoped) AI extract endpoints.

Reuses the same ``X-Portal-Token`` auth as ``/api/v1/public/portal/*`` and
the same per-tenant attachment quota (file size + extension whitelist).

Endpoints:

- ``GET  /api/v1/public/portal/ai-extract/schema?form_key=...`` - return the
  resolved schema + per-field guidance (lookup options, product hints) so the
  FE can show the user what fields will be attempted.
- ``POST /api/v1/public/portal/ai-extract`` - multipart, accepts ``form_key``
  + ``files`` (repeated). Returns a structured ``ExtractResult``.

Both handlers are plain ``def``, so FastAPI runs them in its threadpool: the
extract does a PDF render plus an LLM round trip, and on the loop that froze
every other request on the worker. Same defect, same fix as the flyer read in
PR #164. Measured 5.8 to 9.8 s per image on 2026-08-13 against the portal
extract path (documentation/plans/ai-extract/PLAN-ai-extract-off-the-loop.md);
re-measure before reusing the number.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.portal import PortalToken
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
def ai_extract(
    form_key: Annotated[str, Form(min_length=1)],
    files: Annotated[list[UploadFile], File(...)],
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> ExtractResult:
    """Extract structured fields out of what the contact uploaded.

    Plain ``def``, so FastAPI runs the whole handler in a thread rather than on
    the event loop: ``AIExtractService.extract`` is synchronous and slow (PDF
    render plus LLM), and as an ``async def`` it blocked every concurrent
    request on the worker. ``async`` bought nothing else here, because each file
    is read whole before the running total is checked, so there was never any
    streaming size enforcement to keep. That is the difference from the flyer
    upload route, which stays ``async def`` precisely so it can refuse oversized
    bytes as they arrive. Sibling fix: PR #164.
    """
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
        data = f.file.read()
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

    service = AIExtractService(db)
    try:
        return service.extract(
            form_key,
            payload,
            user_id=None,
            portal_contact_id=token.contact_id,
        )
    except KeyError:
        raise handle_validation_error(f"Unknown form_key: {form_key}")
