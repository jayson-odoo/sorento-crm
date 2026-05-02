"""External API: get a presigned URL for a stored file (S3+CloudFront or R2+Cloudflare CDN)."""
import logging
from urllib.parse import urlparse, unquote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.storage_router import (
    default_provider,
    detect_provider_from_url,
    get_backend,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class PresignedUrlRequest(BaseModel):
    """Request body for presigned URL generation."""

    file_path: str = Field(..., description="S3 key (e.g. promotion/uuid/file.pdf) or CloudFront base URL (https://domain/key)")
    filename: str | None = Field(None, description="Optional display name for the file (echoed in response)")
    expires_in: int = Field(3600, ge=60, le=86400, description="URL validity in seconds (default 3600, max 24h)")


class PresignedUrlResponse(BaseModel):
    """Response with a presigned URL backed by either CloudFront or Cloudflare CDN."""

    presigned_url: str = Field(..., description="Signed URL (CloudFront Policy/Signature for S3, AWS4-HMAC for R2)")
    file_path: str = Field(..., description="Normalized storage key used for signing")
    filename: str | None = Field(None, description="Filename if provided in request")
    expires_in: int = Field(..., description="Expiry in seconds")
    storage_provider: str = Field(..., description="'s3' or 'r2' — which provider served the URL")


def _normalize_to_s3_key(file_path: str) -> str:
    """Convert file_path (S3 key or CloudFront base URL) to a normalized S3 key."""
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("file_path is required")
    if raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        if parsed.query and "Policy=" in parsed.query and "Key-Pair-Id=" in parsed.query:
            # Already signed; we need the path without query
            path = (parsed.path or "").lstrip("/")
        else:
            path = (parsed.path or "").lstrip("/")
        key = unquote(path)
    else:
        key = unquote(raw).lstrip("/")
    if not key:
        raise ValueError("file_path could not be resolved to an S3 key")
    if ".." in key:
        raise ValueError("file_path must not contain '..'")
    return key


def _provider_for_file_path(db: Session, file_path: str) -> str:
    """Best-effort provider lookup so the right backend signs the URL.

    Tries DB lookup by stored file_path first (the canonical source of truth),
    then URL-host sniffing, finally STORAGE_DEFAULT_PROVIDER.
    """
    from app.models.resources import Attachment

    # Match the row by its stored file_path. Row ordering picks the most recent
    # so reuploads of the same key resolve to the latest provider.
    try:
        row = (
            db.query(Attachment.storage_provider)
            .filter(Attachment.file_path == file_path)
            .order_by(Attachment.uploaded_at.desc())
            .first()
        )
        if row and row[0]:
            return str(row[0])
    except Exception as e:  # noqa: BLE001
        logger.debug("storage_provider lookup failed for %s: %s", file_path[:80], e)

    sniffed = detect_provider_from_url(file_path)
    return sniffed or default_provider()


@router.post("/", response_model=PresignedUrlResponse)
async def get_presigned_url(
    body: PresignedUrlRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Return a presigned URL for the given file path.

    Dispatch automatically picks S3+CloudFront or R2+Cloudflare CDN based on
    the attachment row's ``storage_provider``.

    **Auth:** X-API-Key header (external API key).

    **Request body:**
    - **file_path** (required): storage key (e.g. `promotion/abc/file.pdf`) or full CDN base URL.
    - **filename** (optional): Display name; echoed in response.
    - **expires_in** (optional): URL validity in seconds (60–86400). Default 3600.

    **Response:** `presigned_url`, `file_path`, `filename`, `expires_in`, `storage_provider`.
    """
    try:
        key = _normalize_to_s3_key(body.file_path)
        provider = _provider_for_file_path(db, body.file_path)
        backend = get_backend(provider)
        presigned_url = backend.get_signed_url(key, expires_in=body.expires_in)
        return PresignedUrlResponse(
            presigned_url=presigned_url,
            file_path=key,
            filename=body.filename,
            expires_in=body.expires_in,
            storage_provider=provider,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.warning("Presigned URL generation failed for file_path=%s: %s", (body.file_path or "")[:80], e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate presigned URL. Check file_path and storage configuration.",
        )
