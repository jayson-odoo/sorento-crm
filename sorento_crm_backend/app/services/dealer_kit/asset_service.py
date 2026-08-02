"""The Kit's artwork library: naming and finding a file it did not store itself.

``dealer_kit.asset`` adds LIBRARY semantics - a name, a kind, tags - on top of a
row in ``public.attachments``. The bytes stay where every other file in this
system keeps them and travel through ``storage_router``, so the provider column,
the S3-to-R2 migration and the signing path all apply here unchanged. The Kit
does not grow a second file store, and an asset id in a page document survives
the file being renamed (AC-D3).

**Signing is STRICT.** ``resolve_signed_url`` fails open by default, which is the
right answer for a download link and the wrong one for a picture: the browser
requests the unsigned URL, the CDN answers 403, and the reader gets a broken
image where the section already has a perfectly good plain background. So an
unsignable asset is simply ABSENT from the map, and the renderer treats an
absent background as no background. Not hypothetical - 181 of 2,472 product
image links could not be signed on one environment.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import Asset
from app.models.resources import Attachment
from app.services.image_thumbnailer import store_thumbnail
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    get_backend,
    resolve_signed_url,
    sanitize_storage_filename,
)

logger = logging.getLogger(__name__)

# Storage prefix. Matches the uuid-segregated key scheme the attachment upload
# uses ("{type}/{attachment_id}/{filename}"), so two assets with the same name
# can never share an object.
STORAGE_ENTITY_TYPE = "dealer_kit_asset"

DECORATIVE = "decorative"

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def create_from_bytes(
    db: Session,
    *,
    content: bytes,
    name: str,
    mime: str,
    kind: str = DECORATIVE,
    tags: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> Asset:
    """Put bytes in storage and give them a place in the library.

    Writes and FLUSHES, never commits. The invariant worth protecting is that an
    attachment row cannot exist without the asset row that makes it reachable,
    and both are written here in one flush, so the caller's commit gives that
    just as well as a commit taken here would. What a commit taken HERE also
    does is decide the fate of everything else the caller happened to have
    pending, which is not a decision a library helper gets to make: this is
    called from the middle of reading a flyer, page by page, and a caller that
    is 12 pages into building a reading has no way to say "commit the asset but
    not that".

    Raises if the upload fails, so the CALLER decides whether a missing piece of
    artwork is fatal. For a flyer upload it is not - see ``_store_banners``,
    which wraps each attempt in a SAVEPOINT for exactly that reason.
    """
    attachment_id = str(uuid.uuid4())
    filename = _filename(name, mime)
    key = f"{STORAGE_ENTITY_TYPE}/{attachment_id}/{filename}"

    provider = default_provider()
    backend = get_backend(provider)
    stored_key, _url = backend.upload_file(
        file_content=content, file_path=key, content_type=mime
    )

    attachment = Attachment(
        id=attachment_id,
        original_filename=filename,
        stored_filename=name[:255],
        file_path=cdn_base_url(provider, stored_key),
        # Best-effort, and never fatal: a library grid that has to paint the
        # full-resolution banner is slow, not wrong.
        thumbnail_path=store_thumbnail(backend, provider, stored_key, content, mime),
        file_size_bytes=len(content),
        mime_type=mime,
        file_hash=hashlib.sha256(content).hexdigest(),
        entity_type=STORAGE_ENTITY_TYPE,
        uploaded_by=user_id,
        uploader_kind="user" if user_id else "system",
        storage_provider=provider,
    )
    db.add(attachment)
    db.flush()

    asset = Asset(
        attachment_id=attachment.id,
        name=name[:200],
        kind=kind,
        tags=tags or None,
        created_by=user_id,
    )
    db.add(asset)
    db.flush()
    return asset


def urls_for(
    db: Session, asset_ids: Iterable[str], *, expires_in: int = 3600
) -> dict[str, str]:
    """``{asset_id: signed url}``, omitting any that cannot be signed.

    Absent rather than blank, for the same reason a tile with no permitted photo
    is absent from ``primary_image_urls``: the surface has a designed state for
    "no picture" and none at all for "a picture that 403s".
    """
    ids = {value for value in asset_ids if value}
    if not ids:
        return {}

    rows = (
        db.query(Asset, Attachment)
        .join(Attachment, Attachment.id == Asset.attachment_id)
        .filter(Asset.id.in_(ids))
        .filter(Attachment.is_deleted.is_(False))
        .all()
    )

    urls: dict[str, str] = {}
    for asset, attachment in rows:
        signed = resolve_signed_url(
            attachment.file_path,
            provider=attachment.storage_provider,
            expires_in=expires_in,
            strict=True,
        )
        if signed:
            urls[asset.id] = signed
    return urls


def background_asset_ids(doc: Optional[dict]) -> set[str]:
    """Every asset a document uses as a section background.

    Read off the document rather than tracked on the page, so a designer
    swapping a background in the editor cannot leave a stale list behind.
    """
    return {
        (section.get("style") or {}).get("backgroundAssetId")
        for section in (doc or {}).get("sections", []) or []
        if (section.get("style") or {}).get("backgroundAssetId")
    }


def background_urls(db: Session, doc: Optional[dict]) -> dict[str, str]:
    """The one call a render payload needs: document in, ``{assetId: url}`` out."""
    return urls_for(db, background_asset_ids(doc))


def _filename(name: str, mime: str) -> str:
    extension = _EXTENSIONS.get((mime or "").lower(), "bin")
    stem = sanitize_storage_filename(name).rstrip(".") or "asset"
    return f"{stem}.{extension}"


__all__ = [
    "DECORATIVE",
    "STORAGE_ENTITY_TYPE",
    "background_asset_ids",
    "background_urls",
    "create_from_bytes",
    "urls_for",
]
