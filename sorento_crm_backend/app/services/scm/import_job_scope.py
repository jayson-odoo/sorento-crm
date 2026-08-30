"""What one queued upload TOUCHED, read back off the finished job.

`PLAN-scm-oi-handshake.md` AC-H13. The buyer uploads a purchase-order or purchase-history
book from the Order Inquiries page, and when it lands they are offered two next steps:
link what the new documents can now cover, and go and look at the purchase orders that
arrived. Both need the same fact - which products and which documents this upload wrote -
and neither can have it at queue time, because the write happens on the worker.

So it is read off the job afterwards. Each channel states it on its own result
(`outstanding_import_service.apply`, `po_history_service.apply`), the job stores that
under `result.upload`, and this is the one reader of it. Nothing here computes anything:
a second derivation of "what did that upload touch" would be free to disagree with the
importer's own answer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.job import ImportJob, JobStatus

#: A job nobody is waiting on any more, whichever way it ended. The page shows its two
#: next steps at exactly this point and not before: offering "Link now" while the worker
#: is still reading the book links whatever the book had not written yet, which reads to
#: the buyer as the upload having done nothing.
TERMINAL_STATUSES = (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED)

#: How many document numbers travel to the purchase-order list. A URL naming a whole book
#: is not a filter anybody asked for, and past this the honest answer is the unfiltered
#: list - so the count is stated separately and the caller decides.
DOCUMENTS_LISTED = 50


def scope_of_job(db: Session, job_id: str) -> Optional[Dict[str, Any]]:
    """What that upload wrote, or None when no such job exists.

    `job_id` is the id the upload route handed back and the drawer polls on - the RQ id,
    not the row's own primary key.
    """
    job = db.query(ImportJob).filter(ImportJob.job_id == str(job_id)).first()
    if job is None:
        return None
    upload = ((job.result or {}).get("upload") or {}) if job.result else {}
    documents = [str(doc) for doc in (upload.get("documents")
                                      or upload.get("scope_documents") or []) if doc]
    product_ids: List[str] = [str(pid) for pid in (upload.get("product_ids") or []) if pid]
    status = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
    return {
        "job_id": str(job.job_id),
        "status": status,
        "finished": status in {s.value for s in TERMINAL_STATUSES},
        "job_type": job.job_type,
        "filename": job.source_filename or job.filename,
        "product_ids": product_ids,
        "documents": sorted(documents)[:DOCUMENTS_LISTED],
        "document_count": len(documents),
    }
