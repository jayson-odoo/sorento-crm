"""Read a printed flyer, get the match report back (S7.3).

The only surface of the seeding feature a designer touches before the review
screen: point the system at the PDF, see what it found. Two sources, one result:
a file off their laptop, or a file the library is already holding.

**Permissions reuse the page split.** Reading a flyer into the Kit is drafting a
catalogue, so writes carry ``dealer_kit.page.edit`` and reads carry
``dealer_kit.page.view``. No new slug: a fourth one would need a grant sweep
migration before a single existing role held it, and every designer who can
build a page can already do everything this feature leads to. Both sources carry
the same slug, because they do the same thing.

**Extraction happens inside the request, but never on the event loop.** Measured
on the real ``_SORENTO A3 FLYER 2025-2026_compressed.pdf`` (20.1 MB, 36 A3 pages,
998 codes) on a quiet machine, ``extract_flyer`` alone takes 17 to 18 seconds,
and the whole POST 40 to 60 seconds on a loaded one. This module used to claim
"about a second", and that number was the entire justification for doing the
work in the request - so it is written down here as measured, with what it was
measured against, rather than as a recollection.

The consequence of getting it wrong was not slowness. The upload handler is
``async def``, so the read ran ON the loop and one flyer froze its whole worker:
a ``GET /health`` issued during a read waited **57.5 seconds** on a single
worker. Production runs four (``gunicorn --workers 4``), which is why it read as
"the system is jamming" from the uploading desktop and as nothing at all from a
phone on a different worker. The fix is ``run_in_threadpool`` - the heavy half
now runs where FastAPI would have run a plain ``def`` handler anyway.

A queue is still the right end state and is deliberately NOT built here: it buys
a pending row, a polling screen, a failure path and a worker restart per code
change. Take that decision again when artwork rasterisation lands, on these
numbers, not on a guess.

**The report is never stored.** It is derived from the stored reading against
the master, on every read. See ``flyer_reading_service``.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.dealer_kit import (
    AppliedDimensionOut,
    CodeSuggestionOut,
    DimensionApplyIn,
    DimensionApplyOut,
    DimensionCandidateOut,
    FlyerReadingFromAttachmentIn,
    FlyerReadingOut,
    PageHeadingOut,
    FlyerReadingSummary,
    FlyerSeedIn,
    FlyerSeedOut,
    MatchReportOut,
    MatchedCodeOut,
    RefusedDimensionOut,
    UnmatchedCodeOut,
)
from app.services.dealer_kit import dimension_apply_service
from app.services.dealer_kit import flyer_reading_service as svc
from app.services.dealer_kit import flyer_seed_service as seed_service
from app.services.dealer_kit import page_service

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")

# The two halves of applying a printed size, and they are deliberately different
# permissions. See the route.
_READ_THE_FLYER = require_permission("dealer_kit.page.view")
_WRITE_THE_MASTER = require_permission("master_data.products.edit")

# Read in pieces so the limit can be enforced while reading rather than after.
_CHUNK_BYTES = 1024 * 1024


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


async def _read_within_limit(file: UploadFile) -> bytes:
    """The upload's bytes, refusing anything over the ceiling as it arrives.

    Chunked rather than one ``await file.read()``: the check then fires on the
    first megabyte past the limit instead of after the whole file is in memory.
    Starlette has already spooled the request body, so this caps what the process
    HOLDS and what the extractor is handed, not what crossed the wire.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        svc.assert_within_limit(total)
        chunks.append(chunk)
    return b"".join(chunks)


def _suggestion_out(suggestion) -> Optional[CodeSuggestionOut]:
    if suggestion is None:
        return None
    return CodeSuggestionOut(
        product_id=suggestion.product_id,
        product_code=suggestion.product_code,
        product_name=suggestion.product_name,
        similarity=float(suggestion.similarity),
    )


def _matched_out(entry) -> MatchedCodeOut:
    return MatchedCodeOut(
        code=entry.code,
        product_id=entry.product_id,
        product_code=entry.product_code,
        product_name=entry.product_name,
        pages=list(entry.pages),
    )


def _report_out(report) -> MatchReportOut:
    """Built by hand, like every other dealer-kit response.

    A field added only to the schema class never reaches a screen, and the
    dataclasses on the other side of this are not pydantic models.
    """
    return MatchReportOut(
        matched=[_matched_out(entry) for entry in report.matched],
        unmatched=[
            UnmatchedCodeOut(
                code=entry.code,
                pages=list(entry.pages),
                suggestion=_suggestion_out(entry.suggestion),
            )
            for entry in report.unmatched
        ],
        not_promoted=[_matched_out(entry) for entry in report.not_promoted],
        dimension_candidates=[
            DimensionCandidateOut(
                code=entry.code,
                product_id=entry.product_id,
                pages=list(entry.pages),
                printed_length_mm=float(entry.printed_length_mm),
                printed_width_mm=float(entry.printed_width_mm),
                printed_height_mm=float(entry.printed_height_mm),
                current_length_mm=(
                    float(entry.current_length_mm)
                    if entry.current_length_mm is not None
                    else None
                ),
                current_width_mm=(
                    float(entry.current_width_mm)
                    if entry.current_width_mm is not None
                    else None
                ),
                current_height_mm=(
                    float(entry.current_height_mm)
                    if entry.current_height_mm is not None
                    else None
                ),
                verdict=entry.verdict,
            )
            for entry in report.dimension_candidates
        ],
        duplicates={code: list(pages) for code, pages in report.duplicates.items()},
        promotion_id=report.promotion_id,
    )


def _summary(record) -> FlyerReadingSummary:
    return FlyerReadingSummary(
        id=record.id,
        filename=record.filename,
        byte_size=record.byte_size,
        page_count=svc.page_count(record),
        code_count=svc.code_count(record),
        uploaded_at=record.created_at,
    )


def _detail(db: Session, record, promotion_id: Optional[UUID]) -> FlyerReadingOut:
    return FlyerReadingOut(
        **_summary(record).model_dump(),
        report=_report_out(
            svc.report_for(db, record, str(promotion_id) if promotion_id else None)
        ),
        # Off the stored reading, not the report: a heading is what the reader
        # found on the paper and has nothing to say about the master, so it
        # does not move when a product is created. The seed writes these same
        # values as its section names.
        headings=[
            PageHeadingOut(page=number, text=text)
            for number, text in svc.headings(record)
        ],
    )


# ``UUID`` and not ``str``: FastAPI then refuses a malformed value at the edge
# with a 422, so it can never reach a WHERE clause. Hand-checking it in the body
# is the version of this that gets forgotten on the next route, and a malformed
# uuid reaching the driver is exactly how this feature produced a 500 once.
_PROMOTION_ID = Query(
    None,
    alias="promotionId",
    description="Report which printed products this promotion does not carry.",
)


def _create_and_detail(
    db: Session,
    *,
    filename: Optional[str],
    data: bytes,
    user_id: Optional[str],
    promotion_id: Optional[UUID],
) -> FlyerReadingOut:
    """Store a reading and answer with its report, as ONE unit of blocking work.

    Both halves and not just the extraction, deliberately. The report recompute
    inside ``_detail`` is a further 0.9 seconds against the real flyer's 998
    codes, and a handler that moved the extraction off the loop and then ran the
    report on it would have moved the freeze rather than removed it.

    Every second of this is synchronous: PyMuPDF for the reading, boto for the
    banners, psycopg for the row. Nothing in here is awaitable, which is exactly
    why it belongs in a thread.
    """
    record = svc.create_reading(db, filename=filename, data=data, user_id=user_id)
    return _detail(db, record, promotion_id)


@router.post(
    "/flyer-readings",
    response_model=FlyerReadingOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_flyer_reading(
    file: UploadFile = File(...),
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """A flyer off the designer's laptop.

    Still ``async def``, and that is the one thing about this route that must not
    change: ``_read_within_limit`` needs ``await file.read(...)`` to refuse an
    oversized upload as the bytes arrive rather than after they are all in
    memory. What changed is everything after that line - it now goes to
    ``run_in_threadpool``, which is what FastAPI does for a plain ``def`` handler
    and what this half of the route was never getting.

    The behaviour a caller sees is untouched: same 201, same body, same errors,
    same wait. What changed is that everybody ELSE keeps being served while it
    happens. See the module docstring for the 57.5 second measurement that made
    this necessary.
    """
    data = await _read_within_limit(file)
    return await run_in_threadpool(
        _create_and_detail,
        db,
        filename=file.filename,
        data=data,
        user_id=_user_id(user),
        promotion_id=promotion_id,
    )


@router.post(
    "/flyer-readings/from-attachment",
    response_model=FlyerReadingOut,
    status_code=status.HTTP_201_CREATED,
)
def read_flyer_from_attachment(
    payload: FlyerReadingFromAttachmentIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """A flyer the system is already holding.

    Marketing files the season's flyer in Resource Management long before
    anybody thinks about the Kit, so the alternative to this route is a designer
    downloading a 20 MB PDF out of the CRM to upload it straight back in.

    Plain ``def``, so FastAPI runs the whole thing in a thread: it does a storage
    download and then the same extraction as the upload, and must no more sit on
    the loop than that one does.

    ``dealer_kit.page.edit``, declared the same way as the upload, so a caller
    without it gets the same 403 naming the same slug. Nothing about the source
    of the bytes changes who may read a flyer.

    Everything before ``create_reading`` is in the service, in an order that
    matters (scope, then type, then size, THEN bytes) - see
    ``flyer_reading_service.create_reading_from_attachment``. From
    ``create_reading`` on, the two sources are one code path, which is what makes
    "indistinguishable once created" true rather than aspirational.
    """
    record = svc.create_reading_from_attachment(
        db, attachment_id=str(payload.attachment_id), user_id=_user_id(user)
    )
    return _detail(db, record, payload.promotion_id)


@router.get("/flyer-readings", response_model=list[FlyerReadingSummary])
def list_flyer_readings(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    """Which flyers have been read, newest first. No reports: see the schema."""
    return [_summary(record) for record in svc.list_readings(db)]


@router.get("/flyer-readings/{reading_id}", response_model=FlyerReadingOut)
def get_flyer_reading(
    reading_id: str,
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The reading as stored, and the report as it stands right now.

    ``promotionId`` is asked here rather than fixed at upload because "what does
    this promotion not carry" is a question about the report, not a property of
    the file. A reviewer tries it against two promotions without re-uploading.
    """
    return _detail(db, svc.get_reading(db, reading_id), promotion_id)


@router.post(
    "/flyer-readings/{reading_id}/seed",
    response_model=FlyerSeedOut,
    status_code=status.HTTP_201_CREATED,
)
def seed_from_flyer_reading(
    reading_id: str,
    payload: FlyerSeedIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """Build a DRAFT brochure from a reading.

    ``page.edit`` and deliberately NOT ``page.publish``: this creates a version
    no reader can reach, and putting it in front of every dealer stays a
    separate decision by somebody trusted with it. That is the whole of AC-E2 -
    a draft is a draft because no label points at it, not because a flag says so.

    201 rather than 202: the document exists by the time this returns. Matching
    the real flyer's 998 codes costs about 0.4s and the writes are a page, its
    version and one collection per printed row, so a queue here would buy a
    polling screen and nothing else.

    Another company's reading is a 404 from ``get_reading``, before anything is
    written. The seed then lands in the scope that reading was reachable in,
    which IS its company - and a scope holding more than one company cannot
    stamp an owned row at all, so it fails closed rather than guessing.
    """
    record = svc.get_reading(db, reading_id)
    result = seed_service.seed(
        db,
        record,
        page_id=payload.page_id,
        name=payload.name,
        slug=payload.slug,
        promotion_id=str(payload.promotion_id) if payload.promotion_id else None,
        commit_message=payload.commit_message,
        user_id=_user_id(user),
    )
    return FlyerSeedOut(
        page_id=result.page.id,
        name=result.page.name,
        slug=result.page.slug,
        public_path=page_service.public_path(db, result.page),
        version_id=result.version.id,
        version=result.version.version,
        section_count=result.section_count,
        collection_count=len(result.collections),
        seeded_product_count=result.seeded_product_count,
        skipped=[
            UnmatchedCodeOut(
                code=entry.code,
                pages=list(entry.pages),
                suggestion=_suggestion_out(entry.suggestion),
            )
            for entry in result.skipped
        ],
    )


@router.post(
    "/flyer-readings/{reading_id}/dimensions/apply",
    response_model=DimensionApplyOut,
)
def apply_flyer_dimensions(
    reading_id: str,
    payload: DimensionApplyIn,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    user: dict = Depends(_WRITE_THE_MASTER),
):
    """Write the sizes this flyer prints onto the products it names (S7.6).

    **Two permissions, and neither on its own.** Every other route in this file
    runs on the dealer-kit page split, because everything they do stays inside
    the Kit. This one leaves it: it writes ``products``, which order entry,
    procurement, the catalogue and every quote read from. So the authority to
    write is ``master_data.products.edit`` - the same slug that guards the
    product screen and the import - and ``dealer_kit.page.view`` is only the
    right to see the flyer being applied FROM.

    Deliberately NOT ``page.edit``. Drafting a brochure is not authority over
    the master, and a designer who may upload a flyer, seed a catalogue and
    publish it still may not change what a product measures. Equally
    deliberately not ``products.edit`` alone: a reading is company-scoped
    working material, and somebody who cannot open it has no business reaching
    into it. The two are ANDed by declaring both, in this order, so the 403 a
    designer sees names the permission they are actually missing.

    No API-key variant on either. This is a master-data write, and the shared
    external key acting as a user is not the principal for one.

    **The request names codes; it never carries millimetres.** The figures come
    from the stored reading. See ``dimension_apply_service`` for why that is the
    whole security model of this route, and for what a conflict costs.

    200 rather than 207. Refusals are not errors - a row the master already
    agrees with, or a conflict nobody confirmed, is an answer - so the status
    says the request was understood and the BODY says what happened to each
    code. A 4xx here would throw away the per-row detail that makes partial
    success readable.
    """
    record = svc.get_reading(db, reading_id)
    result = dimension_apply_service.apply_dimensions(
        db,
        record,
        codes=payload.codes,
        overwrite_conflicts=payload.overwrite_conflicts,
        user_id=_user_id(user),
    )
    return DimensionApplyOut(
        applied=[
            AppliedDimensionOut(
                code=entry.code,
                product_code=entry.product_code,
                product_name=entry.product_name,
                pages=list(entry.pages),
                length_mm=float(entry.length_mm),
                width_mm=float(entry.width_mm),
                height_mm=float(entry.height_mm),
                previous_length_mm=(
                    float(entry.previous_length_mm)
                    if entry.previous_length_mm is not None
                    else None
                ),
                previous_width_mm=(
                    float(entry.previous_width_mm)
                    if entry.previous_width_mm is not None
                    else None
                ),
                previous_height_mm=(
                    float(entry.previous_height_mm)
                    if entry.previous_height_mm is not None
                    else None
                ),
                was_conflict=entry.was_conflict,
            )
            for entry in result.applied
        ],
        refused=[
            RefusedDimensionOut(code=entry.code, reason=entry.reason, message=entry.message)
            for entry in result.refused
        ],
        applied_count=len(result.applied),
        refused_count=len(result.refused),
    )


@router.delete("/flyer-readings/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flyer_reading(
    reading_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    svc.delete_reading(db, reading_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
