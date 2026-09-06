"""Font bytes for the print page and the tag editor, served same-origin.

`asset_service` (module docstring) documents the gap this closes: a signed CDN
URL answers 200 with no ``Access-Control-Allow-Origin``, so `FontFace.load()`
rejects it in the browser and both consumers silently fall back to the system
sans. Same-origin has no CORS to satisfy, so this route proxies the bytes
instead of handing back a link to them - `media_proxy_service` documents the
same host behaviour for the chat preview, and is the precedent for it.

No auth: an asset id is a UUID nobody can enumerate, and a font is brand
artwork the page already renders unauthenticated (see `print.py`). Only a
``kind='font'`` row answers - any other kind, or an id that does not exist, is
a 404, so this cannot be used to read a brand's other artwork.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.dealer_kit import Asset
from app.models.resources import Attachment
from app.services.dealer_kit.asset_service import FONT
from app.services.error_handler import AppException
from app.services.storage_router import extract_key, get_backend
from app.services.uuid_path_param import validate_uuid_path
from app.utils.http import content_disposition

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{asset_id}")
def read_font_bytes(asset_id: str, db: Session = Depends(get_db)) -> Response:
    asset_id = validate_uuid_path(asset_id, resource="Font")

    # An unauthenticated caller has no company scope, so the ordinary owned
    # read would see nothing. The lookup itself is the only thing gating this
    # route - it can only ever answer a `kind='font'` row - so reading across
    # every company here costs nothing a scoped read would have refused.
    with company_scope(db, None):
        row = (
            db.query(Asset, Attachment)
            .join(Attachment, Attachment.id == Asset.attachment_id)
            .filter(Asset.id == asset_id, Asset.kind == FONT)
            .filter(Attachment.is_deleted.is_(False))
            .first()
        )
    if row is None:
        raise AppException(status_code=404, message="Not found")
    asset, attachment = row

    key = extract_key(attachment.file_path)
    try:
        if not key:
            raise ValueError(f"Not a storage-backed file_path: {attachment.file_path!r}")
        content = get_backend(attachment.storage_provider).download_file(key)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - mirrors portal_download_price_tag_pdf
        logger.warning("read_font_bytes: could not read %s", attachment.file_path, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Font download failed. Please try again.",
        ) from e

    filename = attachment.original_filename or asset.name
    return Response(
        content=content,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=86400",
            # Bytes somebody uploaded, served unauthenticated under our own
            # origin: the browser must take the declared type or nothing.
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": content_disposition(filename, inline=True),
        },
    )
