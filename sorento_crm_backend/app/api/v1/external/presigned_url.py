"""External API: get a CloudFront presigned URL for a given file path (S3 key or CloudFront base URL)."""
import logging
from urllib.parse import urlparse, unquote

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_external_api_user
from app.services.s3_service import S3Service
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class PresignedUrlRequest(BaseModel):
    """Request body for presigned URL generation."""

    file_path: str = Field(..., description="S3 key (e.g. promotion/uuid/file.pdf) or CloudFront base URL (https://domain/key)")
    filename: str | None = Field(None, description="Optional display name for the file (echoed in response)")
    expires_in: int = Field(3600, ge=60, le=86400, description="URL validity in seconds (default 3600, max 24h)")


class PresignedUrlResponse(BaseModel):
    """Response with CloudFront presigned URL."""

    presigned_url: str = Field(..., description="CloudFront signed URL with Policy, Signature, Key-Pair-Id")
    file_path: str = Field(..., description="Normalized S3 key used for signing")
    filename: str | None = Field(None, description="Filename if provided in request")
    expires_in: int = Field(..., description="Expiry in seconds")


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


@router.post("/", response_model=PresignedUrlResponse)
async def get_presigned_url(
    body: PresignedUrlRequest,
    current_user: dict = Depends(get_external_api_user),
):
    """
    Return a CloudFront presigned URL for the given file path.

    **Auth:** X-API-Key header (external API key).

    **Request body:**
    - **file_path** (required): S3 key (e.g. `promotion/abc/file.pdf`) or CloudFront base URL.
    - **filename** (optional): Display name; echoed in response.
    - **expires_in** (optional): URL validity in seconds (60–86400). Default 3600.

    **Response:** `presigned_url` (use for download/preview), `file_path`, `filename`, `expires_in`.
    """
    try:
        s3_key = _normalize_to_s3_key(body.file_path)
        s3 = S3Service()
        presigned_url = s3.get_signed_url(s3_key, expires_in=body.expires_in)
        return PresignedUrlResponse(
            presigned_url=presigned_url,
            file_path=s3_key,
            filename=body.filename,
            expires_in=body.expires_in,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.warning("Presigned URL generation failed for file_path=%s: %s", (body.file_path or "")[:80], e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate presigned URL. Check file_path and S3/CloudFront configuration.",
        )
