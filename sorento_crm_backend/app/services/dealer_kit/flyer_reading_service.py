"""Keeping a flyer reading, and deriving its report on demand (S7.3).

``flyer_extraction`` reads the paper. ``flyer_matching`` says what the paper
means against the master. This module is what sits between them and a designer:
it stores what was read, and rebuilds the report every time somebody asks.

**The reading is stored. The report is not, and must not be.**

A report is only true for the product master and the promotion it was computed
against, and both move every day. A report written at upload time is wrong the
first time somebody creates one of the products it listed as missing, and wrong
in the direction that costs money: it tells marketing to close gaps that are
already closed, and a reviewer has no way to see that the answer is stale.
Recomputing costs 0.4s against the real flyer's 998 codes - three statements,
not 998 - which buys an answer that is true at the moment it is read. If that
ever stops being cheap, the fix is a cache with an explicit invalidation on
product and promotion writes, NOT a column.

**Extraction runs inside the request, off the event loop.** Measured, not
estimated: the real ``_SORENTO A3 FLYER 2025-2026_compressed.pdf`` (20.1 MB, 36
A3 pages, 998 codes) takes **17 to 18 seconds** in ``extract_flyer`` on a quiet
machine, and 40 to 60 seconds end to end through the route on a loaded one.
Profiled, 72 percent of that is PyMuPDF's ``get_text("dict")`` and 22 percent its
``get_image_info``, both native - so there is no algorithmic win hiding in our
own code, and under 7 percent of the time is even ours to optimise.

This docstring used to say "about a second", and named ten seconds as the point
where a queue wins. By its own criterion the argument had already lapsed. The
number now written here is the one that was measured, with the document it was
measured against, so the next person decides on evidence.

What was actually wrong was not the duration but WHERE it ran: the upload route
was ``async def``, so all of it happened on the event loop and one read served
nothing else from that worker for its whole duration (a ``GET /health`` probe
waited 57.5 seconds on a single worker). The route now hands this function to a
threadpool. Callers of ``create_reading`` are therefore expected to be off the
loop already - a plain ``def`` route, a threadpool, or a worker.

The queue is still the end state and is deliberately not built yet: it costs a
pending row, a polling screen, a failure path and a worker restart per change to
this module. Re-take that decision when artwork rasterisation lands.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import FlyerReadingRecord
from app.services.dealer_kit import asset_service
from app.services.dealer_kit.flyer_extraction import (
    UNCROPPED,
    EncryptedFlyerError,
    FlyerArtwork,
    FlyerCard,
    FlyerGrid,
    FlyerPage,
    FlyerReading,
    extract_flyer,
)
from app.services.dealer_kit.flyer_matching import MatchReport, match_reading
from app.services.error_handler import AppException, handle_not_found

logger = logging.getLogger(__name__)

# The ceiling on an uploaded flyer.
#
# The real _SORENTO A3 FLYER 2025-2026_ is 20 MB compressed. A designer
# exporting the same 36 A3 pages without compression can comfortably double
# that, so the limit has to clear 40 MB or it refuses the very document this
# feature exists for. 50 MB also stays inside what one request can hold in
# memory and extract synchronously; past it, the queue argument in the module
# docstring starts winning.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# What the stored JSON is shaped like. Bumped if the extractor's dataclasses
# change shape, so an old row is recognisably old rather than silently misread.
READING_FORMAT_VERSION = 1

# What a stored attachment may claim to be and still be handed to the extractor.
# ``application/pdf`` is what every real upload path records; the rest are the
# spellings other systems emit for the same thing.
PDF_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/x-pdf",
        "application/acrobat",
        "applications/vnd.pdf",
        "text/pdf",
        "text/x-pdf",
    }
)

# Mime types that say "we did not know", not "this is not a PDF". A row carrying
# one of these is let through to the extractor rather than refused on metadata.
_UNKNOWN_MIME_TYPES = frozenset({"application/octet-stream", "binary/octet-stream"})


def assert_within_limit(byte_size: int) -> None:
    """413 for anything over the ceiling, naming the ceiling.

    Called as the upload is read rather than after it, so an oversized file is
    refused without first being held whole in memory.

    The limit is stated in the message on purpose: "file too large" leaves a
    designer guessing what smaller means, and they will guess by uploading again.
    """
    if byte_size > MAX_UPLOAD_BYTES:
        raise AppException(
            status_code=413,
            message=(
                f"That flyer is larger than the {_megabytes(MAX_UPLOAD_BYTES)} MB limit. "
                "Export it at a lower image quality and upload it again."
            ),
            code="FLYER_TOO_LARGE",
        )


def _megabytes(value: int) -> str:
    return f"{value / (1024 * 1024):.2f}".rstrip("0").rstrip(".")


def _not_a_pdf(reason: str) -> AppException:
    """The one 400 for "this is not a flyer", wherever it was noticed.

    Built here rather than written out at each site so both sources say the same
    words for the same failure. A designer who picks the wrong file from the
    library and a designer who uploads it get one message to recognise, and the
    FE has one code to key on.
    """
    return AppException(
        status_code=400,
        message=(
            f"That file could not be read as a PDF ({reason}). "
            "Upload the flyer as a PDF export rather than a Word or image file."
        ),
        code="FLYER_NOT_A_PDF",
    )


def assert_pdf_mime(mime_type: Optional[str]) -> None:
    """Refuse a stored file the library ALREADY says is not a PDF.

    Only reachable from the from-attachment path, where the type is known before
    a single byte is fetched. An upload has no equivalent: its declared content
    type is the browser's guess about a file we are holding anyway, so the
    extractor stays the only judge there.

    Refuses on positive evidence only. A row with no recorded mime, or the
    generic ``application/octet-stream`` that a bulk import leaves behind, is
    "we do not know" rather than "this is a spreadsheet" - those go to the
    extractor, which reaches the same 400 with the same code if it is right.
    Refusing them here would make a perfectly readable flyer unpickable on the
    strength of a metadata gap.
    """
    recorded = (mime_type or "").split(";")[0].strip().lower()
    if not recorded or recorded in _UNKNOWN_MIME_TYPES or recorded in PDF_MIME_TYPES:
        return
    raise _not_a_pdf(f"it is filed as {recorded}")


# --------------------------------------------------------------------------- #
# Serialising a reading
#
# The WHOLE reading is kept, not just its codes. Matching needs the codes alone,
# but the seeder that follows (S7.4) builds one collection per printed ROW and
# one section per page heading, and S7.5 places the artwork - so a serialiser
# that kept only what today's report reads would seed a catalogue with no layout
# at all, and every test in this slice would still pass.
# --------------------------------------------------------------------------- #
def serialise(reading: FlyerReading) -> dict:
    return {
        "version": READING_FORMAT_VERSION,
        "pages": [_page_json(page) for page in reading.pages],
    }


def _page_json(page: FlyerPage) -> dict:
    return {
        "number": page.number,
        "width": page.width,
        "height": page.height,
        "heading": page.heading,
        # Where the page's banner ended up in the asset library, and how a
        # section should lay it out. The BYTES are never in here: they went to
        # storage, and a document binds an id so renaming the file cannot break
        # a published page (AC-D3).
        "banner_asset_id": page.banner_asset_id,
        "banner_fit": page.banner_fit,
        "cards": [_card_json(card) for card in page.cards],
        # Rows reference their cards by code rather than repeating them. A code
        # is unique within a page (the extractor dedupes), and one copy of a card
        # cannot drift out of step with another.
        "grids": [
            {"y": grid.y, "codes": [card.code for card in grid.cards]}
            for grid in page.grids
        ],
        "artwork": [
            {
                "x_pct": art.x_pct,
                "y_pct": art.y_pct,
                "width_pct": art.width_pct,
                "height_pct": art.height_pct,
                "xref": art.xref,
                # Which part of the source image was on the page. Kept so the
                # reading says what was cut and why, rather than only what
                # survived.
                "crop": list(art.crop),
            }
            for art in page.artwork
        ],
    }


def _card_json(card: FlyerCard) -> dict:
    return {
        "code": card.code,
        "lines": list(card.lines),
        "x": card.x,
        "y": card.y,
        "list_price": card.list_price,
        "offer_price": card.offer_price,
        "length_mm": card.length_mm,
        "width_mm": card.width_mm,
        "height_mm": card.height_mm,
    }


def deserialise(payload: dict) -> FlyerReading:
    """Rebuild the reading the extractor produced.

    Lossless by construction, and pinned by a round trip test: what is rebuilt
    here is what the seeder will build a catalogue from, so a dropped field is a
    catalogue missing a row rather than a visible error.
    """
    reading = FlyerReading()
    for entry in (payload or {}).get("pages", []):
        cards = [_card_of(raw) for raw in entry.get("cards", [])]
        by_code = {card.code: card for card in cards}

        page = FlyerPage(
            number=entry["number"],
            width=entry["width"],
            height=entry["height"],
            heading=entry.get("heading"),
            banner_asset_id=entry.get("banner_asset_id"),
            banner_fit=entry.get("banner_fit"),
        )
        page.cards = cards
        page.grids = [
            FlyerGrid(
                cards=[by_code[code] for code in raw.get("codes", []) if code in by_code],
                y=raw["y"],
            )
            for raw in entry.get("grids", [])
        ]
        page.artwork = [
            FlyerArtwork(
                x_pct=raw["x_pct"],
                y_pct=raw["y_pct"],
                width_pct=raw["width_pct"],
                height_pct=raw["height_pct"],
                xref=raw["xref"],
                # Rows written before S7.5 have no crop, and "the whole image"
                # is what they meant.
                crop=tuple(raw.get("crop") or UNCROPPED),  # type: ignore[arg-type]
            )
            for raw in entry.get("artwork", [])
        ]
        reading.pages.append(page)
    return reading


def _card_of(raw: dict) -> FlyerCard:
    return FlyerCard(
        code=raw["code"],
        lines=list(raw.get("lines", [])),
        x=raw["x"],
        y=raw["y"],
        list_price=raw.get("list_price"),
        offer_price=raw.get("offer_price"),
        length_mm=raw.get("length_mm"),
        width_mm=raw.get("width_mm"),
        height_mm=raw.get("height_mm"),
    )


def to_reading(record: FlyerReadingRecord) -> FlyerReading:
    return deserialise(record.reading_json or {})


def page_count(record: FlyerReadingRecord) -> int:
    """Read straight off the JSON rather than through ``deserialise``.

    The list screen shows this for every row, and rebuilding a 998 card reading
    per row to count its pages is work nobody asked for.
    """
    return len((record.reading_json or {}).get("pages", []))


def banner_asset_ids(payload: Optional[dict]) -> set[str]:
    """Every asset a stored reading claims as a page banner.

    Read straight off the JSON rather than through ``deserialise``: this is
    asked while deciding what a delete may destroy, and rebuilding a 998 card
    reading to find two uuids would be work in the one place that must not be
    slow or clever. It is the reading's half of "is anything still naming this
    asset" - see ``asset_service.referenced_asset_ids``.
    """
    return {
        page["banner_asset_id"]
        for page in (payload or {}).get("pages", []) or []
        if page.get("banner_asset_id")
    }


def code_count(record: FlyerReadingRecord) -> int:
    codes = {
        card["code"]
        for page in (record.reading_json or {}).get("pages", [])
        for card in page.get("cards", [])
    }
    return len(codes)


def headings(record: FlyerReadingRecord) -> list[tuple[int, Optional[str]]]:
    """``(page number, heading)`` for EVERY page, in printed order.

    Straight off the JSON for the same reason as ``page_count``: this asks two
    fields of each page and rebuilding the cards to reach them is work nobody
    asked for.

    Every page is listed, including the ones with no heading. A reviewer works
    down this list with the flyer in front of them, so a page that silently
    dropped out would be a page they never compared - and a three page flyer
    reporting two headings reads as a merge rather than a gap.

    Printed order for the same reason: an arbitrary order turns "check these
    against the paper" into a search. The extractor emits pages in order and
    ``serialise`` preserves it, so this is a read rather than a sort - sorting
    here would hide a reading whose page order had gone wrong upstream.
    """
    return [
        (page["number"], page.get("heading"))
        for page in (record.reading_json or {}).get("pages", []) or []
    ]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def create_reading(
    db: Session,
    *,
    filename: Optional[str],
    data: bytes,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Read a flyer's bytes and keep what they say.

    Both sources end here, and that is deliberate: the upload and the
    from-attachment route differ only in where the bytes came from, so a reading
    made either way is the same row, with the same banners in the library and the
    same report. Anything either source needs to do on its own belongs BEFORE
    this call, never inside it.

    ``extract_flyer`` raises ``ValueError`` for anything that is not a readable
    PDF, and that becomes a 400 in words. The alternatives are both worse: a 500
    tells a designer the system is broken when their file is, and a 201 carrying
    an empty report tells them their flyer has no products on it.

    A LOCKED PDF gets its own message. Print-ready artwork comes back from an
    agency password protected far more often than it comes back corrupt, and it
    is fixable in a minute by the person holding it - but only if they are told
    that is the problem. Handed the generic advice, they re-export the same
    locked file and upload it again.
    """
    try:
        # WITH the artwork this time. The upload is the one moment the PDF's
        # bytes exist in this process - the reading deliberately keeps the
        # structure and not the file - so if the banners are not lifted out
        # here, nothing later can lift them out at all.
        reading = extract_flyer(data, with_artwork_images=True)
    except EncryptedFlyerError as exc:
        raise AppException(
            status_code=400,
            message=(
                "That PDF is password protected, so its contents cannot be read. "
                "Save an unprotected copy and upload that."
            ),
            code="FLYER_PASSWORD_PROTECTED",
        ) from exc
    except ValueError as exc:
        raise _not_a_pdf(str(exc)) from exc

    # Before the record, and inside the SAME transaction: the ids the banners
    # come back with are serialised INTO ``reading_json`` below, so an asset
    # committed without its reading would be a library row nothing points at.
    _store_banners(db, reading, filename=filename, user_id=user_id)

    record = FlyerReadingRecord(
        filename=(filename or "flyer.pdf")[:255],
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        reading_json=serialise(reading),
        created_by=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_reading_from_attachment(
    db: Session,
    *,
    attachment_id: str,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Read a flyer the file library is already holding.

    Marketing files the season's flyer in Resource Management as a matter of
    course, long before anybody thinks about the Kit, so without this the
    designer downloads a 20 MB PDF out of the CRM and uploads it straight back
    in. Nothing is asked for except which file: the name, the size and the type
    are all already known.

    **The order of these steps is the design.**

    1. Load the row through the ordinary ORM path, so the global company-scope
       listener does the filtering rather than a check written here. An
       attachment OWNED by another company is therefore simply not there and
       ``get_attachment`` raises its 404 - never a 403, which would confirm the
       id exists, the one thing the other company must not learn (the same
       reasoning as ``get_reading``). An attachment with a NULL ``company_id`` is
       shared on purpose, platform-wide, and stays readable here exactly as it is
       everywhere else.
    2. Refuse a TRASHED row the same way, and this one has to be written here:
       ``get_attachment`` is ``_get_attachment_any``, "active or archived" by its
       own docstring, so a trashed id would otherwise read perfectly well. The
       picker only ever offers live files, so nothing in the UI can reach this -
       which is exactly why the route has to say no on its own. Also a 404 and
       not a 403, for the same reason as above.
    3. Refuse a file the library already says is not a PDF, on metadata, before
       any storage call.
    4. Refuse an oversized file from its RECORDED size, also before any storage
       call. Downloading 200 MB in order to then refuse it is the version of
       this that costs money.
    5. Only now fetch the bytes, through ``get_file_content_for``, which takes
       the row we are already holding (so this does not re-SELECT it) and
       dispatches S3 or R2 from it. A row that names no object at all is a
       BROKEN ROW, not a storage outage, and gets its own answer - telling
       somebody to "try again" for a file that has no bytes anywhere is advice
       that can never come true.
    6. Re-assert the ceiling on what actually arrived. The recorded size is
       metadata, and metadata drifts; the upload path measures the real bytes,
       so this path has to as well or the two limits are not the same limit.

    Then ``create_reading``, unchanged, which is what makes the two sources
    indistinguishable from the reading onwards. The row lands in the caller's
    company scope by the same stamping the upload gets.
    """
    # Imported here rather than at module scope: this is the dealer kit reaching
    # into resources for one call, and a top-level import would drag the whole
    # attachments service into every module that touches a flyer.
    from app.services.resources_service import AttachmentService
    from app.services.storage_router import extract_key

    service = AttachmentService(db)
    attachment = service.get_attachment(attachment_id)
    if getattr(attachment, "is_deleted", False):
        # The SAME 404 the loader raises for a row that is not there, built by
        # the same helper: a trashed file and an out-of-scope one must be one
        # answer, or the difference between them is readable from outside.
        raise handle_not_found("Attachment", attachment_id)

    assert_pdf_mime(getattr(attachment, "mime_type", None))
    recorded_size = getattr(attachment, "file_size_bytes", None)
    if recorded_size:
        assert_within_limit(int(recorded_size))

    # A row with no ``file_path``, or one no storage key can be recovered from,
    # is a broken record rather than a bucket having a bad day. Checked here so
    # the two land on different answers: ``get_file_content_for`` raises a bare
    # ``Exception`` for both, and swept into the arm below they would tell a
    # designer to retry something that will fail identically forever.
    if not extract_key(getattr(attachment, "file_path", None)):
        raise AppException(
            status_code=422,
            message=(
                "That file has no stored copy the system can read, so it cannot "
                "be read as a flyer. Upload the flyer from your computer instead."
            ),
            code="FLYER_SOURCE_MISSING",
        )

    try:
        data = service.get_file_content_for(attachment)
    except AppException:
        raise
    except Exception as exc:  # noqa: BLE001 - the bucket's problem, said in words
        logger.warning(
            "Flyer attachment %s could not be fetched from storage: %s",
            attachment_id,
            exc,
        )
        # Not a bare 500: the global handler answers those with "Internal server
        # error" and nothing else, which tells a designer to raise a ticket for
        # something they can work around in ten seconds by uploading the file.
        raise AppException(
            status_code=502,
            message=(
                "That file could not be fetched from storage. "
                "Try again, or upload the flyer from your computer."
            ),
            code="FLYER_SOURCE_UNREADABLE",
        ) from exc

    assert_within_limit(len(data))

    return create_reading(
        db,
        # The library's user-facing label: ``stored_filename`` is the renameable
        # display name everywhere in Files, and ``original_filename`` is the
        # fallback for rows without one. The picker shows the same precedence.
        filename=(
            getattr(attachment, "stored_filename", None)
            or getattr(attachment, "original_filename", None)
        ),
        data=data,
        user_id=user_id,
    )


def _store_banners(
    db: Session,
    reading: FlyerReading,
    *,
    filename: Optional[str],
    user_id: Optional[str],
) -> None:
    """Put each page's banner in the asset library and note where it went.

    Best-effort per page, deliberately. A storage outage costs the backgrounds
    and nothing else: the reading is what a seed is BUILT from, and throwing
    away a 36 page extraction because a bucket was briefly unreachable would be
    a far worse trade than a draft somebody has to re-upload for its artwork.
    The banners are also the only images stored - one row per flyer page that
    has one, not one per picture on the paper, or a library a human is supposed
    to browse would fill with product shots.

    Each attempt gets its own SAVEPOINT, and that is the whole point rather than
    a detail. "Best-effort" has to mean the caller is no worse off than if the
    effort had never been made, and a bare ``db.rollback()`` in the handler
    breaks that promise in the loudest possible way: it throws away everything
    the caller has written and not yet committed, so a request that goes on to
    return 201 has silently discarded rows it already wrote. A savepoint undoes
    the half-written asset ROWS and nothing else, which is what the word meant.

    **Rows, though - not bytes.** ``create_from_bytes`` PUTs the image (and its
    thumbnail, a second object) into the bucket BEFORE it flushes, so a failure
    at the flush - a company-scope refusal, a constraint, the very CHECK that
    migration 317 widened - rolls the rows back and leaves the objects behind.
    That is the orphan family this module's "Death" section exists to close,
    reappearing on the error path, and it is bounded: two objects per failed
    page, only on a failure that is already being logged. Closing it properly
    means create_from_bytes taking responsibility for its own uploads when the
    flush fails, which is a change to that function rather than to this loop -
    so it is named here and not papered over.

    (The project's usual rule is to commit before a best-effort side effect
    rather than reach for ``begin_nested``. That rule is for effects that happen
    AFTER the main operation, where there is a natural commit point to sit
    behind. This one runs in the MIDDLE of building a reading, where there is no
    such point and a savepoint is the only tool that undoes a part.)
    """
    label = (filename or "flyer.pdf").rsplit(".", 1)[0]

    for page in reading.pages:
        if page.banner is None:
            continue
        try:
            with db.begin_nested():
                asset = asset_service.create_from_bytes(
                    db,
                    content=page.banner.image,
                    name=f"{label} page {page.number} banner",
                    mime=page.banner.mime,
                    tags=["flyer", "banner"],
                    user_id=user_id,
                )
        except Exception as exc:  # noqa: BLE001 - artwork is never worth the reading
            logger.warning(
                "Flyer banner for page %s of %s could not be stored: %s",
                page.number,
                label,
                exc,
            )
            continue
        page.banner_asset_id = asset.id


def get_reading(db: Session, reading_id: str) -> FlyerReadingRecord:
    record = (
        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).first()
    )
    if record is None:
        # The company scope filter runs before this, so "another company's
        # reading" and "no such reading" are deliberately the same answer. A 403
        # would confirm the id exists, which is the one thing the other company
        # must not learn.
        raise AppException(status_code=404, message="Flyer reading not found")
    return record


def list_readings(db: Session) -> list[FlyerReadingRecord]:
    """Newest first: the flyer somebody is working on is the one they just read.

    ``id`` breaks ties. Postgres ``now()`` is transaction time, so two readings
    written inside one transaction share a timestamp and would otherwise come
    back in whatever order the planner felt like.
    """
    return (
        db.query(FlyerReadingRecord)
        .order_by(FlyerReadingRecord.created_at.desc(), FlyerReadingRecord.id.desc())
        .all()
    )


def delete_reading(db: Session, reading_id: str) -> None:
    """Hard delete, and take the artwork nothing else is showing.

    A reading is a working artefact, not a record to retain - but its BANNERS
    are not. Each one is a row in the asset library backed by real bytes, and a
    brochure seeded from this reading binds them as section backgrounds, so a
    cascade would blank the artwork on a catalogue that may already be published.
    Somebody tidying the flyer list must never cost a reader a background they
    can currently see.

    The reading row is deleted and FLUSHED before the sweep, deliberately: the
    reading is itself one of the things that names an asset, so leaving it
    visible would make every banner look in-use and nothing would ever be
    collected. After the flush the only claims left are real ones.

    Refusing the delete outright was the alternative, and it is worse: every
    reading that was ever seeded would be undeletable forever, and the flyer
    list would fill with rows nobody may remove - which is the same litter this
    is meant to stop, moved from the bucket to the screen.
    """
    record = get_reading(db, reading_id)
    banners = banner_asset_ids(record.reading_json)

    db.delete(record)
    db.flush()

    doomed = asset_service.delete_unreferenced(db, banners)
    db.commit()

    # After the commit, never before: bytes are the one part of this no
    # rollback can undo.
    asset_service.purge_objects(doomed)


def report_for(
    db: Session,
    record: FlyerReadingRecord,
    promotion_id: Optional[str] = None,
) -> MatchReport:
    """The report, computed NOW against the master as it stands NOW.

    Deliberately not memoised on the row. See the module docstring: the whole
    value of this report is that it is true at the moment it is read.

    ``promotion_id`` is not checked for existence on purpose. A promotion that
    has been deleted reports every matched product as not promoted, which is how
    a reviewer discovers the brochure points at something that is gone - a 404
    here would just look like a broken screen.
    """
    return match_reading(db, to_reading(record), promotion_id=promotion_id)
