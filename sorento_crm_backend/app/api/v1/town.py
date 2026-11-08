"""SORENTO-TOWN: `GET /api/v1/town/snapshot`.

Serves the snapshot the scheduler tick stored in Redis; the route reads NO business table
(auth, role and company lookups aside). Plan: documentation/plans/dashboard/PLAN-sorento-town-08nov.md.
"""
from __future__ import annotations

import gzip
import json
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.base import get_company_scope
from app.services.error_handler import AppException
from app.services.queue_service import redis_conn
from app.services.sales.invoiced_sales import INVOICED_SLUG
from app.services.town import snapshot as town
from app.services.user_service import holds_permission

router = APIRouter()

RATE_LIMIT_PER_MINUTE = 30
_HEADERS = {"Cache-Control": "private, no-cache"}


def _rate_limit(user_id: str) -> None:
    key = f"town:rl:{user_id}:{int(time.time() // 60)}"
    pipe = redis_conn.pipeline()
    pipe.incr(key)
    pipe.expire(key, 120)
    count = pipe.execute()[0]
    if count > RATE_LIMIT_PER_MINUTE:
        raise AppException(status_code=429, message="Too many requests", code="town_rate_limited")


def _company_id(request: Request, db: Session) -> str:
    # A staff session plus the shared key would resolve the company through the key path.
    if request.headers.get("x-api-key"):
        raise AppException(status_code=400, message="Choose a company first", code="company_required")
    scope = get_company_scope(db)
    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))
    raise AppException(status_code=400, message="Choose a company first", code="company_required")


def _matches(header: Optional[str], etag: str) -> bool:
    if not header:
        return False
    return any(part.strip().removeprefix("W/") == etag for part in header.split(","))


@router.get("/snapshot")
def get_snapshot(
    request: Request,
    mode: Optional[str] = Query(None),
    if_none_match: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _rate_limit(str(current_user["id"]))
    company_id = _company_id(request, db)
    variant = "full" if holds_permission(db, current_user, INVOICED_SLUG) else "redacted"
    wallboard = mode == "wallboard"
    day = datetime.now(town.MYT).date()
    stored = town.load(redis_conn, company_id, day, variant)
    if stored is None:
        return JSONResponse({"pending": True}, headers=_HEADERS)
    body, version = stored
    etag = f'"{version}-{variant}{"-wb" if wallboard else ""}"'
    headers = {**_HEADERS, "ETag": etag}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    if wallboard:
        body = gzip.compress(json.dumps(town.strip_names(json.loads(gzip.decompress(body)))).encode(), mtime=0)
    return Response(
        content=body, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"}
    )
