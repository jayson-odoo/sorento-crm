"""Stock API routes."""
import json as _json
import logging
import time
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel


def _normalize_entities(raw: Optional[list[str]]) -> Optional[list[str]]:
    """Flatten an `entities` query param into a clean list[str].

    Accepts None, a list of strings (repeated query param), or a single-element list
    containing a JSON array or comma-separated string - all forms n8n / curl callers
    produce depending on how they encode the param.
    """
    if raw is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    for p in parsed:
                        ps = str(p).strip()
                        key = ps.lower()
                        if ps and key not in seen:
                            seen.add(key)
                            out.append(ps)
                    continue
            except Exception:
                pass
        for piece in s.split(","):
            piece = piece.strip()
            if not piece:
                continue
            key = piece.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(piece)
    return out or None

from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    require_permission,
    require_permission_with_api_key,
)
from app.services.inventory_service import StockService
from app.services.uuid_list_param import parse_uuid_list
from app.schemas.inventory import StockResponse, StockBalanceListResponse, StockDashboardResponse, BulkImportStockRequest, BulkImportStockResponse, StockLedgerResponse
from app.schemas.common import ListResponse, ValidateImportResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()
logger = logging.getLogger(__name__)


class BulkDeleteStockRequest(BaseModel):
    ids: list[str]


@router.get("/balance", response_model=StockBalanceListResponse)
def get_stock_balance(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    query: Optional[str] = Query(None),
    entities: Optional[list[str]] = Query(
        None,
        description=(
            "DEPRECATED - free-text entity bag. Prefer `product_ids` (canonical UUID csv/list). "
            "Free-text resolution should go through `/api/v1/system/references/resolve` first."
        ),
    ),
    product_ids: Optional[list[str]] = Query(
        None,
        description=(
            "Filter by canonical product UUIDs. Accepts repeated values, comma-separated "
            "string, or JSON array. Non-UUID input → HTTP 400."
        ),
    ),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    warehouse_ids: Optional[list[str]] = Query(
        None,
        description="Filter by canonical warehouse UUIDs (repeated / csv / JSON array).",
    ),
    product_id: Optional[str] = Query(
        None,
        description="Single product UUID or product_code (kept for direct callers).",
    ),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status: critical, low, normal, overstock"),
    exclude_zero_system_adjustment: bool = Query(
        False,
        description=(
            "When true, hide rows whose on-hand is 0 ONLY because the latest stock-ledger "
            "movement was a SYSTEM_ADJUSTMENT (e.g. 'missing from full stock take'). A genuine "
            "0 (last movement an import/sale, or no ledger) is still returned. Used by the MCP."
        ),
    ),
    contact_id: Optional[str] = Query(
        None,
        description=(
            "The contact this question is being asked ON BEHALF OF - either the "
            "respond_contacts.id or the Respond.io id. Its presence switches the "
            "stock-visibility policy on: which locations may be named, and whether "
            "the answer comes back as rows, a per-product summary or a bare yes/no. "
            "Absent (the staff web grid) means no policy is applied at all."
        ),
    ),
    space_id: Optional[str] = Query(
        None,
        description=(
            "Respond.io workspace id. Only used to disambiguate `contact_id` when "
            "it is a Respond.io id: the same id can exist in two workspaces."
        ),
    ),
    requested_qty: Optional[int] = Query(
        None,
        description=(
            "How many units the contact asked for. Read only under an "
            "`availability` policy, where it turns 'how many do you need?' into a "
            "yes/no. A value below 1 is read as not provided (the number is parsed "
            "out of a sentence, so a 0 is a parse artefact) and the reply asks for "
            "the quantity again."
        ),
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock balance with pagination and filtering.

    The stock-visibility policy (PLAN-stock-visibility-policy) is applied ONLY when
    `contact_id` is present. Staff callers pass none, so the web grid keeps getting
    full rows for every warehouse their RBAC allows even if the DEFAULT policy row
    is later flipped to `compact` for the chatbot.

    A `contact_id` MUST arrive with its `space_id`. Two independent resolvers read
    this pair - the request-entry company scope (`_resolve_api_key_scope`) and the
    visibility policy - and company scope needs BOTH params or it stays off
    entirely. With only `contact_id` the contact would therefore be answered a
    policy-shaped slice of every company's stock. They agree or nobody is answered.
    """
    if contact_id and not space_id:
        return {
            "data": [],
            "pagination": {"total": 0, "page": page, "limit": limit},
            "empty": True,
        }
    try:
        service = StockService(db)
        result = service.list_stock(
            page=page,
            limit=limit,
            query=query,
            sort=sort,
            dir=dir,
            warehouse_id=warehouse_id,
            warehouse_ids=parse_uuid_list(warehouse_ids, param_name="warehouse_ids"),
            product_id=product_id,
            product_ids=parse_uuid_list(product_ids, param_name="product_ids"),
            quantity_operator=quantity_operator,
            quantity_value=quantity_value,
            status=status,
            entities=_normalize_entities(entities),
            exclude_zero_system_adjustment=exclude_zero_system_adjustment,
            contact_id=contact_id,
            space_id=space_id,
            requested_qty=requested_qty,
        )
        # Data-miss path (§3.3): when the service attached `alternatives` /
        # `relaxed_axis` (only on an empty result), bypass the strict
        # `ListResponse` response_model - which would silently drop those keys - 
        # and emit the raw dict. `data` is always [] here, so encoding is trivial
        # and the with-data path stays byte-identical (AC-R1).
        if isinstance(result, dict) and result.get("alternatives"):
            from fastapi.encoders import jsonable_encoder
            return JSONResponse(content=jsonable_encoder(result))
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/dashboard", response_model=StockDashboardResponse)
def get_stock_dashboard(
    limit: int = Query(10, ge=1, le=50, description="Cap on list sizes (top warehouses, top low-stock rows)."),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock dashboard statistics."""
    try:
        service = StockService(db)
        result = service.get_stock_dashboard(limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/alerts")
def get_stock_alerts(
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get low stock alerts."""
    started = time.perf_counter()
    logger.info("inventory.stock_alerts start")
    try:
        service = StockService(db)
        alerts = service.get_stock_alerts()
        elapsed_ms = (time.perf_counter() - started) * 1000
        count = len(alerts) if isinstance(alerts, list) else -1
        logger.info("inventory.stock_alerts done elapsed_ms=%.1f count=%s", elapsed_ms, count)
        return alerts
    except Exception as e:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("inventory.stock_alerts failed elapsed_ms=%.1f error=%s", elapsed_ms, str(e))
        raise handle_internal_error(str(e))


@router.get("/balance/export")
def export_stock_balance(
    warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(
        None,
        description="Single product UUID or product_code (kept for direct callers).",
    ),
    product_ids: Optional[list[str]] = Query(
        None,
        description="Filter by canonical product UUIDs (csv/JSON/repeated). Preferred over `entities`.",
    ),
    entities: Optional[list[str]] = Query(
        None,
        description=(
            "DEPRECATED - free-text entity bag. Prefer `product_ids`. Free-text resolution "
            "should go through `/api/v1/system/references/resolve` first."
        ),
    ),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("inventory.stock.export")),
    db: Session = Depends(get_db)
):
    """Export all stock balance data (no pagination, returns all records)."""
    started = time.perf_counter()
    logger.info(
        "inventory.stock_balance_export start warehouse_id=%s product_id=%s quantity_operator=%s quantity_value=%s",
        warehouse_id,
        product_id,
        quantity_operator,
        quantity_value,
    )
    try:
        service = StockService(db)
        stock_items = service.get_all_stock_for_export(
            warehouse_id=warehouse_id,
            product_id=product_id,
            product_ids=parse_uuid_list(product_ids, param_name="product_ids"),
            quantity_operator=quantity_operator,
            quantity_value=quantity_value,
            entities=_normalize_entities(entities),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("inventory.stock_balance_export done elapsed_ms=%.1f rows=%s", elapsed_ms, len(stock_items))
        return {
            "data": stock_items,
            "total": len(stock_items)
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("inventory.stock_balance_export failed elapsed_ms=%.1f error=%s", elapsed_ms, str(e))
        raise handle_internal_error(str(e))


@router.delete("/bulk")
async def bulk_delete_stock(
    body: BulkDeleteStockRequest = Body(...),
    current_user: dict = Depends(require_permission("inventory.stock.delete")),
    db: Session = Depends(get_db)
):
    """Bulk delete stock records by id. Requires inventory.stock.delete permission."""
    try:
        service = StockService(db)
        result = service.bulk_delete_stock(body.ids)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_id}/{warehouse_id}/ledger", response_model=ListResponse[StockLedgerResponse])
def get_stock_ledger_by_stock(
    product_id: str = Path(
        ...,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    warehouse_id: str = Path(..., description="Warehouse id (UUID)."),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock ledger entries for a specific product and warehouse."""
    try:
        service = StockService(db)
        result = service.get_stock_ledger_by_stock(
            product_id=product_id,
            warehouse_id=warehouse_id,
            page=page,
            limit=limit
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Validation only (validate_only=true)", "model": ValidateImportResponse}},
)
async def bulk_import_stock(
    import_data: BulkImportStockRequest,
    current_user: dict = Depends(require_permission("inventory.stock.import")),
    db: Session = Depends(get_db)
):
    """Bulk import stock from Excel data (queued). If validate_only=true, validate only and return errors/warnings (no job)."""
    try:
        if getattr(import_data, "validate_only", False):
            service = StockService(db)
            result = service.bulk_import_stock(
                import_data.stock, current_user["id"], validate_only=True
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "valid": result["valid"],
                    "errors": result["errors"],
                    "warnings": result.get("warnings", []),
                    "summary": result.get("summary"),
                },
            )

        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_stock_import

        # Create job record
        job_service = JobService(db)
        job = job_service.create_job(
            job_type='stock_import',
            user_id=current_user["id"],
            metadata={'total_rows': len(import_data.stock)}
        )
        setattr(job, "total_rows", len(import_data.stock))
        db.commit()
        
        # Enqueue job
        rq_job = enqueue_job(
            process_stock_import,
            str(job.id),  # Pass DB job ID (UUID)
            import_data.stock,
            current_user["id"],
            queue_name='imports',
            job_timeout=3600,
            job_id=str(job.job_id),  # pre-assign RQ id = DB job_id; see update_job_with_rq_id
        )
        
        # Update job with RQ job ID
        job_service.update_job_with_rq_id(job, rq_job.id)
        
        return {
            'job_id': rq_job.id,
            'status': 'queued',
            'message': 'Import job queued successfully'
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
