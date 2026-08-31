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
from typing import Iterable, Iterator, NamedTuple, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dealer_kit import Asset
from app.models.resources import Attachment
from app.services.company_scope import get_company_scope, resolve_write_company_id
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
FONT = "font"

#: What a library asset can BE. `font` (S3b, D29) is a file the editor and the
#: print page load through `@font-face`; everything else is artwork. Kept as a
#: plain set rather than a lookup table because it is a vocabulary, not data
#: somebody administers.
KINDS = frozenset({DECORATIVE, "badge", "icon", "diagram", "logo", FONT})

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "font/woff2": "woff2",
    "font/ttf": "ttf",
    "font/otf": "otf",
}

#: Which file extensions each kind accepts, and the mime each implies.
#:
#: Validated on the EXTENSION rather than the browser's content type, because a
#: browser sends `application/octet-stream` for a woff2 as often as not - and
#: because the failure this guards is silent: a JPEG accepted as a font reaches
#: the print page as a broken `@font-face`, Chromium falls back to a system font
#: without complaining, and the tag prints in the wrong typeface.
FONT_EXTENSIONS = {"woff2": "font/woff2", "ttf": "font/ttf", "otf": "font/otf"}
IMAGE_EXTENSIONS = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


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
        # An attachment is ``__company_shared__``, so the before_insert auto-stamp
        # SKIPS it and NULL means SHARED - a kit asset uploaded inside one company
        # would be visible from the other through the generic attachment surfaces,
        # even though its ``Asset`` row is correctly owned. Stamping through the
        # same helper the ``Asset`` hook uses keeps the pair in agreement: one
        # active company -> that company; scope ``None`` (the system principal)
        # -> the incumbent, which is what the hook stamps too. ``ambiguous=None``
        # leaves NULL rather than guess, and nothing persists anyway - the
        # ``Asset`` insert below raises ``company_scope_required`` on the spot.
        company_id=resolve_write_company_id(get_company_scope(db), ambiguous=None),
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


def mime_for_upload(filename: str, kind: str) -> str:
    """The mime a library upload is stored under, or a refusal.

    Raises ``ValueError`` naming what WOULD have been accepted: an upload
    rejected with "invalid file" sends the person back to the file picker with
    nothing to change.
    """
    if kind not in KINDS:
        raise ValueError(
            f"Unknown asset kind '{kind}'. Choose one of: "
            + ", ".join(sorted(KINDS))
            + "."
        )

    extension = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""

    if kind == FONT:
        mime = FONT_EXTENSIONS.get(extension)
        if not mime:
            raise ValueError(
                "A font must be a .woff2, .ttf or .otf file."
            )
        return mime

    mime = IMAGE_EXTENSIONS.get(extension)
    if not mime:
        raise ValueError(
            "Artwork must be a .png, .jpg, .webp or .svg file."
        )
    return mime


def list_assets(
    db: Session,
    *,
    kind: Optional[str] = None,
    tag: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 100,
) -> list[tuple[Asset, Attachment]]:
    """The library, narrowed the three ways a picker narrows it.

    Company-scoped by the ordinary ORM filter (``Asset`` is owned), and joined to
    the attachment so a caller can sign every row without a second query per
    thumbnail.
    """
    statement = (
        db.query(Asset, Attachment)
        .join(Attachment, Attachment.id == Asset.attachment_id)
        .filter(Attachment.is_deleted.is_(False))
    )

    if kind:
        statement = statement.filter(Asset.kind == kind)
    if tag:
        statement = statement.filter(Asset.tags.any(tag))
    if query and query.strip():
        statement = statement.filter(Asset.name.ilike(f"%{query.strip()}%"))

    return statement.order_by(Asset.name).limit(limit).all()


def font_assets(db: Session, *, expires_in: int = 3600) -> list[dict]:
    """Every brand font this company can print with, signed.

    ALL of them, not just the ones a document names: a text layer carries a font
    FAMILY, never an asset id, so nothing can tell which fonts a page needs until
    the browser lays the text out. The list is small (a brand has a handful of
    faces), and a missing one is a tag printed in the wrong typeface.
    """
    rows = list_assets(db, kind=FONT, limit=100)

    fonts: list[dict] = []
    for asset, attachment in rows:
        signed = resolve_signed_url(
            attachment.file_path,
            provider=attachment.storage_provider,
            expires_in=expires_in,
            strict=True,
        )
        if not signed:
            continue
        # The family IS the asset name. The inspector lists names, a text layer
        # stores the one that was picked, and `@font-face` declares the same
        # string - so the three cannot disagree about what "ZZT Brand" means.
        fonts.append({"name": asset.name, "family": asset.name, "url": signed})
    return fonts


def tag_sheet_asset_ids(doc: Optional[dict]) -> set[str]:
    """Every library asset a tag sheet or tag template document names.

    The tag-shaped counterpart of ``background_asset_ids``: layers rather than
    section styles. Both an ``image`` layer whose source is an asset and a
    ``badge`` layer count, and an ``image`` layer saved before S3b - which
    carried a bare ``assetId`` - counts too, so a template nobody has reopened
    still prints its artwork.

    A product photo is deliberately NOT here: it is a ``product_attachments``
    row behind the access gate, signed by ``product_images``, not a library
    asset.
    """
    ids: set[str] = set()
    if not doc:
        return ids

    for sheet in doc.get("sheets", []) or []:
        for tag in (sheet or {}).get("tags", []) or []:
            ids |= _layer_asset_ids((tag or {}).get("layers", []) or [])

    # A tag TEMPLATE document is layers all the way down, with no sheets.
    ids |= _layer_asset_ids(doc.get("layers", []) or [])
    return ids


def _layer_asset_ids(layers) -> set[str]:
    ids: set[str] = set()
    for layer in layers or []:
        props = (layer or {}).get("props") or {}
        source = props.get("source")
        if isinstance(source, dict) and source.get("type") == "asset":
            if source.get("assetId"):
                ids.add(source["assetId"])
        elif props.get("assetId"):
            ids.add(props["assetId"])
    return ids


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


def _tag_layer_shapes(value: str) -> Iterator[dict]:
    """The jsonb containment shapes that mean "a tag layer names this asset".

    Two per document shape, because a layer carries its asset id in one of two
    places and both are live: a ``badge`` layer (and an ``image`` layer saved
    before S3b) puts it straight on ``props.assetId``, while an ``image`` layer
    saved since puts it under ``props.source``. Missing either would fail the
    guard OPEN - see the docstring below for why that is the direction that
    costs artwork.
    """
    for holder in ({"assetId": value}, {"source": {"type": "asset", "assetId": value}}):
        # A tag TEMPLATE is layers all the way down; a tag SHEET wraps the same
        # layers in sheets and placed tags.
        yield {"layers": [{"props": holder}]}
        yield {"sheets": [{"tags": [{"layers": [{"props": holder}]}]}]}


def referenced_asset_ids(db: Session, asset_ids: Iterable[str]) -> set[str]:
    """Of these assets, the ones something can still show.

    Four things name an asset:

    * a ``page_version.doc`` binding it as ``style.backgroundAssetId`` - ANY
      version, published, staging or an unlabelled draft. Rollback is a label
      move, so an older version is one click from being what readers see, and
      the reviewer opening a draft in the builder is the person the whole
      seeding slice exists for. "Only the published one counts" would blank both.
    * a ``flyer_reading.reading_json`` still claiming it as a page banner, which
      is what lets a brochure be deleted before its reading without stranding
      the artwork.
    * a ``tag_template.doc`` drawing it as a badge or an image layer. The eight
      starter templates are almost nothing BUT badge layers, so for every badge
      the seed uploads this is the ONLY thing that names it.
    * a ``page_version.doc`` holding a TAG SHEET - the same layers, wrapped in
      ``sheets -> tags``, which the background containment test above cannot see
      because it is a different document shape entirely.

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

    from app.models.dealer_kit import FlyerReadingRecord, PageVersion, TagTemplate

    # Local: ``flyer_reading_service`` imports this module, and the reading's
    # JSON shape belongs to it rather than to the library.
    from app.services.dealer_kit import flyer_reading_service

    referenced: set[str] = set()

    tag_shapes = [shape for value in ids for shape in _tag_layer_shapes(value)]

    # None = every company. See the docstring: scoping this read is what turns
    # a fail-closed guard into a fail-open one. ``TagTemplate`` is scoped, so it
    # needs this as much as the reading does.
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
                    ],
                    *[PageVersion.doc.contains(shape) for shape in tag_shapes],
                )
            )
            .all()
        )
        for (doc,) in docs:
            # Both readers, on every hit: one page_version row is a sectioned
            # page OR a tag sheet, and asking which it is would be a third
            # answer to a question these two already answer.
            referenced |= (background_asset_ids(doc) | tag_sheet_asset_ids(doc)) & ids

        templates = (
            db.query(TagTemplate.doc)
            .filter(or_(*[TagTemplate.doc.contains(shape) for shape in tag_shapes]))
            .all()
        )
        for (doc,) in templates:
            referenced |= tag_sheet_asset_ids(doc) & ids

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
    "FONT",
    "IMAGE_EXTENSIONS",
    "FONT_EXTENSIONS",
    "KINDS",
    "STORAGE_ENTITY_TYPE",
    "StoredObject",
    "background_asset_ids",
    "background_urls",
    "create_from_bytes",
    "delete_unreferenced",
    "font_assets",
    "list_assets",
    "mime_for_upload",
    "tag_sheet_asset_ids",
    "purge_objects",
    "referenced_asset_ids",
    "urls_for",
]
