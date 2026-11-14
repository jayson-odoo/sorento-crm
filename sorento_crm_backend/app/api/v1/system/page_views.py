"""UI v2 page-view telemetry (UI-V2 phase 0, D10).

POST: any signed-in principal posts a batch of page views from the v2 shell. Same shape as
`client_errors.py`: the body is size-checked while it streams in, parsed by hand, the user id
comes from the session (never the body), 204 on success, 413 when too large, 429 once the
user's hourly allowance is spent, 422 on a bad item.
"""
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_actor_user_id, get_current_user
from app.services import ui_page_view_service as svc
from app.services.error_handler import AppException

router = APIRouter()


class PageViewItem(BaseModel):
    route: str = Field(..., min_length=1, max_length=2000)
    viewport: Literal["phone", "tablet", "desktop"]
    ms_to_first_data: Optional[int] = Field(None, ge=0, le=svc.MAX_MS)
    ui_version: Literal["v1", "v2"]
    at: Optional[datetime] = None

    @field_validator("route")
    @classmethod
    def _route_characters(cls, value: str) -> str:
        if not svc.is_valid_route(value):
            raise ValueError("route holds characters outside [A-Za-z0-9/_-[].]")
        return value


class PageViewBatch(BaseModel):
    items: List[PageViewItem] = Field(..., min_length=1, max_length=svc.MAX_ITEMS)


def _error(status_code: int, code: str, message: str) -> AppException:
    return AppException(status_code=status_code, message=message, code=code)


@router.post("/page-views", status_code=status.HTTP_204_NO_CONTENT)
async def record_page_views(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > svc.MAX_BODY_BYTES:
        raise _error(413, "payload_too_large", "Batch too large")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > svc.MAX_BODY_BYTES:
            raise _error(413, "payload_too_large", "Batch too large")
    try:
        payload = PageViewBatch.model_validate_json(bytes(received) or b"{}")
    except ValidationError:
        raise _error(422, "invalid_page_views", "Invalid page views")

    # The real actor, as client_errors does: impersonating cannot reset the allowance.
    user_id = get_actor_user_id(request, current_user)
    if svc.is_rate_limited(db, user_id):
        raise _error(429, "rate_limited", "Too many page views")

    svc.record_batch(db, user_id=user_id, items=payload.items)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
