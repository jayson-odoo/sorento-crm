"""The Kit's artwork library over HTTP: list and upload.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Until S3b the library was write-only from one direction - the flyer reader put
banners in it and nothing else could see or add. The tag canvas needs both
halves: a designer picks a badge from it and uploads a new one without leaving
the editor, and uploads the brand's font the same way (D29).

Gated on ``dealer_kit.library.manage``, the permission whose description is
literally "Manage assets, tile templates and reusable collections". Reading the
library is part of managing it, every role that designs a tag already holds it,
and reusing it means no new permission and therefore no grant sweep.

The bytes go through ``asset_service``, which is the same path a flyer banner
takes: one file store, one storage router, one signing rule.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.price_tag import AssetResponse
from app.services.dealer_kit import asset_service
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["dealer-kit-assets"])

_VIEW = require_permission_with_api_key("dealer_kit.library.manage")
_MANAGE = require_permission("dealer_kit.library.manage")

#: A tag's artwork is printed at 300dpi, so the ceiling is generous - but not
#: unbounded: the upload is read into memory before it reaches the bucket.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _user_id(user: dict) -> Optional[str]:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _serialize(asset, attachment, urls: dict) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        name=asset.name,
        kind=asset.kind,
        tags=list(asset.tags or []),
        url=urls.get(asset.id),
        mime_type=attachment.mime_type,
    )


@router.get("", response_model=list[AssetResponse])
def list_assets(
    kind: Optional[str] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The library, filtered by kind, tag or name."""
    rows = asset_service.list_assets(db, kind=kind, tag=tag, query=q, limit=limit)
    urls = asset_service.urls_for(db, [asset.id for asset, _ in rows])
    return [_serialize(asset, attachment, urls) for asset, attachment in rows]


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form(asset_service.DECORATIVE),
    name: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    """Put a file in the library and name it.

    ``tags`` is a comma-separated list, which is what a multipart form can carry
    without inventing an encoding.
    """
    content = await file.read()
    if not content:
        raise AppException(
            status_code=422, message="The uploaded file is empty.", code="EMPTY_FILE"
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise AppException(
            status_code=422,
            message=f"Files must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            code="FILE_TOO_LARGE",
        )

    try:
        mime = asset_service.mime_for_upload(file.filename or "", kind)
    except ValueError as exc:
        raise AppException(status_code=422, message=str(exc), code="UNSUPPORTED_FILE")

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    display_name = (name or "").strip() or (file.filename or "Asset").rsplit(".", 1)[0]

    asset = asset_service.create_from_bytes(
        db,
        content=content,
        name=display_name,
        mime=mime,
        kind=kind,
        tags=tag_list or None,
        user_id=_user_id(user),
    )
    db.commit()
    db.refresh(asset)

    urls = asset_service.urls_for(db, [asset.id])
    from app.models.resources import Attachment

    attachment = db.query(Attachment).filter(Attachment.id == asset.attachment_id).first()
    return _serialize(asset, attachment, urls)
