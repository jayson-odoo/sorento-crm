"""Container requests: the demand-first stage in front of the Loading Plan's CBM fit.

`PLAN-scm-loading-plan-demand-first.md` section 4. `build` is a pure read: what the
supplier's current stock list identifies as theirs, ranked against the outstanding
sales-order book by the ACTIVE Fulfilment Priority policy. The send endpoint turns Ms Tee's
reviewed lines into a notice through the same S8 machinery `approve_loading_plan` uses
(`fulfilment.py`) - a document, an email when an address is on file, an outbox row either way
- just without a Loading Plan behind it, because CBM is not decided until the supplier packs.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.scm import container_request_service, supplier_notice_service
from app.utils.http import content_disposition

router = APIRouter()

#: What the two on-demand documents are served as.
_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

# The same two permissions the Loading Plan screen already reads and writes under (copied from
# `fulfilment.py`) - a container request is an earlier stage of that screen, not a new
# capability.
_READ = require_permission("scm.dashboard.view")
_WRITE = require_permission("scm.reorder.run")


def _actor(user: Optional[dict]) -> Optional[str]:
    """The caller's human name, never their id - same rule as every other SCM provenance."""
    user = user or {}
    return user.get("name") or user.get("email") or None


class ContainerRequestBuildBody(BaseModel):
    supplier_id: str
    # "Plan until" (captain, 20 Aug): mirrors the reorder run's own `plan_horizon_date`
    # (`app.schemas.scm_reorder`), but this build has no stored run row to carry a column on -
    # it recomputes on every call - so the horizon travels as a request field instead. `None`
    # (omitted, the default) means no cutoff, today's behaviour.
    plan_horizon_date: Optional[date] = None


class ContainerRequestLine(BaseModel):
    product_id: str
    qty: float = Field(..., gt=0)


class ContainerRequestBody(BaseModel):
    supplier_id: str
    lines: list[ContainerRequestLine] = Field(
        ..., min_length=1, description="Ms Tee's reviewed lines, edited quantities included."
    )


@router.post("/container-requests/build")
def build_container_request(
    body: ContainerRequestBuildBody,
    include_lines: bool = False,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """What to ask this supplier for, ranked by the active priority policy. Persists nothing.

    `include_lines` adds the open SO lines behind every demand row (see the service
    docstring) - off by default since most callers only need the aggregate rows.
    `body.plan_horizon_date` narrows open SO need to what is required on or before it
    (undated demand always counted) - see `container_request_service.build`.
    """
    return container_request_service.build(
        db,
        supplier_id=body.supplier_id,
        include_lines=include_lines,
        plan_horizon_date=body.plan_horizon_date,
    )


@router.get("/container-requests/history")
def container_request_history(
    supplier_id: str,
    product_ids: list[str] = Query(default=[]),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """What these products were ordered, per month, for the last twelve full months.

    A GET with the product ids repeated, because it is a pure read scoped to the page on
    screen (AC-B8) - the caller asks again when it pages, and the answer is cacheable.
    Declared BEFORE the `/container-requests` POST above it is irrelevant, but it must stay
    ahead of any future `/container-requests/{id}` route: a static segment behind a path
    parameter never matches (the SLA route-shadowing lesson).
    """
    return container_request_service.history(
        db, supplier_id=supplier_id, product_ids=product_ids
    )


@router.post("/container-requests/document")
def container_request_document(
    body: ContainerRequestBody,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The request as a file for the lines currently on screen, WITHOUT sending anything (R23).

    Behind the READ permission, not the write one: nothing is created, nothing leaves the
    building, and the supplier is told nothing - it is the same ask the screen is already
    showing, in a form that can be read, checked or forwarded by hand. `POST` because the
    lines are the body: they are Ms Tee's edits, not a stored plan this could re-derive.

    Ahead of `POST /container-requests` in this file for readability only; a static segment
    under a path parameter is the shadowing trap (the SLA lesson), and there is no
    `/container-requests/{id}` here.
    """
    content, filename = supplier_notice_service.request_document(
        db,
        supplier_id=body.supplier_id,
        lines=[ln.model_dump() for ln in body.lines],
        fmt=format,
    )
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/container-requests", status_code=status.HTTP_201_CREATED)
def send_container_request(
    body: ContainerRequestBody,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Send the reviewed request: one notice per channel, the same act as approving a plan."""
    return container_request_service.send(
        db,
        supplier_id=body.supplier_id,
        lines=[ln.model_dump() for ln in body.lines],
        actor=_actor(_user),
    )
