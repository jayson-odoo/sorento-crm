"""External ingest for AutoCount quotations (header + QTDTL) — Slice 6.

A quotation is a parent+lines document (new tables), so it does not ride the
generic /external/ingest/{entity} surface. Own router, mounted behind
order_management.quotations.edit, same verdict contract: 200 with per-record
outcomes + dry_run.
"""
import logging

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.error_handler import AppException
from app.services.quotation_ingest_service import QuotationIngestService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_BATCH = 1000


@router.post("/ingest")
async def ingest_quotations(
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

    service = QuotationIngestService(db, integration_id=current_user.get("integration_id"))
    result = service.ingest(records, dry_run=dry_run)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    logger.info(
        "quotation.ingest integration=%s dry_run=%s created=%d updated=%d failed=%d retryable=%d",
        current_user.get("integration_name"), dry_run,
        result.created, result.updated, result.failed, result.retryable,
    )
    return result.as_dict()
