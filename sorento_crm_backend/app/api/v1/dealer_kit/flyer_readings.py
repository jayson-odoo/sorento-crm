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

**The request never reads the flyer. It answers 202 and queues the read.**
Measured on the real ``_SORENTO A3 FLYER 2025-2026_compressed.pdf`` (20.1 MB, 36
A3 pages, 998 codes) on a quiet machine, ``extract_flyer`` alone takes 17 to 18
seconds, and the whole POST 40 to 60 seconds on a loaded one. This module used
to claim "about a second", and that number was the entire justification for
doing the work in the request - so it is written down here as measured, with
what it was measured against, rather than as a recollection.

Getting it wrong cost two separate things, in this order. First, the upload
handler was ``async def`` and the read ran ON the loop, so one flyer froze its
whole gunicorn worker: a ``GET /health`` issued during a read waited **57.5
seconds** on a single worker. PR #164 fixed that with ``run_in_threadpool``, and
deliberately left the duration alone. The duration then produced the second
failure on its own: the captain's read came back as ``Gateway timeout (504)``,
a proxy in front of the backend giving up while FastAPI was still extracting.
Raising that timeout fixes one flyer and re-breaks on the next bigger one, and
it keeps a designer staring at a disabled button for a minute either way.

So the read is now an RQ job on the ``flyer_read`` queue, following the shape
the catalogue PDF export already uses. Both POSTs answer **202** with the
reading in ``processing``, carrying the id the finished reading will have, so
the Flyers list shows the row from the first second and the report link never
changes. What still runs in the request is only what cannot wait: the ceiling as
the bytes arrive, the refusals that need nothing but the attachment row, staging
an upload's bytes, and the INSERT. Everything the bytes alone can reveal lands
on the row as ``failed`` with the reason, which the list and the review screen
both show.

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
    CodeOverrideIn,
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
from app.services.error_handler import AppException

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
        adopted=entry.adopted,
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
    """The ONE builder for a row, list and detail alike.

    Which is why the three lifecycle fields go in here and nowhere else: a
    column that reaches only one of the two builders is a column the screen
    shows on one page and not the other, and this repository has paid for that
    twice already (``get_user``, ``system_settings``).

    ``status`` falls back to ``done`` for a row read out of a database that has
    not taken migration 359 yet. Those rows were all read synchronously and
    successfully, so it is what happened to them rather than a guess.
    """
    return FlyerReadingSummary(
        id=record.id,
        filename=record.filename,
        byte_size=record.byte_size,
        page_count=svc.page_count(record),
        code_count=svc.code_count(record),
        uploaded_at=record.created_at,
        status=getattr(record, "status", None) or svc.ReadingStatus.DONE,
        error_message=getattr(record, "error_message", None),
        finished_at=getattr(record, "finished_at", None),
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
        code_overrides_changed_at=getattr(record, "code_overrides_changed_at", None),
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


@router.post(
    "/flyer-readings",
    response_model=FlyerReadingSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_flyer_reading(
    file: UploadFile = File(...),
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """A flyer off the designer's laptop, queued for the worker.

    **202 and a summary, not 201 and a report.** The report does not exist yet:
    the read is 18 seconds of PyMuPDF on the real flyer and it happens on the
    worker. What comes back is the row, in ``processing``, carrying the id the
    finished reading will have - so the dialog closes at once, the Flyers list
    shows the row immediately, and the link to the report is the same URL from
    the first second to the last.

    Still ``async def``, and that is the one thing about this route that must not
    change: ``_read_within_limit`` needs ``await file.read(...)`` to refuse an
    oversized upload as the bytes arrive rather than after they are all in
    memory. Everything after it - hashing 20 MB, the PUT that stages the bytes
    where the worker can reach them, the INSERT - is synchronous, so it goes to
    ``run_in_threadpool`` exactly as the extraction used to (AC-K1).

    ``promotionId`` is still accepted and still validated at the edge, even
    though there is no report on this response to compute against: the frontend
    sends it with the upload, and a malformed uuid reaching a WHERE clause is
    how this feature produced a 500 once. The report is asked for on the GET.
    """
    data = await _read_within_limit(file)
    record = await run_in_threadpool(
        svc.enqueue_reading_from_upload,
        db,
        filename=file.filename,
        data=data,
        user_id=_user_id(user),
    )
    return _summary(record)


@router.post(
    "/flyer-readings/from-attachment",
    response_model=FlyerReadingSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def read_flyer_from_attachment(
    payload: FlyerReadingFromAttachmentIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """A flyer the system is already holding, queued for the worker.

    Marketing files the season's flyer in Resource Management long before
    anybody thinks about the Kit, so the alternative to this route is a designer
    downloading a 20 MB PDF out of the CRM to upload it straight back in.

    **202, before a single byte is fetched.** This path touches storage not at
    all: everything it refuses, it refuses on the attachment ROW - out of scope
    or trashed is a 404, a file the library already says is not a PDF is a 400,
    a recorded size over the ceiling is a 413, a row naming no stored object is
    a 422. The order matters and lives in the service; see
    ``flyer_reading_service.assert_attachment_readable``.

    Plain ``def``, so FastAPI runs it in a thread. It is metadata and one INSERT
    now rather than a download and an extraction, but the rule that no handler
    here does synchronous work on the loop does not change with the workload.

    ``dealer_kit.page.edit``, declared the same way as the upload, so a caller
    without it gets the same 403 naming the same slug. Nothing about the source
    of the bytes changes who may read a flyer.
    """
    record = svc.enqueue_reading_from_attachment(
        db, attachment_id=str(payload.attachment_id), user_id=_user_id(user)
    )
    return _summary(record)


# Refusing to build anything out of a flyer that has not been read yet. Lifted into
# the service (``flyer_reading_service.assert_read``) so the flyer-spec-proposal routes
# refuse in the SAME words rather than in a second copy of them; aliased here so the
# two call sites below read unchanged.
_assert_read = svc.assert_read


@router.get("/flyer-readings", response_model=list[FlyerReadingSummary])
def list_flyer_readings(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    """Which flyers have been read, newest first. No reports: see the schema.

    Every row carries ``status``, ``errorMessage`` and ``finishedAt``, because
    this is the screen a designer watches a read on. The frontend polls this
    while any row is Processing and stops when none is.
    """
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

    Answers on ANY status, deliberately. The row exists from the moment the POST
    returns, so the review screen has to be able to open it before the job has
    run - and a reading that has not happened yet has an empty reading, which
    matches nothing and reports nothing without a single special case here. The
    screen reads ``status`` and shows its waiting or failed state instead.
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
    _assert_read(record)
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
    _assert_read(record)
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


@router.put(
    "/flyer-readings/{reading_id}/code-overrides/{printed_code}",
    response_model=FlyerReadingOut,
)
def adopt_flyer_code(
    reading_id: str,
    printed_code: str,
    payload: CodeOverrideIn,
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    _writer: dict = Depends(_WRITE_THE_MASTER),
):
    """"This printed code IS that product" (PLAN-flyer-code-adopt.md, R1-R4).

    Same two permissions as applying a printed size, and for the same reason:
    this writes something a designer's dealer-kit authority alone does not
    cover - here, which product a card on the flyer means - so
    ``master_data.products.edit`` is required alongside ``dealer_kit.page.view``.

    200 with the full detail, not 204: the report changed, and the frontend
    replaces its cache with this response rather than refetching (no flash
    back to the stale row before the new one lands).

    ``promotionId`` travels the same way it does on the GET: the frontend is
    looking at one promotion's report and the response it swaps in must stay
    computed against it, or an adopted row that the promotion does not carry
    would read as promoted for one frame.
    """
    record = svc.get_reading(db, reading_id)
    updated = svc.adopt_code(
        db,
        record,
        printed_code=printed_code,
        product_id=str(payload.product_id),
    )
    return _detail(db, updated, promotion_id)


@router.delete(
    "/flyer-readings/{reading_id}/code-overrides/{printed_code}",
    response_model=FlyerReadingOut,
)
def undo_flyer_code_adoption(
    reading_id: str,
    printed_code: str,
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    _writer: dict = Depends(_WRITE_THE_MASTER),
):
    """Undo an adoption. Specs already applied to the product stay applied (R2).

    200 with the detail, for the same reason the PUT above answers 200: the
    code returns to `unmatched`, and the frontend replaces its cache with this
    response. ``promotionId`` travels the same way it does on the PUT above.
    """
    record = svc.get_reading(db, reading_id)
    updated = svc.unadopt_code(db, record, printed_code=printed_code)
    return _detail(db, updated, promotion_id)


@router.delete("/flyer-readings/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flyer_reading(
    reading_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    svc.delete_reading(db, reading_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
