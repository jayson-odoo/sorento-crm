"""Container requests: the demand-first stage in front of the Loading Plan's CBM fit.

`PLAN-scm-loading-plan-demand-first.md` section 4. `build` is a pure read: what the
supplier's current stock list identifies as theirs, ranked against the outstanding
sales-order book by the ACTIVE Fulfilment Priority policy. The send endpoint turns Ms Tee's
reviewed lines into a notice through the same S8 machinery `approve_loading_plan` uses
(`fulfilment.py`) - a document, an email when an address is on file, an outbox row either way
- just without a Loading Plan behind it, because CBM is not decided until the supplier packs.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.scm import (
    container_request_drill,
    container_request_service,
    supplier_notice_service,
)
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
    """Which PLAN to build (part 4, R2).

    It used to be `{supplier_id, plan_horizon_date}`, because the build recomputed on every
    call and had no row to read them off. It has one now, and the row is also where the typed
    quantities live - so a body naming only a supplier could not say which plan's edits to
    apply. The old form is refused by validation; the loading-plan page was its only caller.
    """

    plan_id: str


class ContainerRequestLine(BaseModel):
    """One reviewed line. It names a product OR one of our product sets, never both.

    A set line carries no product id at all (R19): the supplier sells the whole WC under a
    code our catalogue does not hold, so the ask goes out under the set code and naming one
    member here would make the document disagree with the row it came from.
    """

    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    qty: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _one_target(self) -> "ContainerRequestLine":
        if bool(self.product_id) == bool(self.product_set_id):
            raise ValueError("name either a product or a product set on each line")
        return self


class ContainerRequestBody(BaseModel):
    plan_id: str
    lines: list[ContainerRequestLine] = Field(
        ..., min_length=1, description="Ms Tee's reviewed lines, edited quantities included."
    )


class ContainerRequestSendBody(ContainerRequestBody):
    """The reviewed lines, plus who this send goes to and how (R9, AC-C1/C2/C3).

    Its own body rather than four more optional fields on `ContainerRequestBody`: that one
    also backs `/container-requests/document`, which sends nothing and has no recipients to
    name.

    Every field is optional and `channel` defaults to email, so a caller written before the
    send dialog existed behaves exactly as it did: the request goes by email to
    `suppliers.email`.
    """

    channel: Literal["email", "chat"] = "email"
    #: The addresses an email send goes to. Omitted (null) means the supplier's own address;
    #: an EMPTY list is a 422, because a dialog that just asked who to send to cannot answer
    #: "nobody".
    recipients: Optional[list[EmailStr]] = None
    #: Which Respond.io contact a chat send is addressed to (`respond_contacts.id`).
    chat_contact_id: Optional[str] = None
    #: One line in the sender's own words, prepended to the bilingual body.
    note: Optional[str] = Field(None, max_length=2000)


@router.post("/container-requests/build")
def build_container_request(
    body: ContainerRequestBuildBody,
    include_lines: bool = False,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """What to ask this plan's supplier for, ranked by the active priority policy.

    Reads the supplier and the sales order cut-off off the plan row and applies its saved
    quantities, so the grid, the document and the send can never disagree about what is being
    asked for. `include_lines` adds the open SO lines behind every demand row - off by default
    since most callers only need the aggregate rows.
    """
    try:
        return container_request_service.build_for_plan(
            db, plan_id=body.plan_id, include_lines=include_lines
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


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
    try:
        plan = container_request_service._plan_or_404(db, body.plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    content, filename = supplier_notice_service.request_document(
        db,
        supplier_id=str(plan.supplier_id),
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
    body: ContainerRequestSendBody,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Send the reviewed request on the channel the sender chose (R9), for ONE plan.

    ONE notice row, for that channel: email to every address named, or WeChat to the picked
    Respond.io contact. The notice carries `loading_plan_id` and the plan flips to `sent`, so
    the list can say what went out and when, and the plan can no longer be deleted (Q5).
    Anything that would make the send impossible (no address, no WeChat channel connected, no
    approved template out of window) is a 422 with a `code` and nothing is written - see
    `supplier_notice_service.request_and_notify`.
    """
    try:
        return container_request_service.send(
            db,
            plan_id=body.plan_id,
            lines=[ln.model_dump() for ln in body.lines],
            actor=_actor(_user),
            channel=body.channel,
            recipients=[str(a) for a in body.recipients] if body.recipients is not None else None,
            chat_contact_id=body.chat_contact_id,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/container-requests/drill")
def drill_container_request_cell(
    supplier_id: str,
    product_id: str,
    kind: Literal["spo", "incoming_pl", "po"],
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The documents behind the SPO / Incoming PL / PO figure on one row (R8, AC-B4).

    `{kind, rows, total, history}`, where `total` is the SAME number the cell shows because
    both are one predicate - see `container_request_drill`'s module docstring, including why
    the SPO reader stays on `spo_allocations` after migration 420.

    `kind` is a `Literal`, so a kind nothing reads is a 422 from FastAPI rather than an
    empty 200 that reads as "there is nothing here". `on_hand` is deliberately absent: the
    On hand lightbox is served by `/reorder-runs/location-stock?product_id=`, which already
    answers it per product and is reused as-is (R7).

    A GET, and behind `_READ` for the same reason `/container-requests/history` is: it is a
    pure read of what the screen is already showing, scoped to one product.
    """
    return container_request_drill.drill(
        db, supplier_id=supplier_id, product_id=product_id, kind=kind
    )
