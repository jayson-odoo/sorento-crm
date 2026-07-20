"""API call log admin API — external + MCP request telemetry.

Read-only. Rows are written by `ApiCallLogMiddleware`, never by a route, so there
is no create/update/delete surface to expose.

Gated on its own permission slug rather than a general system-admin grant: the
payloads are redacted but still contain business data from every external call.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.api_call_log_service import DEFAULT_LIMIT, MAX_LIMIT, list_call_logs
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


class ApiCallLogRow(BaseModel):
    id: str
    endpoint: str
    method: str
    source: str
    tool_name: Optional[str] = None
    actor: Optional[str] = None
    status_code: Optional[int] = None
    outcome: str
    latency_ms: Optional[int] = None
    correlation_id: Optional[str] = None
    request_payload: Optional[str] = None
    response_payload: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApiCallLogListResponse(BaseModel):
    data: List[ApiCallLogRow]
    total: int
    page: int
    limit: int


@router.get("/api-call-logs", response_model=ApiCallLogListResponse)
def list_api_call_logs(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None, pattern="^(success|client_error|server_error)$"),
    endpoint: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    min_latency_ms: Optional[int] = Query(None, ge=0),
    # The DataGrid sends its free-text box as `query`; `search` accepted too.
    query: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(require_permission("system_management.api_call_log.view")),
    db: Session = Depends(get_db),
):
    """Offset page for the DataGrid. Defaults to the last 24h.

    Unbounded by default would mean a full-table scan on a table that grows with
    every external request.
    """
    try:
        if date_from is None and date_to is None:
            date_from = datetime.utcnow() - timedelta(hours=24)

        rows, total = list_call_logs(
            db,
            date_from=date_from,
            date_to=date_to,
            source=source,
            outcome=outcome,
            endpoint=endpoint,
            correlation_id=correlation_id,
            min_latency_ms=min_latency_ms,
            search=search or query,
            page=page,
            limit=limit,
            sort=sort,
            dir_=dir,
        )
        return ApiCallLogListResponse(
            data=[ApiCallLogRow.model_validate(r) for r in rows],
            total=total,
            page=page,
            limit=limit,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Error listing api call logs: %s", e, exc_info=True)
        raise handle_internal_error(str(e))


@router.get("/api-call-logs/sources", response_model=List[str])
def list_api_call_log_sources(
    current_user: dict = Depends(require_permission("system_management.api_call_log.view")),
    db: Session = Depends(get_db),
):
    """Distinct sources actually present, for the filter dropdown.

    Live values rather than a hardcoded enum: a new caller should appear in the
    filter the first time it calls, without a code change.
    """
    from app.models.api_call_log import ApiCallLog

    rows = db.query(ApiCallLog.source).distinct().order_by(ApiCallLog.source).all()
    return [r[0] for r in rows if r[0]]
