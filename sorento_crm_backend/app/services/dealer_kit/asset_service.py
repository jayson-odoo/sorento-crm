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

**An asset dies when the last thing that names it dies.** The library also owns
that rule, and owns it ALONE, because every deleter needs the same answer to
"is anything still showing this" and two implementations of it would drift the
first time a document changed shape. See ``referenced_asset_ids``.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Iterable, NamedTuple, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dealer_kit import Asset
from app.models.resources import Attachment
from app.services.image_thumbnailer import store_thumbnail, thumbnail_key_for
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    delete_object_best_effort,
    extract_key,
    get_backend,
    normalize_provider,
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

    # From here on the bytes are already in the bucket, and a rollback cannot
    # reach them. A caller's savepoint undoes the ROWS; the objects would stay
    # forever, which is exactly the orphan family the "Death" note above exists
    # to close. So this function owns what it uploaded until the rows are
    # safely flushed, and sweeps on the way out if they are not.
    #
    # Reachable, not theoretical: a company-scope refusal on the insert, or any
    # constraint on `attachments` - migration 317 shipped one that fired.
    uploaded: list[str] = [stored_key]
    try:
        return _persist_asset(
            db,
            backend=backend,
            provider=provider,
            uploaded=uploaded,
            attachment_id=attachment_id,
            filename=filename,
            stored_key=stored_key,
            name=name,
            mime=mime,
            kind=kind,
            tags=tags,
            content=content,
            user_id=user_id,
        )
    except Exception:
        for orphan in uploaded:
            delete_object_best_effort(provider, orphan)
        raise


def _persist_asset(
    db: Session,
    *,
    backend,
    provider: str,
    uploaded: list[str],
    attachment_id: str,
    filename: str,
    stored_key: str,
    name: str,
    mime: str,
    kind: str,
    tags: Optional[list[str]],
    content: bytes,
    user_id: Optional[str],
) -> Asset:
    """The row half of ``create_from_bytes``, split out so its caller can sweep.

    ``uploaded`` is appended to as objects are written, so the caller's handler
    knows what to remove. The thumbnail is the second one and is written here.
    """
    # store_thumbnail returns a CDN URL, not a key, so the key is derived the
    # same way it derives it. Deleting the URL would silently remove nothing.
    thumbnail = store_thumbnail(backend, provider, stored_key, content, mime)
    if thumbnail:
        uploaded.append(thumbnail_key_for(stored_key))

    attachment = Attachment(
        id=attachment_id,
        original_filename=filename,
        stored_filename=name[:255],
        file_path=cdn_base_url(provider, stored_key),
        # Best-effort, and never fatal: a library grid that has to paint the
        # full-resolution banner is slow, not wrong.
        thumbnail_path=thumbnail,
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


# --------------------------------------------------------------------------- #
# Death
#
# Everything above puts artwork INTO the library. Nothing used to take it out,
# and the bill for that was 1,356 objects in a live bucket with no row anywhere
# pointing at them: a flyer reading created an asset per page banner, and
# deleting the reading deleted only the reading. They could not be tidied up
# afterwards either - ``asset.attachment_id`` is ON DELETE RESTRICT, so the
# attachment refused to go while the asset row lived, and nothing deleted the
# asset.
#
# The obvious fix is the wrong one. A banner is a section BACKGROUND in every
# brochure seeded from that reading, and a reading is a working artefact people
# tidy away, so a cascade would blank the artwork on a published catalogue
# somebody approved. A reader losing a background they can currently see is far
# worse than an orphan row.
#
# So the rule is neither "always" nor "never": an asset dies when the LAST thing
# that names it dies. That also makes the order irrelevant - delete the brochure
# then the reading, or the reading then the brochure, and whichever goes last
# takes the artwork with it.
# --------------------------------------------------------------------------- #
class StoredObject(NamedTuple):
    """One object in storage, and which provider holds it.

    The provider travels WITH the key because it is read off the attachment row,
    and by the time the bytes are purged that row is gone. Falling back to
    ``STORAGE_DEFAULT_PROVIDER`` at purge time would delete from the wrong
    bucket during the S3-to-R2 transition, which is a silent no-op on one side
    and a live object left behind on the other.
    """

    provider: str
    key: str


def referenced_asset_ids(db: Session, asset_ids: Iterable[str]) -> set[str]:
    """Of these assets, the ones something can still show.

    Two things name an asset:

    * a ``page_version.doc`` binding it as ``style.backgroundAssetId`` - ANY
      version, published, staging or an unlabelled draft. Rollback is a label
      move, so an older version is one click from being what readers see, and
      the reviewer opening a draft in the builder is the person the whole
      seeding slice exists for. "Only the published one counts" would blank both.
    * a ``flyer_reading.reading_json`` still claiming it as a page banner, which
      is what lets a brochure be deleted before its reading without stranding
      the artwork.

    A jsonb containment test per candidate, OR'd into ONE statement, so the
    database hands back only documents that really name one of them; which ids
    those are is then decided by the same helpers that read a background out of
    a document and a banner out of a reading. Two definitions of "a background
    binding" would disagree the first time the document shape moved.

    Both reads run under an ALL-COMPANIES scope, and that is load-bearing
    rather than tidy. This is the guard that decides whether something is safe
    to destroy, so it has to fail closed - but the company filter makes it fail
    OPEN. ``do_orm_execute`` injects a company predicate into every SELECT on a
    ``CompanyScopedMixin`` model, and ``FlyerReadingRecord`` is one, so under an
    UNSET or empty scope the predicate is ``false()``: the guard sees no
    references, concludes the asset is unreferenced, and the caller deletes
    artwork somebody is looking at. "No rows visible" and "nothing references
    it" are the same answer to this function and opposite answers to the
    caller.

    That is reachable: ``worker.py`` registers the scope listeners, so anything
    running off a queue or a script starts UNSET. ``PageVersion`` is not scoped
    and was never affected, which is why the published-brochure half of this
    guard held while the reading half quietly did not.
    """
    from app.models.base import company_scope

    ids = {value for value in asset_ids if value}
    if not ids:
        return set()

    from app.models.dealer_kit import FlyerReadingRecord, PageVersion

    # Local: ``flyer_reading_service`` imports this module, and the reading's
    # JSON shape belongs to it rather than to the library.
    from app.services.dealer_kit import flyer_reading_service

    referenced: set[str] = set()

    # None = every company. See the docstring: scoping this read is what turns
    # a fail-closed guard into a fail-open one.
    with company_scope(db, None):
        docs = (
            db.query(PageVersion.doc)
            .filter(
                or_(
                    *[
                        PageVersion.doc.contains(
                            {"sections": [{"style": {"backgroundAssetId": value}}]}
                        )
                        for value in ids
                    ]
                )
            )
            .all()
        )
        for (doc,) in docs:
            referenced |= background_asset_ids(doc) & ids

        readings = (
            db.query(FlyerReadingRecord.reading_json)
            .filter(
                or_(
                    *[
                        FlyerReadingRecord.reading_json.contains(
                            {"pages": [{"banner_asset_id": value}]}
                        )
                        for value in ids
                    ]
                )
            )
            .all()
        )
    for (payload,) in readings:
        referenced |= flyer_reading_service.banner_asset_ids(payload) & ids

    return referenced


def delete_unreferenced(db: Session, asset_ids: Iterable[str]) -> list[StoredObject]:
    """Delete the rows for every one of these assets nothing names any more.

    ROWS only, inside the caller's transaction, exactly as ``create_from_bytes``
    writes without committing. The bytes come back as a list for the caller to
    purge AFTER its commit - see ``purge_objects`` - because a delete that
    removed the object first and then failed to commit would leave a live asset
    row pointing at nothing.

    The asset row is deleted BEFORE its attachment, with a flush between them,
    and that is the entire reason this has to be a function rather than two
    ``db.delete`` calls at each call site: ``asset.attachment_id`` is ON DELETE
    RESTRICT, so the other order is an IntegrityError and a 500 for a delete
    that was perfectly legal. The constraint is right - an attachment vanishing
    under a live asset would leave a library row pointing at nothing - so the
    order is what adapts to it.
    """
    ids = {value for value in asset_ids if value}
    if not ids:
        return []

    doomed = ids - referenced_asset_ids(db, ids)
    if not doomed:
        return []

    rows = (
        db.query(Asset, Attachment)
        .join(Attachment, Attachment.id == Asset.attachment_id)
        .filter(Asset.id.in_(doomed))
        .all()
    )

    objects: list[StoredObject] = []
    attachments: list[Attachment] = []
    for asset, attachment in rows:
        provider = normalize_provider(attachment.storage_provider)
        # The thumbnail is a SEPARATE object with its own key. Half the bucket
        # litter was thumbnails, so forgetting it here would fix the defect by
        # half and look complete.
        for path in (attachment.file_path, attachment.thumbnail_path):
            key = extract_key(path)
            if key:
                objects.append(StoredObject(provider, key))
        db.delete(asset)
        attachments.append(attachment)

    db.flush()
    for attachment in attachments:
        db.delete(attachment)
    db.flush()

    return objects


def purge_objects(objects: Iterable[StoredObject]) -> None:
    """Remove the bytes. Called AFTER the caller commits, never before.

    Deleting them is the right answer even though it cannot be undone. Once the
    asset row is gone the object is unreachable by every path this product has -
    nothing can list it, sign it or delete it - so keeping it buys no recovery,
    only storage cost and a bucket nobody can audit. A missing object under a
    LIVE row is the state worth avoiding, and that is what the ordering here is
    for.

    Best-effort per object: a bucket that is unreachable costs an orphan, never
    the delete the user asked for. They would otherwise be handed a row they
    cannot remove, for a reason nothing on their screen could explain, and the
    retry would hit the same wall.
    """
    for stored in objects:
        delete_object_best_effort(stored.provider, stored.key)


__all__ = [
    "DECORATIVE",
    "STORAGE_ENTITY_TYPE",
    "StoredObject",
    "background_asset_ids",
    "background_urls",
    "create_from_bytes",
    "delete_unreferenced",
    "purge_objects",
    "referenced_asset_ids",
    "urls_for",
]
