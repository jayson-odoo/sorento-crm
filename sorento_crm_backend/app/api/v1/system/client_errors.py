"""Browser crash reports (CLIENT-ERROR-REPORT).

POST: any signed-in principal reports one error that reached a React error boundary.
The body is parsed by hand after a size check, so an oversized payload is refused
while it streams in, before it is buffered in full, parsed or stored. 204 on success; 413 when too large;
429 once the user's hourly allowance is spent.

GET: the System Management list, gated on its own view slug.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_actor_user_id, get_current_user, require_permission
from app.services import client_error_report_service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


class ClientErrorIn(BaseModel):
    boundary: str = "global"
    name: Optional[str] = None
    message: Optional[str] = None
    stack: Optional[str] = None
    digest: Optional[str] = None
    path: Optional[str] = None
    build_sha: Optional[str] = None
    is_chunk_error: bool = False
    timestamp: Optional[datetime] = None


class ClientErrorRow(BaseModel):
    id: str
    user_id: Optional[str] = None
    # Resolved for the list; the screen never shows the raw id.
    user_name: Optional[str] = None
    boundary: str
    error_name: Optional[str] = None
    message: Optional[str] = None
    stack: Optional[str] = None
    digest: Optional[str] = None
    path: Optional[str] = None
    build_sha: Optional[str] = None
    user_agent: Optional[str] = None
    is_chunk_error: bool
    client_ts: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ClientErrorListResponse(BaseModel):
    data: List[ClientErrorRow]
    total: int
    page: int
    limit: int


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"message": message, "detail": None, "code": code},
    )


@router.post("/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_error(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > svc.MAX_BODY_BYTES:
        return _error(413, "payload_too_large", "Report too large")
    # Read in chunks and stop at the cap: a chunked request has no content-length,
    # and request.body() would buffer whatever the client cares to send.
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > svc.MAX_BODY_BYTES:
            return _error(413, "payload_too_large", "Report too large")
    body = bytes(received)
    try:
        payload = ClientErrorIn.model_validate_json(body or b"{}")
    except ValidationError:
        return _error(422, "invalid_report", "Invalid report")

    user_id = get_actor_user_id(request, current_user)
    if svc.is_rate_limited(db, user_id):
        return _error(429, "rate_limited", "Too many reports")

    svc.record_report(
        db,
        user_id=user_id,
        boundary=payload.boundary,
        error_name=payload.name,
        message=payload.message,
        stack=payload.stack,
        digest=payload.digest,
        path=payload.path,
        build_sha=payload.build_sha,
        # From the header, not the body: the one field the browser cannot be asked to supply honestly.
        user_agent=request.headers.get("user-agent"),
        is_chunk_error=payload.is_chunk_error,
        client_ts=payload.timestamp,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/client-errors", response_model=ClientErrorListResponse)
def list_client_errors(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    chunk_only: Optional[bool] = Query(None),
    query: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission("system_management.client_error.view")),
    db: Session = Depends(get_db),
):
    """Newest first. Defaults to the last 7 days."""
    if date_from is None and date_to is None:
        date_from = datetime.utcnow() - timedelta(days=7)
    rows, total = svc.list_reports(
        db,
        date_from=date_from,
        date_to=date_to,
        chunk_only=chunk_only,
        search=search or query,
        page=page,
        limit=limit,
    )
    names = svc.user_names(db, [r.user_id for r in rows])
    data = []
    for r in rows:
        item = ClientErrorRow.model_validate(r)
        item.user_name = names.get(r.user_id) if r.user_id else None
        data.append(item)
    return ClientErrorListResponse(
        data=data,
        total=total,
        page=page,
        limit=limit,
    )
