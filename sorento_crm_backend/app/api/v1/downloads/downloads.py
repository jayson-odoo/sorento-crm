"""Per-user downloads (My Downloads drawer): list rows + resolve a signed URL.

Rows are created by export endpoints (e.g. POST complaints/{id}/export/pdf) and
populated asynchronously by RQ tasks. These endpoints are scoped to the current
user — a download is only visible/resolvable by the user who requested it.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.download import DownloadStatus
from app.schemas.download import DownloadListResponse, DownloadResponse, DownloadUrlResponse
from app.services.download_service import DownloadService
from app.services.storage_router import resolve_signed_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=DownloadListResponse)
def list_my_downloads(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadListResponse:
    user_id = str(current_user["id"])
    rows = DownloadService(db).list_for_user(user_id, limit=max(1, min(limit, 200)))
    return DownloadListResponse(downloads=[DownloadResponse.model_validate(r) for r in rows])


@router.get("/{download_id}/url", response_model=DownloadUrlResponse)
def get_download_url(
    download_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadUrlResponse:
    user_id = str(current_user["id"])
    row = DownloadService(db).get_for_user(download_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Download not found")
    if row.status != DownloadStatus.READY.value or not row.storage_key:
        raise HTTPException(status_code=409, detail=f"Download is not ready (status: {row.status})")
    url = resolve_signed_url(row.storage_key, provider=row.storage_provider, expires_in=3600)
    if not url:
        raise HTTPException(status_code=500, detail="Could not resolve a download URL")
    return DownloadUrlResponse(url=url, filename=row.filename)
