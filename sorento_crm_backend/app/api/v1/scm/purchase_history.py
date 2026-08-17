"""Upload channels for purchase history and the Order Inquiry sheet, and the link report.

Separate routes rather than another `kind` on the outstanding importer, because these are
different SHAPES, not another spelling of the same table. The outstanding channel reads a flat
table through the alias resolver; the PO listing is a banded report of header-and-line blocks,
and the Order Inquiry sheet is a book of monthly tabs. Forcing them through one `kind`
parameter would mean one route whose branches have nothing in common.

Preview/apply is the same two-step as the outstanding channel and for the same reason: the
whole plan is computed from this data, so nothing is ever written from a single click. And as
there, preview is synchronous (the operator is waiting for the answer) while apply is a
QUEUED import job: the sales book is 81,361 lines in the client's own export and it timed the
gateway out mid-write, which is exactly what the imports queue exists to stop.

Every write resolves the SO<->PO claims afterwards - inside the job now, not the request - so
the linkage is still formed by whichever upload completes the pair.

The two `/order-inquiry/*` routes are a thin SHIM onto Project Sales. Per ADR 0010 the Order
Inquiry loop is owned by that module and its importer lives in
`app/services/project_order_inquiry_import_service.py`, but the URL and the `scm.reorder.run`
permission stay here and stay stable, because the FE upload dialog calls them. Moving the
routes into the projects namespace is a recorded follow-up, not part of the ownership move.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services import project_order_inquiry_import_service as order_inquiry_service
from app.services.job_service import JobService, active_company_id_from_scope
from app.services.queue_service import enqueue_job
from app.services.scm import (
    order_link_service,
    po_history_service,
    so_history_service,
)
from app.services.scm.upload_intake import RetainedUpload, read_upload, read_upload_retained

router = APIRouter()

# Same capability as the outstanding upload: these files rewrite what the plan is computed
# from, so they sit behind the operator permission rather than the read one.
_WRITE = require_permission("scm.reorder.run")


def _require_single_company(db: Session) -> str:
    """Refuse to read or write these books without one company to read them against.

    On a WRITE the reason is ownership: these feeds write `sales_orders` /
    `purchase_orders`, which are owned tables, and a worker with no single company either
    fails closed part-way through or writes across the partition.

    On a READ (preview, and `?validate_only=true`) the reason is that the answer would be
    untrue. Every one of these readers resolves item codes, debtor codes and warehouses to
    ids through last-write-wins dicts, and 11,390 product codes are held by more than one
    company - so an all-companies read matches a line against whichever company's row came
    out of the query last, and reports counts about rows the apply would never touch. Same
    refusal on both steps for the same reason the customer importer refuses both
    (`order_management/customers.py`): a preview that cannot be trusted is worse than none.
    """
    company_id = active_company_id_from_scope(db)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a single company before uploading this file.",
        )
    return company_id


def _queue(db: Session, *, upload: RetainedUpload, job_type: str, task, user_id: str,
           message: str) -> dict:
    """Create the job row, retain the operator's own file, and hand it to the worker.

    One helper for all three channels: they differ in which task runs, and in nothing else.
    The company refusal is FIRST and before any job row, so a refused upload leaves no
    half-made job behind.
    """
    company_id = _require_single_company(db)

    from app.services.import_source_store import store_import_source_file

    job_service = JobService(db)
    job = job_service.create_job(
        job_type=job_type,
        user_id=user_id,
        filename=upload.filename,
        company_id=company_id,
    )
    store_import_source_file(job, upload.source_bytes, upload.source_name,
                             upload.content_type)
    db.commit()
    rq_job = enqueue_job(
        task,
        str(job.id),
        upload.data,
        upload.filename,
        user_id,
        queue_name="imports",
        job_timeout=3600,
        job_id=str(job.job_id),  # pre-assign RQ id = DB job_id; see update_job_with_rq_id
    )
    job_service.update_job_with_rq_id(job, rq_job.id)
    return {"message": message, "job_id": job.job_id, "id": str(job.id)}


@router.post("/purchase-history/preview")
async def preview_purchase_history(
    file: UploadFile = File(
        ...,
        description="AutoCount Purchase Order Listing With Detail, or the flat PO + SPO "
                    "history extract. Which one it is is read off the header row.",
    ),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this order book would write. Writes nothing.

    A file that cannot be read comes back 200 carrying `ok: false` and its problems, not an
    error, because the screen has to render WHICH part failed for the export to be fixed and
    an exception body would lose that.

    One channel, two file shapes and two document families: purchase orders and shipping
    orders (`SPO-...`) are split on the Doc No prefix and counted separately on the answer
    (`orders_po` / `orders_spo`).

    This is HISTORY, not outstanding supply: neither export carries a received or outstanding
    column this channel reads, so every line is written closed and fully received and can
    never read as stock on its way in.

    Refused without a single active company: read across every company the item and creditor
    codes resolve to the wrong company's rows, so the counts describe a book nobody has.
    """
    _require_single_company(db)
    return po_history_service.preview(db, await read_upload(file))


@router.post("/purchase-history/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_purchase_history(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Queue the order book. Idempotent on the document number.

    `?validate_only=true` is unchanged and still synchronous: it writes nothing and the
    operator is waiting for the verdict. Without it the file is queued and the answer lands on
    the job, so an unreadable file fails the JOB with its problems rather than the request.

    Both branches refuse without a single active company: the Test verdict is read at the
    same scope the write would run at, or it is a verdict about a different book.
    """
    if validate_only:
        _require_single_company(db)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(po_history_service.validate(db, await read_upload(file))),
        )

    from app.tasks.import_tasks import process_po_history_import

    return _queue(
        db,
        upload=await read_upload_retained(file),
        job_type="po_history_import",
        task=process_po_history_import,
        user_id=current_user["id"],
        message="Purchase history upload queued.",
    )


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

    Refused without a single active company: those two counts are the whole point of the
    screen, and read across every company they are counts about somebody else's catalogue.
    """
    _require_single_company(db)
    return so_history_service.preview(db, await read_upload(file))


@router.post("/sales-history/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_sales_history(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Queue the sales book as history. Idempotent on the document number.

    Every line is written closed and fully delivered, so absorbed history contributes NOTHING
    to committed demand: measured on the client's own 11,275-document export, absorbing it
    left `scm.committed_v` and `scm.net_position_v` byte-identical. A document that already
    exists and was not created by this feed is left untouched, so a live commitment somebody
    is working can never be closed by a six-year-old export.

    This is the channel that proved the point: 81,361 lines written inside one request is a
    504 and a half-written book. It goes on the queue.
    """
    from app.tasks.import_tasks import process_sales_history_import

    return _queue(
        db,
        upload=await read_upload_retained(file),
        job_type="sales_history_import",
        task=process_sales_history_import,
        user_id=current_user["id"],
        message="Sales history upload queued.",
    )


# Project Sales owns what these two routes call (ADR 0010). The path stays under /scm so the
# FE upload dialog is unaffected by the ownership move.
@router.post("/order-inquiry/preview")
async def preview_order_inquiry(
    file: UploadFile = File(..., description="Order Inquiry sheet"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this sheet would write. Writes nothing.

    Refused without a single active company: the sheet is matched against sales orders,
    products and warehouses, and read across every company it matches the wrong ones.
    """
    _require_single_company(db)
    return order_inquiry_service.preview(db, await read_upload(file))


@router.post("/order-inquiry/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_order_inquiry(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Queue the sheet: project demand, stock locations, and the purchase-order claims.

    Both branches refuse without a single active company, for the same reason preview does.
    """
    if validate_only:
        _require_single_company(db)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                order_inquiry_service.validate(db, await read_upload(file))
            ),
        )

    from app.tasks.import_tasks import process_order_inquiry_import

    return _queue(
        db,
        upload=await read_upload_retained(file),
        job_type="order_inquiry_import",
        task=process_order_inquiry_import,
        user_id=current_user["id"],
        message="Order inquiry upload queued.",
    )


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
