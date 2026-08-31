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

**Extraction runs on the worker, never in the request.** Measured, not
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

PR #164 moved that work off the event loop with a threadpool, which stopped one
read freezing a whole gunicorn worker (a ``GET /health`` probe waited 57.5
seconds on a single worker before it) and did nothing about the duration - by
design. The duration then produced its own failure: the captain's read came back
as ``Gateway timeout (504)``, because a proxy in front of the backend gave up
while FastAPI was still extracting. Raising that timeout fixes one flyer and
re-breaks on the next bigger one, so the request now returns BEFORE the work
starts.

**So this module has two halves, and the split is the design.**

*In the request*: ``enqueue_reading_from_upload`` / ``enqueue_reading_from_attachment``.
They do only what cannot wait - the refusals a designer must be told about at
once (not a PDF, over the ceiling, no stored copy), staging an upload's bytes,
and writing the row. The row is created in ``processing``, with the id it will
still have when the report is ready, which is what makes "it appears in my
uploads immediately" and "Done opens the report exactly as today" one thing.

*On the worker*: ``complete_reading`` / ``fail_reading``, driven by
``app.tasks.flyer_read_tasks.read_flyer``. That is where the bytes are fetched
and the 18 seconds are spent.

``create_reading`` survives as a synchronous convenience for tests, fixtures and
scripts: it builds the same enqueue-shape row and completes it in place, so what
it produces is byte-identical to what the job produces.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dealer_kit import FlyerReadingRecord
from app.models.product import Product
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

# The read gets its OWN queue, for the reason ``catalogue_render`` has one: 20
# to 60 seconds of CPU-bound PyMuPDF should not sit in front of every Excel
# import. It is listed LAST in the worker's default queue list, so RQ drains the
# imports first.
FLYER_READ_QUEUE = "flyer_read"

# 15 minutes. The real flyer measures 20 to 60 seconds, so this is a ceiling on
# a job that has gone wrong rather than a budget anything normal spends.
FLYER_READ_JOB_TIMEOUT = 900

# Where an upload's bytes wait for the worker. Deliberately NOT under any
# attachment prefix: this is a temporary copy of a file nobody filed, it is
# deleted the moment the job ends either way, and nothing in Resource Management
# should ever list it.
STAGING_PREFIX = "flyer-readings/pending/"


class ReadingStatus:
    """Where a reading is. The database CHECK holds the same three values.

    ``PROCESSING`` from the moment the POST answers until the job writes one of
    the other two. Nothing else is ever a status, and a row written before the
    job existed reads ``DONE`` by the migration's server default - which is not
    a guess, it is what happened to it.
    """

    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


def _now() -> datetime:
    """Naive UTC, matching every other timestamp column in this system."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def empty_reading_json() -> dict:
    """What a reading holds before the flyer has been read.

    An empty reading rather than NULL or ``{}``, so ``page_count``,
    ``code_count`` and ``headings`` answer 0 / 0 / [] on a pending row without a
    single special case at any of the places that read them.
    """
    return {"version": READING_FORMAT_VERSION, "pages": []}


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


def refusal_message(exc: Exception) -> str:
    """The words an ``AppException`` was raised with, for writing onto a row.

    There is no ``.message`` on it to read, and this is the one thing about
    ``AppException`` that catches everybody: it is an ``HTTPException`` whose
    ``detail`` is the ``{message, detail, code}`` dict the global handler
    serialises. ``exc.message`` raises ``AttributeError`` - and it raises it
    inside the handler for the ORIGINAL refusal, which is the worst place
    available: the read stops without recording why, so the row sits
    ``processing`` forever and the designer is told nothing at all.

    Same extraction as ``bulk_update_registry._exc_message``, with this feature's
    fallback rather than that one's.
    """
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        message = detail.get("message")
        if message:
            return str(message)
    if detail:
        return str(detail)
    return str(exc) or "The flyer could not be read."


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
def _new_processing_record(
    *,
    filename: Optional[str],
    byte_size: int,
    sha256: Optional[str],
    source_attachment_id: Optional[str],
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """The row as it looks the instant a read is asked for.

    Built in ONE place for both sources and for the synchronous convenience, so
    a reading made any of the three ways starts identical - which is what lets
    the job be written against the row rather than against where it came from.
    """
    return FlyerReadingRecord(
        filename=(filename or "flyer.pdf")[:255],
        byte_size=byte_size,
        sha256=sha256,
        reading_json=empty_reading_json(),
        status=ReadingStatus.PROCESSING,
        source_attachment_id=source_attachment_id,
        created_by=user_id,
    )


def _reading_in_flight(
    db: Session, *, sha256: Optional[str] = None, attachment_id: Optional[str] = None
) -> Optional[FlyerReadingRecord]:
    """A read of the SAME source that is already running, if there is one.

    The re-click is the case this exists for: a designer who does not see the
    row appear (or who is not sure the click registered) presses the button
    again, and without this they get a second 20 to 60 second extraction of the
    same document, a second set of banners in the asset library, and two rows to
    choose between.

    Company scope is the session's, applied by the global listener, so this can
    only ever find the caller's own reading.

    Only ``processing`` blocks. A ``done`` or ``failed`` reading of the same file
    is history: re-reading a flyer after fixing the master, or after a failure,
    is a thing people do on purpose.

    This is a READ, and a read cannot be the guarantee - see ``_insert_or_join``
    for the window it leaves and the unique index that closes it.
    """
    query = db.query(FlyerReadingRecord).filter(
        FlyerReadingRecord.status == ReadingStatus.PROCESSING
    )
    if attachment_id is not None:
        query = query.filter(FlyerReadingRecord.source_attachment_id == attachment_id)
    elif sha256 is not None:
        query = query.filter(FlyerReadingRecord.sha256 == sha256)
    else:  # pragma: no cover - a caller with neither has nothing to match on
        return None
    return query.order_by(FlyerReadingRecord.created_at.desc()).first()


def _insert_or_join(
    db: Session,
    record: FlyerReadingRecord,
    *,
    sha256: Optional[str] = None,
    attachment_id: Optional[str] = None,
) -> tuple[FlyerReadingRecord, bool]:
    """Commit the new ``processing`` row, or hand back the one that beat it.

    Returns ``(row, inserted)``. ``inserted`` is False when this call joined a
    read that was already running, so the caller knows there is nothing to queue
    and, for an upload, a staged copy of the bytes to throw away.

    ``_reading_in_flight`` reads and this writes, and between the two statements
    there is a window nothing in Python can close: two clicks landing together -
    a double click, a retried request, two tabs - both see nothing in flight and
    both insert. The loser's job then reads the same 20 to 60 second document a
    second time and stores a SECOND set of banner assets, which is the part that
    is not merely wasteful: those assets are library rows a designer has to tell
    apart afterwards.

    So the database closes it. Migration 359's two partial indexes are UNIQUE on
    ``(company_id, source_attachment_id)`` and ``(company_id, sha256)`` while
    ``status = 'processing'``, and the second INSERT is refused. That refusal is
    not an error, it is the answer the read was asking for: roll back, look
    again, and return the row that won. The caller answers 202 carrying it,
    exactly as the uncontended re-click does.

    The second attempt covers the one case where the look comes back empty: the
    winner reached ``done`` or ``failed`` between our INSERT and our SELECT, so
    the index no longer holds anything and the row we were refused now belongs.
    Re-reading a finished flyer is a thing people do on purpose. A refusal on
    that attempt is a real one and propagates.
    """

    def _commit_new() -> FlyerReadingRecord:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    try:
        return _commit_new(), True
    except IntegrityError:
        db.rollback()
        existing = _reading_in_flight(db, sha256=sha256, attachment_id=attachment_id)
        if existing is not None:
            logger.info(
                "A read of the same source was already in flight as reading %s; "
                "joining it rather than starting a second",
                existing.id,
            )
            return existing, False

    return _commit_new(), True


def _enqueue(
    record: FlyerReadingRecord,
    staged_provider: Optional[str],
    staged_key: Optional[str],
) -> Optional[str]:
    """Hand the read to the worker. Returns the RQ job id.

    **The one seam the tests patch**, and it is deliberately thin: it does the
    enqueue and nothing else, so a test can replace it with a recorder (and run
    the job inline on its own session) or with something that raises, and still
    exercise the real failure handling in ``_enqueue_or_fail`` around it.

    Both imports are inside the function. ``app.tasks.flyer_read_tasks`` pulls in
    ``SessionLocal`` and ``queue_service`` pulls in Redis, and neither belongs in
    every module that happens to touch a flyer.
    """
    from app.services.queue_service import enqueue_job
    from app.tasks.flyer_read_tasks import read_flyer

    job = enqueue_job(
        read_flyer,
        str(record.id),
        staged_provider,
        staged_key,
        queue_name=FLYER_READ_QUEUE,
        job_timeout=FLYER_READ_JOB_TIMEOUT,
    )
    return getattr(job, "id", None)


def _enqueue_or_fail(
    db: Session,
    record: FlyerReadingRecord,
    *,
    staged_provider: Optional[str] = None,
    staged_key: Optional[str] = None,
) -> FlyerReadingRecord:
    """Queue the read, or record that it could not be queued.

    Redis being down must not read as "your flyer is being processed". The row
    is marked ``failed`` with the queue named, the staged copy is discarded so
    the bucket does not keep bytes for a job that will never run, and the caller
    still answers 202 carrying that row - the designer sees a Failed pill with a
    reason instead of a row that stays Processing forever.
    """
    try:
        job_id = _enqueue(record, staged_provider, staged_key)
    except Exception as exc:  # noqa: BLE001 - the queue's problem, said in words
        logger.exception("Flyer reading %s could not be queued", record.id)
        fail_reading(db, record, message=f"Could not queue the flyer read: {exc}")
        discard_staged(staged_provider, staged_key)
        return record

    record.job_id = job_id
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _stage_upload(data: bytes) -> tuple[str, str]:
    """Park an upload's bytes where the worker can reach them.

    ``storage_router`` is reached through the MODULE at call time rather than by
    a name imported at load, and that is not a style preference:
    ``tests/_fake_storage.patch_storage`` patches ``storage_router.get_backend``,
    and a name bound at import would still hold the real backend and PUT the
    fixture flyer into the live Cloudflare bucket on every test run. That is the
    exact accident that file exists to prevent. Same rule as ``asset_service``.

    A bucket that refuses is answered in words, not as a bare 500. This is the
    ONE storage failure a designer can be told about while they are still
    looking at the dialog - the worker's fetch happens long after the request -
    and "Internal server error" would send them to raise a ticket for something
    a retry usually fixes. Nothing has been written at this point: the row is
    created after the bytes are parked, precisely so a failure here leaves no
    reading claiming to be in progress.
    """
    from app.services import storage_router

    provider = storage_router.default_provider()
    try:
        key, _url = storage_router.get_backend(provider).upload_file(
            file_content=data,
            file_path=f"{STAGING_PREFIX}{uuid.uuid4().hex}.pdf",
            content_type="application/pdf",
        )
    except Exception as exc:  # noqa: BLE001 - the bucket's problem, said in words
        logger.exception("A flyer upload could not be staged for the worker")
        raise AppException(
            status_code=502,
            message=(
                "That flyer could not be stored for reading. "
                "Try again in a moment."
            ),
            code="FLYER_STAGING_FAILED",
        ) from exc
    return provider, key


def discard_staged(provider: Optional[str], key: Optional[str]) -> None:
    """Forget a staged upload. Best-effort: an orphan object is never worth a 500."""
    if not key:
        return
    from app.services import storage_router

    storage_router.delete_object_best_effort(provider or "", key)


def enqueue_reading_from_upload(
    db: Session,
    *,
    filename: Optional[str],
    data: bytes,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Take a flyer off the designer's laptop and hand the read to the worker.

    The order is the design, and it is the same shape the from-attachment path
    uses:

    1. Fingerprint the bytes. It is what "the same file is already being read"
       is answered with, and it is what the row will carry when it is done.
    2. If a read of these exact bytes is already in flight for this company,
       return THAT row. Nothing is staged and nothing is queued - see
       ``_reading_in_flight``.
    3. Stage the bytes. The worker is another process (and in production another
       container), so the only way it can see an upload is through storage. They
       go under their own prefix and are deleted when the job ends, either way.
    4. Write the row and commit. The commit is what stamps the company, and it
       has to happen HERE, in the request, because the worker has no request
       identity to stamp from. It is also where step 2's answer is made true
       under concurrency (``_insert_or_join``), and where a failure has to give
       step 3's bytes back.
    5. Queue it.

    Called from a threadpool: hashing 20 MB and a PUT to object storage are both
    synchronous, and the route that calls this is ``async def`` for the chunked
    ceiling read (AC-K1).
    """
    digest = hashlib.sha256(data).hexdigest()

    existing = _reading_in_flight(db, sha256=digest)
    if existing is not None:
        logger.info(
            "Flyer upload %s is already being read as reading %s", filename, existing.id
        )
        return existing

    provider, key = _stage_upload(data)

    try:
        record, inserted = _insert_or_join(
            db,
            _new_processing_record(
                filename=filename,
                byte_size=len(data),
                sha256=digest,
                source_attachment_id=None,
                user_id=user_id,
            ),
            sha256=digest,
        )
    except Exception:
        # The bytes are parked BEFORE the row exists (step 3 before step 4), so
        # everything that can refuse the row - the company stamp, the CHECK, a
        # database blip - leaves a copy of somebody's flyer in the bucket with
        # nothing pointing at it. Only a QUEUED job discards a staged object,
        # and no job was queued, so this is the last place that can.
        discard_staged(provider, key)
        raise

    if not inserted:
        # A concurrent click won the race. Its job reads its OWN staged copy;
        # ours is already an orphan.
        discard_staged(provider, key)
        return record

    return _enqueue_or_fail(db, record, staged_provider=provider, staged_key=key)


def enqueue_reading_from_attachment(
    db: Session,
    *,
    attachment_id: str,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Read a flyer the file library is already holding, on the worker.

    Everything a designer must be told AT ONCE still happens here, in the
    request, on METADATA only - and that is the whole reason this path never
    touches storage: out of scope or trashed is a 404, a file the library
    already says is not a PDF is a 400, a recorded size over the ceiling is a
    413, and a row naming no stored object is a 422. See
    ``assert_attachment_readable`` for why that order matters.

    Then the same four steps as the upload, minus the staging: idempotency on
    the attachment id, the row, the commit, the queue. ``sha256`` is left NULL -
    there are no bytes here to fingerprint, and inventing one from the
    attachment's own hash would claim something about a file this row has not
    read yet. The job fills it in.
    """
    attachment = assert_attachment_readable(db, attachment_id)

    existing = _reading_in_flight(db, attachment_id=str(attachment.id))
    if existing is not None:
        logger.info(
            "Attachment %s is already being read as reading %s", attachment_id, existing.id
        )
        return existing

    record = _new_processing_record(
        # The library's user-facing label: ``stored_filename`` is the renameable
        # display name everywhere in Files, and ``original_filename`` is the
        # fallback for rows without one. The picker shows the same precedence.
        filename=(
            getattr(attachment, "stored_filename", None)
            or getattr(attachment, "original_filename", None)
        ),
        # The recorded size, so the list has a number to show while it runs. The
        # job overwrites it with what actually arrived.
        byte_size=int(getattr(attachment, "file_size_bytes", None) or 0),
        sha256=None,
        source_attachment_id=str(attachment.id),
        user_id=user_id,
    )
    record, inserted = _insert_or_join(db, record, attachment_id=str(attachment.id))
    if not inserted:
        # Two clicks landed together and the other one won. Nothing is staged on
        # this path, so there is nothing to clean up - just hand back its row.
        return record

    return _enqueue_or_fail(db, record)


def assert_attachment_readable(db: Session, attachment_id: str):
    """The checks that need only the attachment ROW, in the order that matters.

    1. Load it through the ordinary ORM path, so the global company-scope
       listener does the filtering rather than a check written here. An
       attachment OWNED by another company is therefore simply not there and
       ``get_attachment`` raises its 404 - never a 403, which would confirm the
       id exists, the one thing the other company must not learn (the same
       reasoning as ``get_reading``). An attachment with a NULL ``company_id`` is
       shared on purpose, platform-wide, and stays readable here exactly as it
       is everywhere else.
    2. Refuse a TRASHED row the same way, and this one has to be written here:
       ``get_attachment`` is ``_get_attachment_any``, "active or archived" by its
       own docstring, so a trashed id would otherwise read perfectly well. The
       picker only ever offers live files, so nothing in the UI can reach this -
       which is exactly why the route has to say no on its own. Also a 404 and
       not a 403, for the same reason as above.
    3. Refuse a file the library already says is not a PDF, on metadata.
    4. Refuse an oversized file from its RECORDED size. Downloading 200 MB in
       order to then refuse it is the version of this that costs money - and
       under the queue it would also mean the designer waits for a worker to
       tell them something the row already said.
    5. Refuse a row that names no stored object at all. That is a BROKEN ROW,
       not a storage outage, and it gets its own answer: telling somebody to
       "try again" for a file that has no bytes anywhere is advice that can
       never come true.

    Returns the attachment so the caller does not re-SELECT it. Called twice per
    library read - once in the request, once on the worker - because the worker
    holds a different session and the file may have been trashed in between.
    """
    # Imported here rather than at module scope: this is the dealer kit reaching
    # into resources for one call, and a top-level import would drag the whole
    # attachments service into every module that touches a flyer.
    from app.services.resources_service import AttachmentService
    from app.services.storage_router import extract_key

    attachment = AttachmentService(db).get_attachment(attachment_id)
    if getattr(attachment, "is_deleted", False):
        # The SAME 404 the loader raises for a row that is not there, built by
        # the same helper: a trashed file and an out-of-scope one must be one
        # answer, or the difference between them is readable from outside.
        raise handle_not_found("Attachment", attachment_id)

    assert_pdf_mime(getattr(attachment, "mime_type", None))
    recorded_size = getattr(attachment, "file_size_bytes", None)
    if recorded_size:
        assert_within_limit(int(recorded_size))

    if not extract_key(getattr(attachment, "file_path", None)):
        raise AppException(
            status_code=422,
            message=(
                "That file has no stored copy the system can read, so it cannot "
                "be read as a flyer. Upload the flyer from your computer instead."
            ),
            code="FLYER_SOURCE_MISSING",
        )
    return attachment


def attachment_bytes(db: Session, attachment) -> bytes:
    """The file's actual bytes, and the ceiling re-asserted on them.

    Runs on the WORKER, which is the whole point of the split: this is the step
    that can take seconds against a 20 MB object in another region, and nothing
    a designer is waiting on should be behind it.

    The ceiling is checked again here because the recorded size is metadata and
    metadata drifts. The upload path measures the real bytes, so this path has
    to as well, or the two limits are not the same limit.
    """
    from app.services.resources_service import AttachmentService

    try:
        data = AttachmentService(db).get_file_content_for(attachment)
    except AppException:
        raise
    except Exception as exc:  # noqa: BLE001 - the bucket's problem, said in words
        logger.warning(
            "Flyer attachment %s could not be fetched from storage: %s",
            getattr(attachment, "id", None),
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
    return data


def complete_reading(
    db: Session,
    record: FlyerReadingRecord,
    *,
    data: bytes,
    filename: Optional[str] = None,
) -> FlyerReadingRecord:
    """Read the bytes and write what they say INTO the row that was waiting.

    The job's core, and the one place a reading is ever filled in. Both sources
    arrive here with the same row shape, so a reading made from an upload and one
    made from the library are the same record with the same banners and the same
    report - which is what makes "indistinguishable once created" true rather
    than aspirational.

    ``extract_flyer`` raises ``ValueError`` for anything that is not a readable
    PDF, and that becomes the same 400 in words it always did. The alternatives
    are both worse: a 500 tells a designer the system is broken when their file
    is, and a done row carrying an empty report tells them their flyer has no
    products on it.

    A LOCKED PDF gets its own message. Print-ready artwork comes back from an
    agency password protected far more often than it comes back corrupt, and it
    is fixable in a minute by the person holding it - but only if they are told
    that is the problem. Handed the generic advice, they re-export the same
    locked file and read it again.

    It RAISES those rather than writing them, deliberately: the caller decides
    what a refusal means. The job turns it into a ``failed`` row; ``create_reading``
    turns it into an exception for the script that called it.

    ONE commit, at the end, covering the banners and the reading together. The
    asset ids the banners come back with are serialised INTO ``reading_json``,
    so a half-commit would be a library row nothing points at.
    """
    try:
        # WITH the artwork this time. The job holds the PDF's bytes for the only
        # moment they exist in this system - the reading deliberately keeps the
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

    label = filename or record.filename
    _store_banners(db, reading, filename=label, user_id=record.created_by)

    record.reading_json = serialise(reading)
    record.byte_size = len(data)
    record.sha256 = hashlib.sha256(data).hexdigest()
    record.status = ReadingStatus.DONE
    record.error_message = None
    record.finished_at = _now()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def fail_reading(
    db: Session, record: FlyerReadingRecord, *, message: str
) -> FlyerReadingRecord:
    """Record why a read did not happen, in the words the request used to say.

    The row IS the record. A read that fails on the worker has no request left
    to answer, so a message that is not written here is a message nobody ever
    sees - and a designer looking at a row with no reason re-uploads the same
    broken file.

    Truncated at 2000 characters: a driver traceback stringified into a pill on
    a list screen helps nobody, and the full text is in the worker log.
    """
    record.status = ReadingStatus.FAILED
    record.error_message = (message or "The flyer could not be read.")[:2000]
    record.finished_at = _now()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_reading(
    db: Session,
    *,
    filename: Optional[str],
    data: bytes,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Read a flyer's bytes and keep what they say, synchronously.

    Not what the routes use any more - they enqueue - but kept, and kept on the
    same two functions the job runs, so a fixture, a script or a test gets a row
    that is indistinguishable from one the worker produced: same enqueue-shape
    row, same ``complete_reading`` writing into it.

    A refusal is written onto the row AND re-raised. The caller asked for a
    reading and has to be told it did not get one; the row still has to say why,
    because it is committed by then and something has to explain it on the list.

    It does NOT join an in-flight read the way the two enqueue paths do: a
    caller here wants a finished reading back, not somebody else's half of one.
    So it inserts, and the unique index means "the same bytes are being read on
    the worker RIGHT NOW" refuses that insert rather than producing a second
    row. That is the same answer, delivered as an exception because this caller
    has one to catch.
    """
    record = _new_processing_record(
        filename=filename,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_attachment_id=None,
        user_id=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        return complete_reading(db, record, data=data, filename=filename)
    except AppException as exc:
        db.rollback()
        fail_reading(db, record, message=refusal_message(exc))
        raise
    except Exception as exc:  # noqa: BLE001 - the row is committed; it must say why
        # Anything that is NOT a refusal - PyMuPDF dying on a malformed page,
        # the process running out of memory mid-extraction, a storage driver
        # raising while the banners are stored. The row was committed as
        # ``processing`` before any of this ran, so a handler that only knows
        # about ``AppException`` leaves it saying "being read" forever, on a
        # list screen, with no job anywhere that will ever finish it. Same words
        # the worker's generic arm uses, so the two paths read alike.
        # ``complete_reading`` commits the row and only then refreshes it, so a
        # failure raised after that commit belongs to a read that DID happen.
        # Re-read the row after the rollback and fail it only while it still
        # says ``processing``, or a finished reading gets relabelled as one that
        # never happened.
        logger.exception("Flyer reading %s could not be completed", record.id)
        db.rollback()
        current = (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.id == record.id)
            .first()
        )
        if current is not None and (
            getattr(current, "status", None) == ReadingStatus.PROCESSING
        ):
            fail_reading(db, current, message=f"The flyer could not be read: {exc}")
        raise


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


def assert_read(record: FlyerReadingRecord) -> None:
    """Refuse to build anything out of a flyer that has not been read yet.

    409 rather than 404 or 422: the reading EXISTS and the request is
    well-formed, it is the state that is wrong, and it will stop being wrong on
    its own in a few seconds. The two states get different words because the
    next action differs - one is "wait", the other is "read a different file".

    The screens do not offer the actions this guards before a reading is done,
    so nothing in the UI can reach it. That is exactly why it is here: a stale
    tab, a retried request or a script are all outside what the UI can promise,
    and seeding a brochure - or proposing specs - from an empty reading would
    produce an answer with nothing in it and no error to explain why.

    It lives in the service rather than beside its first caller because three
    routes across two modules now refuse on the same condition (seed, apply the
    printed sizes, propose the specs), and three copies of a refusal are three
    sets of words that drift.
    """
    reading_status = getattr(record, "status", None) or ReadingStatus.DONE
    if reading_status == ReadingStatus.DONE:
        return
    if reading_status == ReadingStatus.PROCESSING:
        message = "That flyer is still being read. Try again once it says Done."
    else:
        message = (
            "That flyer could not be read, so there is nothing to build from it. "
            + (record.error_message or "Read the flyer again, or try another file.")
        )
    raise AppException(status_code=409, message=message, code="FLYER_NOT_READ_YET")


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

    ``record.code_overrides`` travels straight through: what a reviewer has
    adopted on this reading (PLAN-flyer-code-adopt.md) resolves everywhere the
    report is read from, exactly like a real match.
    """
    return match_reading(
        db,
        to_reading(record),
        promotion_id=promotion_id,
        overrides=record.code_overrides,
    )


def _printed_on(pages: tuple[int, ...]) -> str:
    """"p. 3" / "p. 3, 11" - the same words the frontend's own helper uses.

    A reviewer reading a refusal is holding the flyer; a page range beside the
    other product's code is the whole reason AC-A.5's target-taken message is
    actionable rather than merely accurate.
    """
    if not pages:
        return "another page"
    return "p. " + ", ".join(str(page) for page in pages)


def adopt_code(
    db: Session,
    record: FlyerReadingRecord,
    *,
    printed_code: str,
    product_id: str,
) -> FlyerReadingRecord:
    """"This printed code IS that product" (PLAN-flyer-code-adopt.md, R4).

    The suggestion offered in the dialog is a default the FRONTEND applies;
    the server has no opinion and accepts any product in this company's scope.

    The report is recomputed WITHOUT this code's own override (so re-adopting
    - AC-A.4 - compares against the master and every OTHER adoption, never
    against the choice being replaced) and used for two refusals that would
    otherwise need their own queries:

    * the code already resolves on its own -> 409 (nothing to adopt);
    * the product is what another printed code on this reading already
      resolves to, itself or by an earlier adoption -> 409, naming that code
      and page (R1 - one product, one card).
    """
    assert_read(record)

    current = dict(record.code_overrides or {})
    others = {code: pid for code, pid in current.items() if code != printed_code}
    report = match_reading(db, to_reading(record), overrides=others)

    printed_codes = {entry.code for entry in report.matched} | {
        entry.code for entry in report.unmatched
    }
    if printed_code not in printed_codes:
        raise AppException(
            status_code=404,
            message=f"{printed_code} is not printed on this reading.",
            code="flyer_code_not_printed",
        )

    matched_by_code = {entry.code: entry for entry in report.matched}
    if printed_code in matched_by_code:
        raise AppException(
            status_code=409,
            message=f"{printed_code} is already a product; nothing to adopt.",
            code="flyer_code_already_matched",
        )

    product = db.query(Product).filter(Product.id == product_id).one_or_none()
    if product is None:
        raise AppException(
            status_code=404,
            message="That product was not found.",
            code="flyer_adopt_product_not_found",
        )

    taken = next(
        (entry for entry in report.matched if entry.product_id == product_id), None
    )
    if taken is not None:
        raise AppException(
            status_code=409,
            message=(
                f"{taken.code} on {_printed_on(taken.pages)} is already this product."
            ),
            code="flyer_adopt_target_taken",
        )

    current[printed_code] = product_id
    # REASSIGN, never mutate: SQLAlchemy does not see an in-place change to a
    # plain JSONB column.
    record.code_overrides = current
    record.code_overrides_changed_at = _now()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def unadopt_code(
    db: Session,
    record: FlyerReadingRecord,
    *,
    printed_code: str,
) -> FlyerReadingRecord:
    """Undo an adoption (R2: never touches a spec proposal batch, or the product).

    Specs already applied to the product from an adopted card stay applied -
    applying was its own deliberate act, and this only says the code is no
    longer being read as that product going forward.
    """
    assert_read(record)

    current = dict(record.code_overrides or {})
    if printed_code not in current:
        raise AppException(
            status_code=404,
            message=f"{printed_code} has not been adopted.",
            code="flyer_code_not_adopted",
        )

    del current[printed_code]
    record.code_overrides = current
    record.code_overrides_changed_at = _now()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
