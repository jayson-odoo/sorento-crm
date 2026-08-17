"""Propose product specifications from a flyer, review them, apply what was ticked.

Seven routes, all under the dealer kit because the flyer is the dealer kit's object -
they sit beside `dimensions/apply`, which is the same shape of act: read the Kit, write
the master. Four of them are the propose-read-apply loop; the other three are what makes
the review screen the whole act rather than a staging post - correct a value the reader
misread, add a key it never caught, dismiss a row that belongs to the neighbouring card
(UAC sections F and G). All three write PROPOSALS. The apply is still the only way onto
the product master, and it still names ids only.

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
UAC: `flyer-spec-ingestion-acceptance-criteria.md` AC-A.1, A.5, A.7, B.1, B.2, C.1-C.7,
F.1, F.2, F.5, G.1-G.3.
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
    FlyerSpecProposalEditIn,
    FlyerSpecProposalOut,
    FlyerSpecProposalRowIn,
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


def _settled_batch(db: Session, reading_id: str):
    """`(reading, batch)` for a batch there is something to do to, or the refusal.

    Every act that names a row of a batch - apply, edit, add, dismiss - needs the same
    two facts first and refuses on the same two conditions, in the same words: nobody
    has proposed from this flyer (404), or a pass is running / did not finish so its
    rows are not the rows the caller is looking at (409). One helper because four
    copies of a refusal are four sets of words that drift.
    """
    record = svc.get_reading(db, reading_id)
    batch = ingest.batch_for(db, record)
    if batch is None:
        raise AppException(
            status_code=404,
            message=(
                "Nobody has proposed specifications from this flyer yet, so there is "
                "nothing to review."
            ),
            code="FLYER_SPEC_NO_BATCH",
        )
    ingest.assert_proposed(batch)
    return record, batch


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

    200 with per-row outcomes rather than a 4xx: see the module docstring. The one
    exception is a batch that is not `proposed` - mid-re-propose or failed - which is
    409 `FLYER_SPEC_NOT_PROPOSED`, because its rows are not the rows the caller ticked.
    """
    record, batch = _settled_batch(db, reading_id)

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


@router.patch(
    "/flyer-readings/{reading_id}/spec-proposals/{proposal_id}",
    response_model=FlyerSpecProposalOut,
)
def edit_flyer_spec_proposal(
    reading_id: str,
    proposal_id: str,
    payload: FlyerSpecProposalEditIn,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    user: dict = Depends(_WRITE_THE_MASTER),
):
    """Correct what the reader made of a card, in place (AC-F.2).

    A reader that gets one value wrong is not a reason to leave the review screen, open
    the product, type it there and come back - that round trip is what stops a
    merchandiser using the screen at all. So the correction is stored on the PROPOSAL,
    validated against the registry exactly as the write choke point would validate it,
    and the apply still names ids only.

    The answer is the whole row back, because its `kind` may have changed: correcting a
    value to what the product already holds turns it `unchanged`, and the screen must
    stop offering to write it.
    """
    _record, batch = _settled_batch(db, reading_id)
    row = ingest.proposal_in(db, batch, proposal_id)
    return FlyerSpecProposalOut(
        **ingest.edit_proposal(db, batch, row, value=payload.value, user=user)
    )


@router.delete(
    "/flyer-readings/{reading_id}/spec-proposals/{proposal_id}",
    response_model=FlyerSpecBatchOut,
)
def dismiss_flyer_spec_proposal(
    reading_id: str,
    proposal_id: str,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    _writer: dict = Depends(_WRITE_THE_MASTER),
):
    """Take a proposal off the batch (AC-G.3).

    A HARD delete: the row is a proposal nobody accepted, and a dismissed-but-present
    one is exactly the sort of state a reviewer has to re-decide about every visit. A
    row that was already written is refused 409 - what is on the product is changed on
    the product's own Specifications tab.

    It answers with the batch summary rather than nothing, so the screen's counts move
    with the row it just removed.
    """
    record, batch = _settled_batch(db, reading_id)
    row = ingest.proposal_in(db, batch, proposal_id)
    ingest.delete_proposal(db, batch, row)
    names = ingest.user_names(db, [batch.created_by, batch.applied_by])
    return _summary(batch, record, names)


@router.post(
    "/flyer-readings/{reading_id}/spec-proposals/rows",
    response_model=FlyerSpecProposalOut,
    status_code=status.HTTP_201_CREATED,
)
def add_flyer_spec_proposal_row(
    reading_id: str,
    payload: FlyerSpecProposalRowIn,
    db: Session = Depends(get_db),
    _reader: dict = Depends(_READ_THE_FLYER),
    user: dict = Depends(_WRITE_THE_MASTER),
):
    """Add a specification the flyer states in a way no rule caught (AC-G.1).

    The product must already be in this batch and the key must be one the registry
    defines AND one this product's class can carry - the same scope gate the propose
    pass applies, so a reviewer cannot hand-place a key the pass would have dropped.

    The row is `manual`, which is the one thing that makes it apply as `human` with
    "set during flyer review" as its evidence: a person typed it, and badging it `Flyer`
    would be a claim about a document that never said it (AC-G.2).
    """
    _record, batch = _settled_batch(db, reading_id)
    return FlyerSpecProposalOut(
        **ingest.add_proposal_row(
            db,
            batch,
            product_id=payload.product_id,
            spec_key=payload.spec_key,
            value=payload.value,
            user=user,
        )
    )
