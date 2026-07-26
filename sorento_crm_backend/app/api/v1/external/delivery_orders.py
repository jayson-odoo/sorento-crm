"""External ingest for AutoCount delivery orders (header + DODTL) — Slice 5.

A DO is a parent+lines document that REUSES orders + order_lines, so it does not
ride the generic /external/ingest/{entity} surface (flat ENTITY_SPECS). It gets
its own router, mounted behind order_management.orders.import, but keeps the
exact same verdict contract: 200 with per-record outcomes + dry_run.
"""
import logging

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.error_handler import AppException
from app.services.delivery_order_ingest_service import DeliveryOrderIngestService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_BATCH = 1000


@router.post("/ingest")
async def ingest_delivery_orders(
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

    service = DeliveryOrderIngestService(db, integration_id=current_user.get("integration_id"))
    result = service.ingest(records, dry_run=dry_run)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    logger.info(
        "delivery_order.ingest integration=%s dry_run=%s created=%d updated=%d failed=%d retryable=%d",
        current_user.get("integration_name"), dry_run,
        result.created, result.updated, result.failed, result.retryable,
    )
    return result.as_dict()
