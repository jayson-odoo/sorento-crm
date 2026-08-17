"""Propose product specifications from a flyer, review them, apply what was ticked.

Four routes, all under the dealer kit because the flyer is the dealer kit's object -
they sit beside `dimensions/apply`, which is the same shape of act: read the Kit, write
the master.

**Two permissions, and neither on its own**, declared in the order
`dealer_kit.page.view` then `master_data.products.edit` (L9, the precedent
`apply_flyer_dimensions` set). These routes leave the Kit: they write
`product_specifications`, which the ranker, the catalogue and the AI assistant all read
from. So the authority to write is the master-data slug, and the dealer-kit slug is only
the right to see the flyer being written FROM. Declared in that order so the 403 a
designer sees names the permission they are actually missing. No API-key variant on any
of them: this is a master-data write, and the shared external key acting as a user is
not the principal for one.

**The static path is declared FIRST**, and this router is included BEFORE
`flyer_readings.router`, because `GET /flyer-readings/{reading_id}` would otherwise
match `/flyer-readings/spec-proposal-batches` and answer 404 for a reading called
"spec-proposal-batches".

**200 with refusals, never a 4xx for a refused row.** A row the master already agrees
with, or one that disagrees with a value somebody set, is an answer - so the status says
the request was understood and the BODY says what happened to each row. A 4xx here would
throw away the per-row detail that makes partial success readable.

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.4.
UAC: `flyer-spec-ingestion-acceptance-criteria.md` AC-A.1, A.5, A.7, B.1, B.2, C.1-C.7.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.product_spec import ProductSpecFlyerBatch
from app.schemas.dealer_kit import (
    AppliedFlyerSpecOut,
    FlyerSpecApplyIn,
    FlyerSpecApplyOut,
    FlyerSpecBatchOut,
    FlyerSpecProductGroupOut,
    FlyerSpecProposalOut,
    FlyerSpecProposalsOut,
    RefusedFlyerSpecOut,
)
from app.services import product_spec_flyer_ingest as ingest
from app.services.dealer_kit import flyer_reading_service as svc
from app.services.error_handler import AppException

router = APIRouter()

# The two halves of writing the master from a flyer. See the module docstring.
_READ_THE_FLYER = require_permission("dealer_kit.page.view")
_WRITE_THE_MASTER = require_permission("master_data.products.edit")


def _user_id(user: dict | None) -> Optional[str]:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _summary(
    batch: Optional[ProductSpecFlyerBatch],
    record,
    names: dict[str, str],
    *,
    reading_id: Optional[str] = None,
) -> FlyerSpecBatchOut:
    """The ONE builder for a batch, list row and page header alike.

    Which is why every field goes through here: a column that reaches one builder and
    not the other is a value the screen shows on one page and not the other, and this
    repository has paid for that twice already (`get_user`, `system_settings`).

    A missing batch is not a missing answer. It is `status: "none"` with zero counts,
    because the reading page renders this section whatever the answer is.
    """
    if batch is None:
        return FlyerSpecBatchOut(
            id=None,
            reading_id=str(reading_id or record.id),
            filename=record.filename,
            status="none",
            read_at=record.created_at,
        )

    return FlyerSpecBatchOut(
        id=str(batch.id),
        reading_id=str(batch.flyer_reading_id),
        filename=record.filename,
        status=batch.status,
        error_message=batch.error_message,
        product_count=batch.product_count,
        proposal_count=batch.proposal_count,
        new_count=batch.new_count,
        change_count=batch.change_count,
        conflict_count=batch.conflict_count,
        unchanged_count=batch.unchanged_count,
        suppressed_count=batch.suppressed_count,
        applied_count=batch.applied_count,
        read_at=record.created_at,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        applied_at=batch.applied_at,
        created_by_name=names.get(str(batch.created_by)) if batch.created_by else None,
        applied_by_name=names.get(str(batch.applied_by)) if batch.applied_by else None,
    )


@router.get(
    "/flyer-readings/spec-proposal-batches", response_model=list[FlyerSpecBatchOut]
)
def list_flyer_spec_batches(
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    _writer: dict = Depends(_WRITE_THE_MASTER),
):
    """Every proposal pass, newest first. The Master Data list screen is this call.

    Declared before the `{reading_id}` routes so the static path wins.

    It carries the flyer's own name and the day it was read, so a merchandiser finds a
    batch without going through the Kit and the list needs no second call per row.
    """
    pairs = ingest.list_batches(db)
    names = ingest.user_names(
        db, [batch.created_by for batch, _ in pairs] + [batch.applied_by for batch, _ in pairs]
    )
    return [_summary(batch, record, names) for batch, record in pairs]


@router.post(
    "/flyer-readings/{reading_id}/spec-proposals",
    response_model=FlyerSpecBatchOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def propose_flyer_specs(
    reading_id: str,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    user: dict = Depends(_WRITE_THE_MASTER),
):
    """Ask for a proposal pass over this reading (AC-A.1).

    **202 and the batch, not 200 and the proposals.** The pass runs on the worker, on
    the same queue as the read, so this returns before it starts and the screen polls
    the GET below every three seconds until it settles.

    409 when the reading is not read yet, in the same words the seed and the sizes
    apply use, and 409 when a pass is already running for this reading - two passes over
    one reading would race to write the same rows and one of them would lose silently.

    Pressing it again on a settled batch re-proposes: the old rows go and the pass runs
    against the master as it is NOW. That is the point of pressing it again (AC-A.5).
    """
    record = svc.get_reading(db, reading_id)
    batch = ingest.start_batch(db, record, user_id=_user_id(user))
    names = ingest.user_names(db, [batch.created_by, batch.applied_by])
    return _summary(batch, record, names)


@router.get(
    "/flyer-readings/{reading_id}/spec-proposals", response_model=FlyerSpecProposalsOut
)
def get_flyer_spec_proposals(
    reading_id: str,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    _writer: dict = Depends(_WRITE_THE_MASTER),
):
    """The batch for one reading, and its rows when there are any (AC-B.1).

    Answers on every state, including "nobody has proposed from this flyer", which
    comes back as `status: "none"` rather than a 404: the reading page renders this
    section whatever the answer is, and a 404 there would read as a broken screen.

    The rows arrive grouped by PRODUCT and in flyer page order, because the reviewer is
    holding the paper and works through it product by product.
    """
    record = svc.get_reading(db, reading_id)
    batch = ingest.batch_for(db, record)
    names = (
        ingest.user_names(db, [batch.created_by, batch.applied_by]) if batch else {}
    )
    summary = _summary(batch, record, names, reading_id=reading_id)

    groups: list[FlyerSpecProductGroupOut] = []
    if batch is not None and batch.status == ingest.PROPOSED:
        groups = [
            FlyerSpecProductGroupOut(
                product_id=group["product_id"],
                product_code=group["product_code"],
                product_name=group["product_name"],
                pages=group["pages"],
                proposals=[FlyerSpecProposalOut(**row) for row in group["proposals"]],
            )
            for group in ingest.grouped_proposals(db, batch)
        ]

    return FlyerSpecProposalsOut(**summary.model_dump(), groups=groups)


@router.post(
    "/flyer-readings/{reading_id}/spec-proposals/apply", response_model=FlyerSpecApplyOut
)
def apply_flyer_spec_proposals(
    reading_id: str,
    payload: FlyerSpecApplyIn,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    user: dict = Depends(_WRITE_THE_MASTER),
):
    """Write the ticked proposals onto the products the flyer names (AC-C.1).

    The request names proposal ids and never values: the values come off the stored
    proposals, which came off the reading. That is the whole security model of this
    route, and it is the same one `dimension_apply_service` has.

    Every ticked row is re-classified against the LIVE spec row before anything is
    written, so a batch proposed yesterday cannot overwrite what somebody set this
    morning, and re-applying the same flyer writes nothing at all.

    200 with per-row outcomes rather than a 4xx: see the module docstring.
    """
    record = svc.get_reading(db, reading_id)
    batch = ingest.batch_for(db, record)
    if batch is None:
        raise AppException(
            status_code=404,
            message=(
                "Nobody has proposed specifications from this flyer yet, so there is "
                "nothing to apply."
            ),
            code="FLYER_SPEC_NO_BATCH",
        )

    result = ingest.apply_batch(
        db,
        batch,
        record,
        proposal_ids=[str(value) for value in payload.proposal_ids],
        user=user,
    )
    return FlyerSpecApplyOut(
        applied=[
            AppliedFlyerSpecOut(
                proposal_id=entry.proposal_id,
                product_code=entry.product_code,
                spec_key=entry.spec_key,
                value=entry.value,
            )
            for entry in result.applied
        ],
        refused=[
            RefusedFlyerSpecOut(
                proposal_id=entry.proposal_id,
                product_code=entry.product_code,
                spec_key=entry.spec_key,
                reason=entry.reason,
                message=entry.message,
            )
            for entry in result.refused
        ],
    )
