"""External ingest for AutoCount stock-balance reports — Slice 4.

A report, not a document: each push creates one appended run-history snapshot.
Own router (not the /external/ingest/{entity} surface, which is idempotent-upsert
masters). Returns a run summary, not a per-record verdict.
"""
import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.error_handler import AppException
from app.services.stock_balance_ingest_service import StockBalanceIngestService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_ROWS = 50000


@router.post("/ingest")
async def ingest_stock_balance(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    # Accept either {"rows": [...]} or {"records": [...]} -- the report is a bare
    # array conceptually; both keys map to the same run.
    rows = payload.get("rows")
    if rows is None:
        rows = payload.get("records")
    if not isinstance(rows, list):
        raise AppException(status_code=422, message="Body must contain a 'rows' array",
                           code="INVALID_BODY")
    if len(rows) > MAX_ROWS:
        raise AppException(
            status_code=413,
            message=f"Report of {len(rows)} rows exceeds the maximum of {MAX_ROWS}. Split it.",
            code="BATCH_TOO_LARGE",
        )

    service = StockBalanceIngestService(db, integration_id=current_user.get("integration_id"))
    result = service.ingest(rows)

    if not result.get("created"):
        db.rollback()
        errs = result.get("errors") or []
        detail = "; ".join(f"row {e['index']}: {e['error']}" for e in errs[:10])
        raise AppException(status_code=422, message="Stock balance report has invalid rows",
                           code="INVALID_ROWS", detail=detail)

    db.commit()
    logger.info(
        "stock_balance.ingest integration=%s run=%s rows=%d resolved=%d",
        current_user.get("integration_name"), result["run_id"],
        result["row_count"], result["rows_with_product"],
    )
    return result
