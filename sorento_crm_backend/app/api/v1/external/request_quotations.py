"""External ingest for AutoCount request-for-quotations (header + RQDTL) — Slice 7.

Parent+lines document (new tables), own router, mounted behind
procurement.request_quotations.edit, same verdict contract: 200 with per-record
outcomes + dry_run.
"""
import logging

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.error_handler import AppException
from app.services.request_quotation_ingest_service import RequestQuotationIngestService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_BATCH = 1000


@router.post("/ingest")
async def ingest_request_quotations(
    payload: dict = Body(...),
    dry_run: bool = Query(False, description="Resolve + apply then roll back; writes nothing."),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    records = payload.get("records")
    if not isinstance(records, list):
        raise AppException(status_code=422, message="Body must contain a 'records' array",
                           code="INVALID_BODY")
    if len(records) > MAX_BATCH:
        raise AppException(
            status_code=413,
            message=f"Batch of {len(records)} exceeds the maximum of {MAX_BATCH}. Split it.",
            code="BATCH_TOO_LARGE",
        )

    service = RequestQuotationIngestService(db, integration_id=current_user.get("integration_id"))
    result = service.ingest(records, dry_run=dry_run)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    logger.info(
        "request_quotation.ingest integration=%s dry_run=%s created=%d updated=%d failed=%d retryable=%d",
        current_user.get("integration_name"), dry_run,
        result.created, result.updated, result.failed, result.retryable,
    )
    return result.as_dict()
