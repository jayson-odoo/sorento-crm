"""Upload channels for purchase history and the Order Inquiry sheet, and the link report.

Separate routes rather than another `kind` on the outstanding importer, because these are
different SHAPES, not another spelling of the same table. The outstanding channel reads a flat
table through the alias resolver; the PO listing is a banded report of header-and-line blocks,
and the Order Inquiry sheet is a book of monthly tabs. Forcing them through one `kind`
parameter would mean one route whose branches have nothing in common.

Preview/apply is the same two-step as the outstanding channel and for the same reason: the
whole plan is computed from this data, so nothing is ever written from a single click.

Every write route resolves the SO<->PO claims afterwards, so the linkage is formed by whichever
upload happens to complete the pair - which is the point of the claim table.

The two `/order-inquiry/*` routes are a thin SHIM onto Project Sales. Per ADR 0010 the Order
Inquiry loop is owned by that module and its importer lives in
`app/services/project_order_inquiry_import_service.py`, but the URL and the `scm.reorder.run`
permission stay here and stay stable, because the FE upload dialog calls them. Moving the
routes into the projects namespace is a recorded follow-up, not part of the ownership move.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services import project_order_inquiry_import_service as order_inquiry_service
from app.services.scm import (
    order_link_service,
    po_history_service,
    so_history_service,
)
from app.services.scm.upload_intake import read_upload

router = APIRouter()

# Same capability as the outstanding upload: these files rewrite what the plan is computed
# from, so they sit behind the operator permission rather than the read one.
_WRITE = require_permission("scm.reorder.run")


def _reject_unreadable(out: dict) -> None:
    """Apply refuses a file it could not read. Preview does NOT - see below."""
    if out.get("ok"):
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="; ".join(out.get("problems") or ["This file could not be read."]),
    )


@router.post("/purchase-history/preview")
async def preview_purchase_history(
    file: UploadFile = File(..., description="AutoCount Purchase Order Listing With Detail"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this order book would write. Writes nothing.

    A file that cannot be read comes back 200 carrying `ok: false` and its problems, not an
    error, because the screen has to render WHICH part failed for the export to be fixed and
    an exception body would lose that.

    This is HISTORY, not outstanding supply: the report carries what was ordered and has no
    received or outstanding column at all, so the lines are written closed and fully received
    and can never read as stock on its way in.
    """
    return po_history_service.preview(db, await read_upload(file))


@router.post("/purchase-history/apply")
async def apply_purchase_history(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Write the order book. Idempotent on the document number.

    `?validate_only=true` is the Test the rest of this system's importers already have
    (`import-tracking`, the GRN import). Same query parameter, same response shape, so a Test
    means the same thing wherever somebody presses it - and the verdict is derived from the
    same read `apply` performs, so the two cannot disagree.
    """
    data = await read_upload(file)
    if validate_only:
        return po_history_service.validate(db, data)
    out = po_history_service.apply(db, data, actor=current_user.get("id"))
    _reject_unreadable(out)
    # The notes in this file name sales orders, so an upload can complete a pairing the other
    # side claimed months ago.
    out["links"] = order_link_service.resolve(db)
    db.commit()
    return out


@router.post("/sales-history/preview")
async def preview_sales_history(
    file: UploadFile = File(..., description="AutoCount sales-order detail listing"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this sales book would absorb. Writes nothing.

    Read the counts before pressing apply, because two of them decide whether this is even
    the right channel. `outstanding_lines` above zero means the file still holds real
    commitments, which belong to the outstanding upload - this one records finished business.
    `unknown_item_count` and `unknown_debtor_count` say how much of the book will land
    unattributed.
    """
    return so_history_service.preview(db, await read_upload(file))


@router.post("/sales-history/apply")
async def apply_sales_history(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Absorb the sales book as history. Idempotent on the document number.

    Every line is written closed and fully delivered, so absorbed history contributes NOTHING
    to committed demand: measured on the client's own 11,275-document export, absorbing it
    left `scm.committed_v` and `scm.net_position_v` byte-identical. A document that already
    exists and was not created by this feed is left untouched, so a live commitment somebody
    is working can never be closed by a six-year-old export.
    """
    out = so_history_service.apply(db, await read_upload(file), actor=current_user.get("id"))
    db.commit()
    return out


# Project Sales owns what these two routes call (ADR 0010). The path stays under /scm so the
# FE upload dialog is unaffected by the ownership move.
@router.post("/order-inquiry/preview")
async def preview_order_inquiry(
    file: UploadFile = File(..., description="Order Inquiry sheet"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this sheet would write. Writes nothing."""
    return order_inquiry_service.preview(db, await read_upload(file))


@router.post("/order-inquiry/apply")
async def apply_order_inquiry(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Write the stock locations and claim the purchase-order links."""
    data = await read_upload(file)
    if validate_only:
        return order_inquiry_service.validate(db, data)
    out = order_inquiry_service.apply(db, data, actor=current_user.get("id"))
    _reject_unreadable(out)
    out["links"] = order_link_service.resolve(db)
    db.commit()
    return out


@router.get("/order-links/open")
def get_open_order_links(
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Pairings still waiting for one side to be uploaded.

    Reported rather than kept as a silence: "34 sales orders name a purchase order we have not
    seen" is how somebody finds out the PO book is a month behind, and there is no other way
    to find it out.
    """
    return order_link_service.open_claims(db)
