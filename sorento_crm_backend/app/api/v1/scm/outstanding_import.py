"""Upload channel for outstanding orders, until AutoCount is integrated.

Two steps on purpose. `POST .../preview` says what would change and writes nothing;
`POST .../apply` writes it. Nothing is ever saved from a single click, because the whole
plan is built on this data and a wrong file quietly imported is a week of unpicking.

The two steps run in different places, and deliberately so. **Preview is synchronous**: the
operator is standing in front of the answer, and a job id they then have to poll would break
the one interaction that matters. **Apply is a queued import job** on the shared machinery
(`imports` queue, per-row outcomes, retained source file, the upload drawer) - because the
inline version was a request that wrote thousands of lines, and the sales book proved what
that costs by timing the gateway out mid-write. Nothing about the confirm step needs the
operator to keep the tab open.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.job_service import JobService, active_company_id_from_scope
from app.services.queue_service import enqueue_job
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO
from app.services.scm.upload_intake import (
    allowed_extensions,
    read_upload,
    read_upload_retained,
)

router = APIRouter()

# Uploading the open order book rewrites what the whole plan is computed from, so it sits
# behind the operator capability rather than the read one.
_WRITE = require_permission("scm.reorder.run")

_DOC_TYPES = {"sales-orders": SO, "purchase-orders": PO}

# The job type each book queues under. Named per book rather than one `outstanding_import`,
# because the two write different tables and the operator reading the import-jobs list is
# looking for the one they uploaded.
_JOB_TYPES = {SO: "outstanding_so_import", PO: "outstanding_po_import"}

# Document types `apply` can actually WRITE. Preview works for every readable type, because it
# only reads, but the write path must refuse anything it cannot persist correctly rather than
# persist it somewhere plausible-looking.
#
# This exists because it already went wrong: `apply` branched on doc_type only to pick a reader,
# then unconditionally constructed SalesOrder / SalesOrderLine. Uploading the purchase order book
# therefore created SALES orders whose so_number was the PO number - silent cross-table
# corruption that a reader-level doc_type check did nothing to stop. Keep this allow-list even
# after the PO write path lands: a type that can be read but not written must fail loudly.
_WRITABLE_DOC_TYPES = {SO, PO}


def _require_single_company(db: Session) -> str:
    """Refuse to read or write this book without one company to read it against.

    On `apply` the reason is ownership: `sales_orders` and `purchase_orders` are owned
    tables, so "whose order book is this?" has no answer and the worker would either fail
    closed part-way through or write across the partition.

    On PREVIEW the reason is that the answer would be untrue. `_resolve` builds
    `product_by_code` as a last-write-wins dict, and 11,390 product codes are held by more
    than one company - so an all-companies read binds a line to whichever company's product
    came out of the query last, and the diff on screen is about the wrong rows. The operator
    then confirms a diff they were shown and gets a different one, or a 400. Same refusal on
    both steps for the same reason the customer importer refuses both (customers.py): a
    preview that cannot be trusted is worse than no preview.
    """
    company_id = active_company_id_from_scope(db)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a single company before uploading the order book.",
        )
    return company_id


def _doc_type(kind: str) -> str:
    try:
        return _DOC_TYPES[kind]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown document type '{kind}'. Expected one of: "
                   f"{', '.join(sorted(_DOC_TYPES))}.",
        )


def _assert_writable(kind: str, doc_type: str) -> None:
    """Refuse `apply` for a type this route can read but not write.

    501 rather than 400: the request is well formed and authorized, and the file may be
    perfectly good - the server simply has no write path for this book yet, which is what
    501 means. A 400 would land in the same bucket as this route's other 400s ("your file
    is missing a column", "that is not an xlsx"), so the operator would go looking for a
    problem with their export that does not exist.
    """
    if doc_type in _WRITABLE_DOC_TYPES:
        return
    writable = ", ".join(sorted(k for k, v in _DOC_TYPES.items() if v in _WRITABLE_DOC_TYPES))
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Applying the {kind.replace('-', ' ')} book is not implemented yet. "
            f"Preview it to check the file; only {writable.replace('-', ' ')} can be applied."
        ),
    )


@router.get("/outstanding/config")
def get_outstanding_upload_config(_user: dict = Depends(_WRITE)):
    """What the upload dialog may offer, so the browser and the server agree.

    The dialog used to hard-code its own accept list, which is how it came to refuse a file
    the reader can parse perfectly well.
    """
    return {"allowed_extensions": list(allowed_extensions())}


@router.post("/outstanding/{kind}/preview")
async def preview_outstanding_import(
    kind: str,
    file: UploadFile = File(..., description="AutoCount outstanding-orders extract (.xlsx)"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What this file would change. Writes nothing.

    Refused without a single active company all the same: a preview read across every
    company resolves its item codes against the wrong company's catalogue and shows a diff
    that is not the one apply would make.
    """
    doc_type = _doc_type(kind)
    _require_single_company(db)
    result = svc.preview(db, await read_upload(file), doc_type)
    # A file whose header cannot answer the question is a 200 carrying `ok: false`, not an
    # error: the screen needs to render WHICH columns are missing so the export can be
    # fixed, and an exception body would lose that.
    return result.to_dict()


@router.post("/outstanding/{kind}/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_outstanding_import(
    kind: str,
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Queue the upload. Returns the job to watch, not the result.

    202, not 200: the write happens on the worker, so the body cannot carry counts that have
    not been computed yet. What happened lands on the job - per-row outcomes, the diff counts,
    the agents the file named - and the upload drawer follows it there.

    A file this route cannot READ is no longer a 400. The reading happens on the worker now,
    so an unreadable file fails the JOB with its problems on it; refusing here would mean
    parsing the whole book twice, once to answer the request and once to write it.
    """
    doc_type = _doc_type(kind)
    _assert_writable(kind, doc_type)
    upload = await read_upload_retained(file)

    # Refused BEFORE any job row exists, so a refused upload leaves nothing behind for
    # somebody to wonder about.
    company_id = _require_single_company(db)

    from app.services.import_source_store import store_import_source_file
    from app.tasks.import_tasks import process_outstanding_import

    job_service = JobService(db)
    job = job_service.create_job(
        job_type=_JOB_TYPES[doc_type],
        user_id=current_user["id"],
        filename=upload.filename,
        company_id=company_id,
    )
    store_import_source_file(job, upload.source_bytes, upload.source_name,
                             upload.content_type)
    db.commit()
    rq_job = enqueue_job(
        process_outstanding_import,
        str(job.id),
        upload.data,
        upload.filename,
        current_user["id"],
        doc_type,
        queue_name="imports",
        job_timeout=3600,
        job_id=str(job.job_id),  # pre-assign RQ id = DB job_id; see update_job_with_rq_id
    )
    job_service.update_job_with_rq_id(job, rq_job.id)
    return {"message": "Order book upload queued.", "job_id": job.job_id, "id": str(job.id)}
