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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import Asset
from app.models.resources import Attachment
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
def upload_asset(
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

    Plain ``def``, not ``async def`` (AC-J3): a library asset is a badge, icon
    or font, not a 20 MB flyer, so there is no byte-by-byte size ceiling to
    enforce while the upload streams in - the whole body, read + MIME sniff +
    the storage PUT + the INSERT, is synchronous work, and FastAPI threadpools
    a plain ``def`` route automatically. ``file.file.read()`` reads the
    underlying ``SpooledTemporaryFile`` synchronously; ``await file.read()``
    would need an event loop this handler no longer runs on.
    """
    content = file.file.read()
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


class _RenameAssetRequest(BaseModel):
    name: str


@router.patch("/{asset_id}", response_model=AssetResponse)
def rename_asset(
    asset_id: str,
    body: _RenameAssetRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Rename a library asset.

    A font is named by FAMILY, not by id (see ``asset_service``'s "Brand
    fonts" section), so renaming one also rewrites every text layer that
    named the old family, in the same transaction. Any other kind carries its
    id in the document and only the row changes (AC-D3, AC-12).
    """
    new_name = (body.name or "").strip()
    if not new_name:
        raise AppException(
            status_code=422, message="Name cannot be empty.", code="VALIDATION_ERROR"
        )
    if len(new_name) > 200:
        # Rejected rather than silently sliced: a truncated row next to docs
        # rewritten with the FULL name would leave the row and the layers
        # disagreeing about the family's own name.
        raise AppException(
            status_code=422,
            message="Name must be 200 characters or fewer.",
            code="VALIDATION_ERROR",
        )

    row = (
        db.query(Asset, Attachment)
        .join(Attachment, Attachment.id == Asset.attachment_id)
        .filter(Asset.id == asset_id, Attachment.is_deleted.is_(False))
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404,
            message="Asset not found. Someone might have deleted it already.",
            code="ASSET_NOT_FOUND",
        )
    asset, attachment = row

    if asset.kind == asset_service.FONT and new_name != asset.name:
        # Two `@font-face` rules for one family would be ambiguous - and the
        # inspector's dropdown lists a font by name, so two rows sharing one
        # would be indistinguishable there too.
        taken = (
            db.query(Asset)
            .filter(
                Asset.kind == asset_service.FONT,
                Asset.name == new_name,
                Asset.id != asset_id,
            )
            .first()
        )
        if taken:
            raise AppException(
                status_code=409,
                message=f'"{new_name}" is already the name of another brand font.',
                code="FONT_NAME_TAKEN",
            )
        asset_service.rename_font_family(db, asset.name, new_name, asset.company_id)

    asset.name = new_name
    db.commit()
    db.refresh(asset)

    urls = asset_service.urls_for(db, [asset.id])
    return _serialize(asset, attachment, urls)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Delete a library asset. Refused while anything still names it (AC-9/10/12)."""
    asset_service.delete_asset_guarded(db, asset_id)
