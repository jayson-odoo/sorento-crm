"""Upload a printed flyer, get the match report back (S7.3).

The only surface of the seeding feature a designer touches before the review
screen: drop the PDF in, see what the system found.

**Permissions reuse the page split.** Reading a flyer into the Kit is drafting a
catalogue, so writes carry ``dealer_kit.page.edit`` and reads carry
``dealer_kit.page.view``. No new slug: a fourth one would need a grant sweep
migration before a single existing role held it, and every designer who can
build a page can already do everything this feature leads to.

**Extraction happens inside the request.** The real 36 page flyer takes about a
second, so a job queue would add a pending state, a polling screen, a failure
path and a worker restart per code change, and buy nothing. The reasoning stops
holding at roughly ten seconds of extraction - a much larger document, or the
artwork rasterisation coming in S7.5 - at which point this becomes an enqueue
returning 202 with a row to watch, like the catalogue PDF export.

**The report is never stored.** It is derived from the stored reading against
the master, on every read. See ``flyer_reading_service``.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.dealer_kit import (
    CodeSuggestionOut,
    DimensionCandidateOut,
    FlyerReadingOut,
    FlyerReadingSummary,
    FlyerSeedIn,
    FlyerSeedOut,
    MatchReportOut,
    MatchedCodeOut,
    UnmatchedCodeOut,
)
from app.services.dealer_kit import flyer_reading_service as svc
from app.services.dealer_kit import flyer_seed_service as seed_service
from app.services.dealer_kit import page_service

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")

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
    response_model=FlyerReadingOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_flyer_reading(
    file: UploadFile = File(...),
    promotion_id: Optional[UUID] = _PROMOTION_ID,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    data = await _read_within_limit(file)
    record = svc.create_reading(
        db, filename=file.filename, data=data, user_id=_user_id(user)
    )
    return _detail(db, record, promotion_id)


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


@router.delete("/flyer-readings/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flyer_reading(
    reading_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    svc.delete_reading(db, reading_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
