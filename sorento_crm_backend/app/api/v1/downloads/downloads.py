"""Per-user downloads (My Downloads drawer): list rows + resolve a signed URL.

Rows are created by export endpoints (e.g. POST complaints/{id}/export/pdf) and
populated asynchronously by RQ tasks. These endpoints are scoped to the current
user - a download is only visible/resolvable by the user who requested it.
"""
import logging
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.download import DownloadStatus
from app.schemas.download import DownloadListResponse, DownloadResponse, DownloadUrlResponse
from app.services.uuid_path_param import validate_uuid_path
from app.services.download_service import DownloadService
from app.services.storage_router import get_backend, resolve_signed_url
from app.utils.http import content_disposition

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=DownloadListResponse)
def list_my_downloads(
    limit: int = 50,
    source_entity_type: str | None = None,
    source_entity_id: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadListResponse:
    user_id = str(current_user["id"])
    capped = max(1, min(limit, 200))
    svc = DownloadService(db)
    if source_entity_type and source_entity_id:
        rows = svc.list_for_user_by_source(
            user_id, source_entity_type, source_entity_id, limit=capped
        )
    else:
        rows = svc.list_for_user(user_id, limit=capped)
    return DownloadListResponse(downloads=[DownloadResponse.model_validate(r) for r in rows])


@router.get("/{download_id}/url", response_model=DownloadUrlResponse)
def get_download_url(
    download_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadUrlResponse:
    validate_uuid_path(download_id, resource="Download")
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


@router.get("/{download_id}/file")
def stream_download_file(
    download_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """The bytes themselves, same-origin and authenticated.

    Separate from ``/url`` because a bucket's presigned URL is cross-origin and sends no CORS
    headers: the shared preview modal reads spreadsheet bytes with ``fetch`` and saves files as
    a blob, and both fail against a presigned URL while succeeding here. ``/url`` stays for the
    cases where an element loads the file itself (an ``<iframe>``/``<img>`` cannot send an auth
    header, so it needs the signed URL).

    Scoped to the row's owner, exactly as ``/url`` is - a download id in someone else's hand is
    not a licence to read it.
    """
    validate_uuid_path(download_id, resource="Download")
    row = DownloadService(db).get_for_user(download_id, str(current_user["id"]))
    if row is None:
        raise HTTPException(status_code=404, detail="Download not found")
    if row.status != DownloadStatus.READY.value or not row.storage_key:
        raise HTTPException(status_code=409, detail=f"Download is not ready (status: {row.status})")
    try:
        content = get_backend(row.storage_provider).download_file(row.storage_key)
    except Exception as e:  # noqa: BLE001 - a missing object is not a server bug worth a 500
        logger.warning("stream_download_file: could not read %s: %s", row.storage_key, e)
        raise HTTPException(status_code=404, detail="The stored file is no longer available")

    filename = row.filename or "download"
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Length": str(len(content)),
        },
    )
