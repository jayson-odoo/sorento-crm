"""Upload channels for the Order Inquiry sheet, and the link report.

The SO/PO history importers this file used to also route (`purchase-history` /
`sales-history` preview+apply) were RETIRED at ingest-parity-standardisation
S4 (AC-P4-1): closed history now arrives through the ESB's own document
ingest, the same channel that carries live orders, rather than a separate
banded-report upload nobody re-runs after the first backfill. See
`documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md`
section 10 for the contract this retirement is part of.

The two `/order-inquiry/*` routes are a thin SHIM onto Project Sales. Per ADR 0010 the Order
Inquiry loop is owned by that module and its importer lives in
`app/services/project_order_inquiry_import_service.py`, but the URL and the `scm.reorder.run`
permission stay here and stay stable, because the FE upload dialog calls them. Moving the
routes into the projects namespace is a recorded follow-up, not part of the ownership move.

Preview/apply is a two-step upload for the same reason the outstanding channel is: the whole
plan is computed from this data, so nothing is ever written from a single click. Preview is
synchronous (the operator is waiting for the answer); apply is a QUEUED import job, since a
large sheet can time the gateway out mid-write.
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
from app.services.scm import order_link_service
from app.services.scm.upload_intake import RetainedUpload, read_upload, read_upload_retained

router = APIRouter()

# Same capability as the outstanding upload: this file rewrites what the plan is computed
# from, so it sits behind the operator permission rather than the read one.
_WRITE = require_permission("scm.reorder.run")


def _require_single_company(db: Session) -> str:
    """Refuse to read or write this sheet without one company to read it against.

    On a WRITE the reason is ownership: this feed writes project demand, stock locations
    and purchase-order claims - owned rows - and a worker with no single company either
    fails closed part-way through or writes across the partition.

    On a READ (preview, and `?validate_only=true`) the reason is that the answer would be
    untrue. The reader resolves item codes, debtor codes and warehouses to ids through
    last-write-wins dicts, and 11,390 product codes are held by more than one company - so
    an all-companies read matches a line against whichever company's row came out of the
    query last, and reports counts about rows the apply would never touch. Same refusal on
    both steps for the same reason the customer importer refuses both
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
