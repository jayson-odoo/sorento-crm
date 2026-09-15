"""CRM-side price tag request endpoints.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Permission gates:
  * ``dealer_kit.price_tag_requests.view``    - list + detail
  * ``dealer_kit.price_tag_requests.process`` - claim, transition, line update
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import Page, PageVersion
from app.models.price_tag import (
    PriceTagRequest,
    PriceTagRequestLine,
    PriceTagRequestTag,
)
from app.models.user import User
from app.schemas.price_tag import (
    PriceTagRequestLineResponse,
    LineDataChange,
    PriceTagRequestOfficeUpdate,
    RequestVersionSummary,
    ResolvedLineData,
    ReviewCommentResolvePayload,
    ReviewCommentResponse,
    PriceTagRequestTagResponse,
    PriceTagRequestTagSplit,
    PriceTagRequestTagUpdate,
    TagDataChangeSet,
    TagPinPayload,
    TagPinResponse,
    PriceTagRequestListItem,
    PriceTagRequestResponse,
    TagSheetDocPayload,
    TagSheetDesignResponse,
    TagSheetDocResponse,
    TagSheetExportIn,
    TagSheetExportOut,
    TransitionPayload,
)
from app.services import price_tag_review_service
from app.services.uuid_path_param import validate_uuid_path
from app.services.dealer_kit import tag_data_service, tag_sheet_export_service
from app.services.error_handler import AppException
from app.services.price_tag_request_service import (
    PriceTagRequestService,
    PRINT_BY_CHOICES,
    STATUS_DESIGNING,
    STATUS_PROOF_READY,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/price-tag-requests", tags=["price-tag-requests"])

_VIEW = require_permission_with_api_key("dealer_kit.price_tag_requests.view")
_PROCESS = require_permission("dealer_kit.price_tag_requests.process")

def _default_tag_sheet_doc() -> dict:
    """A tag sheet nobody has drawn on yet, but one the designer can OPEN.

    Written only when a version has to exist and there is no document to put
    in it (R6) - what that version is FOR is the pins it carries, not the
    empty page. The prior fallback (``{"kind": "tag_sheet", "sheets": []}``)
    had no ``imposition`` key, and every reader of a tag_sheet doc
    (``ScaledSheet``, ``TagSheetRenderer``) reads
    ``doc.imposition.page_width_mm`` / ``page_height_mm`` unconditionally, so
    a request whose FIRST design action was Update tag (not a CRM Claim,
    which auto-creates the ``Page`` via ``ensure_tag_sheet_page`` but writes
    no document at all until a save) left a document nothing could draw.
    Values match the designer's own default (``IMPOSITION_PRESETS.auto``,
    `lib/dealer-kit/tag-template-types.ts`), so the page this builds looks
    exactly like the one a fresh claim opens on.
    """
    return {
        "kind": "tag_sheet",
        "imposition": {
            "preset": "auto",
            "page_width_mm": 210,
            "page_height_mm": 297,
            "bleed_mm": 3,
            "gap_mm": 2,
        },
        "sheets": [],
    }


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class PriceTagRequestPage(BaseModel):
    """One page of the queue, and how many rows there are behind it.

    The shape ``buildDataGridParams`` asks for and the grid reads: ``data`` plus
    ``pagination``, the same envelope the other server-paged listings answer.
    """

    data: list[PriceTagRequestListItem]
    pagination: dict


@router.get("", response_model=PriceTagRequestPage)
def list_price_tag_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    query: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """One page of price tag requests, searched, sorted and counted here.

    On the server, not in the browser: this used to answer the WHOLE table and
    let the grid cut a page out of it, so every keystroke shipped every request
    in the system and the record count was the length of the array that arrived.

    Drafts are not in it either. A request the salesperson has saved but not
    submitted is not work yet, and it used to sit in this queue at status ``new``
    looking exactly like one that had been sent.
    """
    rows, total = PriceTagRequestService.list_page(
        db,
        status=status_filter,
        search=query,
        include_drafts=False,
        page=page,
        limit=limit,
        sort=sort,
        direction=dir,
    )
    return PriceTagRequestPage(
        data=PriceTagRequestService.list_items(db, rows),
        pagination={"total": total, "page": page, "limit": limit},
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def _with_resolved_lines(db: Session, req) -> PriceTagRequestResponse:
    """The request with its lines resolved to code, name and both prices.

    One implementation, in the service: the portal detail route answers with the
    same body, and two copies would let the two screens drift (D49).
    """
    return PriceTagRequestService.response_with_resolved_lines(db, req)


@router.get("/{request_id}", response_model=PriceTagRequestResponse)
def get_price_tag_request(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    return _with_resolved_lines(db, req)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


@router.post("/{request_id}/claim", response_model=PriceTagRequestResponse)
def claim_price_tag_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Assign the request to the claiming user and transition new -> designing."""
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    PriceTagRequestService.validate_claimable(req)

    # The ASSIGNEE, not the creator. This used to write ``created_by``, which
    # says who made the row and which no reader looks at, so the header said
    # "Unclaimed" from the claim onwards.
    req.assigned_to_id = _user_id(user)
    result = PriceTagRequestService.transition_status(
        db, request_id, STATUS_DESIGNING, user_id=_user_id(user),
    )

    # Auto-create a tag_sheet page for this request if one does not exist.
    # Shared with auto_assign_from_tracker (D8, B1) so a request claimed by
    # either path ends up with the same page.
    PriceTagRequestService.ensure_tag_sheet_page(db, result, _user_id(user))

    db.commit()
    # Answered through the same resolver as the detail route: the page renders
    # this body straight into the header, and a bare model_validate would send
    # back the claim with no name on it.
    return _with_resolved_lines(db, result)


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


@router.post("/{request_id}/transition", response_model=PriceTagRequestResponse)
def transition_price_tag_request(
    request_id: str,
    payload: TransitionPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Apply a status transition with optional note."""
    result = PriceTagRequestService.transition_status(
        db,
        request_id,
        payload.status,
        user_id=_user_id(user),
        notify_ctx={"reason": payload.note} if payload.note else None,
    )
    # D14: `TransitionPayload.note` has existed since r7 and this route threw it
    # away, so a rejection reason was typed into a box that discarded it. It is
    # a general review comment by the staffer now - the salesperson reads it
    # beside their own pins, and the message quotes it.
    if payload.note and payload.note.strip():
        price_tag_review_service.create_comments(
            db,
            result,
            comments=[],
            note=payload.note,
            author_user_id=_user_id(user),
        )
    # Marking the proof ready is a deliberate act, so it promotes the autosaved
    # draft to a version the same way manual Save does (B1). The designer's own
    # button saves first and leaves nothing to promote, but the detail page's
    # header can transition a request whose designer tab still holds an
    # unsaved draft - and the proof renders from VERSIONS, so without this the
    # salesperson would review the last manual save rather than the design
    # marketing just declared ready.
    if payload.status == STATUS_PROOF_READY and result.page_id:
        page = db.query(Page).filter(Page.id == result.page_id).first()
        if page is not None and page.draft_doc is not None:
            _snapshot_draft(
                db, page, page.draft_doc, _user_id(user), "Marked proof ready"
            )
    db.commit()
    return _with_resolved_lines(db, result)


# ---------------------------------------------------------------------------
# Edit request (r9 S3/D7)
# ---------------------------------------------------------------------------


@router.patch("/{request_id}", response_model=PriceTagRequestResponse)
def update_price_tag_request(
    request_id: str,
    payload: PriceTagRequestOfficeUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """The office fixing what the salesperson answered (D7).

    Only the print choice today: everything else on a submitted request is the
    salesperson's own, and changes through the revision engine. Refused once the
    request is finished - the choice decides a journey that has already ended.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND"
        )
    if PriceTagRequestService.is_terminal(req):
        raise AppException(
            status_code=409,
            message="This request is finished and can no longer be changed.",
            code="INVALID_STATE",
        )
    data = payload.model_dump(exclude_unset=True)
    if "print_by" in data:
        choice = data["print_by"]
        if choice is not None and choice not in PRINT_BY_CHOICES:
            raise AppException(
                status_code=422,
                message="Printing must be Office prints or I print myself.",
                code="INVALID_PRINT_BY",
            )
        req.print_by = choice
    db.flush()
    db.commit()
    return _with_resolved_lines(db, req)


# ---------------------------------------------------------------------------
# The product data gate and the request's own history (r9 S5/D18-D19)
# ---------------------------------------------------------------------------


def _change_sets(db: Session, req) -> list[TagDataChangeSet]:
    """The resolver's diff, one entry per changed TAG.

    Per tag since the combos slice: a line may print several tags and two of
    them resolve different products, so rolling them up here would ask one
    question about two different changes. The Lines tab rolls its own pill up
    from these.
    """
    return [
        TagDataChangeSet(
            tag_id=row["tag_id"],
            tag_label=row.get("tag_label") or "",
            line_id=row["line_id"],
            code=row.get("code") or "",
            name=row.get("name") or "",
            changes=row.get("data_changes") or [],
        )
        for row in tag_data_service.resolve_request_line_data(db, req)
        if row.get("data_changes")
    ]


@router.get("/{request_id}/data-changes", response_model=list[TagDataChangeSet])
def list_tag_data_changes(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """What master data has moved under this request's pinned tags (D17/D18).

    The SAME diff the resolver computes - this route only reshapes it per tag
    with the line's code, so the card and the Lines tab can name what changed
    without resolving anything a second time. A terminal request answers an
    empty list: nothing on it can be updated.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND"
        )
    return _change_sets(db, req)


@router.post(
    "/{request_id}/data-changes/recheck", response_model=list[TagDataChangeSet]
)
def recheck_tag_data_changes(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """Forget every Keep on this request and re-run the product-data gate
    (owner test round finding 3).

    Keep current silenced ONE drift by recording its hash as the ack, and
    there was no way to ask again - so a red dot silenced once stayed silent
    forever, even for a later, unrelated edit that would have tripped the
    gate on its own. Clearing every tag's ack re-arms the comparison, then
    answers the same shape ``GET .../data-changes`` does.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND"
        )
    for line in req.lines:
        for tag in line.tags or []:
            if tag.data_change_ack_hash is not None:
                tag.data_change_ack_hash = None
    db.commit()
    return _change_sets(db, req)


@router.post("/{request_id}/tags/{tag_id}/pin", response_model=TagPinResponse)
def resolve_tag_pin(
    request_id: str,
    tag_id: str,
    payload: TagPinPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Answer the product-data question for one TAG (D18).

    ``update`` takes the new values, and keeps the design as it stood in a
    version FIRST - so the tag is always one Restore away from what it was.
    ``keep`` records the hash of what was looked at, so the same change stops
    asking; a different change later asks again.

    Per tag rather than per line since the combos slice: two tags split off one
    line print two different basins, so a Keep on one must not silence the
    other.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND"
        )
    if PriceTagRequestService.is_terminal(req):
        raise AppException(
            status_code=409,
            message="This request is finished; its tags can no longer change.",
            code="INVALID_STATE",
        )
    tag = _tag_or_404(db, request_id, tag_id)

    live_rows = {
        row["tag_id"]: row
        for row in tag_data_service.resolve_tags_live(db, req, [tag])
    }
    live = live_rows.get(tag.id)
    if live is None:
        raise AppException(
            status_code=409,
            message="This tag's product can no longer be resolved.",
            code="INVALID_STATE",
        )

    if payload.action == "update":
        # R6: a pin is never overwritten without a version to get back to, so
        # a request that has no page yet gets one here. The version's own
        # `pinned_line_data` is what Restore needs, and it is exactly what the
        # next two lines are about to replace - an empty document is still a
        # complete way back.
        PriceTagRequestService.ensure_tag_sheet_page(db, req, _user_id(user))
        page = db.query(Page).filter(Page.id == req.page_id).first()
        if page is not None:
            latest = _latest_version(db, page)
            doc = (
                page.draft_doc
                or (latest.doc if latest else None)
                or _default_tag_sheet_doc()
            )
            fields = ", ".join(
                change["label"]
                for change in (
                    tag_data_service.diff_pin_against_live(
                        db, req, tag.pinned_tag_data or {}, live, None
                    )
                )
            )
            _snapshot_draft(
                db,
                page,
                doc,
                _user_id(user),
                f"Before product update: {fields}" if fields else
                "Before product update",
            )
        tag.pinned_tag_data = tag_data_service.pin_payload(live)
        tag.pinned_at = datetime.utcnow()
        tag.data_change_ack_hash = None
    else:
        # Keep: the TAG stays as it is. The hash of what was looked at is the
        # ack, so this exact change stops asking and the next one does not.
        tag.data_change_ack_hash = tag_data_service.data_hash(live)

    db.flush()
    db.commit()
    return TagPinResponse(tag_id=tag.id, pinned_at=tag.pinned_at)


@router.get("/{request_id}/versions", response_model=list[RequestVersionSummary])
def list_request_versions(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The design's history, newest first (D19).

    An empty history is a state the sheet draws, not an error: a request whose
    design has never been saved answers `[]`.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req = PriceTagRequestService.get_request(db, request_id)
    if not req or not req.page_id:
        return []
    rows = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == req.page_id)
        .order_by(PageVersion.version.desc())
        .all()
    )
    authors = {
        user.id: (user.name or user.email)
        for user in db.query(User)
        .filter(User.id.in_({row.created_by for row in rows if row.created_by}))
        .all()
    } if rows else {}
    return [
        RequestVersionSummary(
            version=row.version,
            commit_message=row.commit_message,
            created_by_name=authors.get(row.created_by),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{request_id}/versions/{version}", response_model=TagSheetDesignResponse)
def get_request_version(
    request_id: str,
    version: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """One version, as the shared lightbox draws it (D19).

    The same payload shape a live design answers - a version IS a whole tag
    sheet document, so it needs the same media maps to draw.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req, page = _require_request_page(db, request_id)
    row = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page.id, PageVersion.version == version)
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404, message="That version no longer exists.", code="NOT_FOUND"
        )
    # S2: a version draws the pins it was WRITTEN with. Resolving its lines
    # against today's pins shows last week's layout filled with this week's
    # prices - a page that never existed, presented as history. A version from
    # before the pins existed has none of its own and falls back to the live
    # resolve, which is what it was drawn from anyway.
    rows, media = tag_sheet_export_service.design_media(
        db,
        req,
        row.doc,
        rows=(
            tag_data_service.resolve_version_line_data(db, req, row.pinned_line_data)
            if row.pinned_line_data
            else None
        ),
    )
    return TagSheetDesignResponse(
        page_id=str(page.id),
        version=row.version,
        doc=row.doc,
        source="version",
        lines=[ResolvedLineData.model_validate(line) for line in rows],
        **media,
    )


@router.post(
    "/{request_id}/versions/{version}/restore", response_model=RequestVersionSummary
)
def restore_request_version(
    request_id: str,
    version: int,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Put a version's document AND its pins back (D19).

    Adds a version rather than destroying one, so the way back is the list
    itself - which is also why it asks nothing first.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    req, page = _require_request_page(db, request_id)
    if PriceTagRequestService.is_terminal(req):
        raise AppException(
            status_code=409,
            message="This request is finished; its design can no longer change.",
            code="INVALID_STATE",
        )
    row = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page.id, PageVersion.version == version)
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404, message="That version no longer exists.", code="NOT_FOUND"
        )

    pins = row.pinned_line_data or {}
    for line in req.lines:
        for tag in line.tags or []:
            if tag.id in pins:
                tag.pinned_tag_data = pins[tag.id]
                tag.data_change_ack_hash = None
    page.draft_doc = row.doc
    db.flush()
    created = _snapshot_draft(db, page, row.doc, _user_id(user), f"Restored v{version}")
    # The restored document is the draft AND the newest version: the designer
    # opens draft-first, and the history has to show what happened.
    page.draft_doc = row.doc
    db.flush()
    db.commit()
    return RequestVersionSummary(
        version=created.version,
        commit_message=created.commit_message,
        created_by_name=None,
        created_at=created.created_at,
    )


# ---------------------------------------------------------------------------
# Pinned change requests (r9 S2/D6)
# ---------------------------------------------------------------------------


@router.get(
    "/{request_id}/review-comments", response_model=list[ReviewCommentResponse]
)
def list_review_comments(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Every change request the salesperson pinned on this design (D6)."""
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    return price_tag_review_service.to_responses(
        db, price_tag_review_service.list_comments(db, request_id)
    )


@router.patch(
    "/{request_id}/review-comments/{comment_id}",
    response_model=ReviewCommentResponse,
)
def resolve_review_comment(
    request_id: str,
    comment_id: str,
    payload: ReviewCommentResolvePayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Tick a change request Done, or put it back (D6).

    Gated on the PROCESS permission, not view: the salesperson may read their
    own comments and never close one - a change request is closed by whoever
    did the work, and the row records which of them it was.
    """
    request_id = validate_uuid_path(request_id, resource="Price tag request")
    row = price_tag_review_service.set_resolved(
        db,
        request_id,
        comment_id,
        resolved=payload.resolved,
        user_id=_user_id(user),
    )
    return price_tag_review_service.to_responses(db, [row])[0]


# ---------------------------------------------------------------------------
# Tags (D3): what actually gets printed for a line
#
# The line-level `PUT /{request_id}/lines/{line_id}` is GONE with the columns it
# wrote. Left mounted it would keep accepting a blind `setattr` of fields that no
# longer exist, so a stale frontend build would get a 200 for a write that did
# nothing.
# ---------------------------------------------------------------------------


def _tag_or_404(db: Session, request_id: str, tag_id: str) -> PriceTagRequestTag:
    """One tag of THIS request, or 404.

    The request is resolved FIRST, through `get_request`, and that is what makes
    this safe: neither `price_tag_request_tags` nor `price_tag_request_lines` is
    company-scoped on its own (both hang off the request, which carries the
    partition), so a query that named only those two had no scoped entity for
    `do_orm_execute` to attach the company predicate to - and PATCH, split and
    DELETE all worked across companies. DELETE went further and rewrote the
    other company's draft document.

    `get_request` returns None for a request outside the caller's scope, which
    reads here exactly like one that does not exist. That is the correct answer:
    never confirm another company's id is real.
    """
    request = PriceTagRequestService.get_request(db, request_id)
    if request is None:
        raise AppException(status_code=404, message="Tag not found.", code="NOT_FOUND")
    tag = (
        db.query(PriceTagRequestTag)
        .join(PriceTagRequestLine, PriceTagRequestLine.id == PriceTagRequestTag.line_id)
        .filter(
            PriceTagRequestTag.id == tag_id,
            PriceTagRequestLine.request_id == request.id,
        )
        .first()
    )
    if tag is None:
        raise AppException(status_code=404, message="Tag not found.", code="NOT_FOUND")
    return tag


@router.patch(
    "/{request_id}/tags/{tag_id}",
    response_model=PriceTagRequestTagResponse,
)
def update_price_tag_request_tag(
    request_id: str,
    tag_id: str,
    payload: PriceTagRequestTagUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """Quantity, the marketing override and its reason, and "Pick one" (D3).

    All four are tag facts: two tags split off one line print two different
    basins at two different prices, and a line-level figure would put the same
    hand-set number on both.
    """
    tag = _tag_or_404(db, request_id, tag_id)
    data = payload.model_dump(exclude_unset=True)
    if "quantity" in data and data["quantity"] is not None:
        tag.quantity = data["quantity"]
    if "marketing_price_override" in data:
        tag.marketing_price_override = data["marketing_price_override"]
    if "marketing_override_reason" in data:
        tag.marketing_override_reason = data["marketing_override_reason"]
    if data.get("choices") is not None:
        # MERGED, not replaced: a line may leave two groups open and Pick one
        # answers them one at a time.
        PriceTagRequestService.validate_choices(db, tag, data["choices"])
        tag.choices = {**dict(tag.choices or {}), **data["choices"]}
        # Answering a choice changes WHICH products this tag prints, so the pin
        # taken before it describes a different tag (r9 D16). Dropping it makes
        # the next resolve re-pin, instead of reporting marketing's own decision
        # back to marketing as "master data moved".
        tag.pinned_tag_data = None
        tag.pinned_at = None
        tag.data_change_ack_hash = None
    # The body is built BEFORE the commit: it goes back through the resolver, and
    # a failure there used to leave the write applied and answer 500.
    db.flush()
    body = _tag_body(tag, _resolved_by_tag(db, request_id))
    db.commit()
    return body


@router.post(
    "/{request_id}/tags/{tag_id}/split",
    response_model=list[PriceTagRequestTagResponse],
)
def split_price_tag_request_tag(
    request_id: str,
    tag_id: str,
    payload: PriceTagRequestTagSplit,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """"Split into N tags" (AC-S3-4): one tag per candidate of an open group.

    The tag that is there KEEPS ITS ID and takes candidate 1, so it keeps its
    geometry in the saved document and its review pins; N-1 siblings follow it,
    each resolved to one of the remaining candidates in combo order. A split that
    minted N fresh tags would throw away the design marketing had already drawn.

    Answers the LINE's tags, in order, because that is what the rail redraws.
    """
    tag = _tag_or_404(db, request_id, tag_id)
    tags = PriceTagRequestService.split_tag(db, tag, payload.role)
    # Every tag of the split now resolves a different candidate, the original
    # included, so none of their pins still describes what they print (r9 D16).
    # Cleared here and re-taken by the resolve below.
    for row in tags:
        row.pinned_tag_data = None
        row.pinned_at = None
        row.data_change_ack_hash = None
    db.flush()
    resolved = _resolved_by_tag(db, request_id)
    bodies = [_tag_body(row, resolved) for row in tags]
    db.commit()
    return bodies


@router.delete("/{request_id}/tags/{tag_id}", status_code=204)
def delete_price_tag_request_tag(
    request_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """Remove one tag, never the line's last (AC-S3-6).

    A line with no tags can never be printed and never be designed, and nothing
    on screen would say why - so the last one is a named 422 rather than a
    silent no-op.
    """
    tag = _tag_or_404(db, request_id, tag_id)
    PriceTagRequestService.delete_tag(db, tag)
    db.commit()
    return None


def _resolved_by_tag(db: Session, request_id: str) -> dict:
    """The resolver's rows for one request, keyed by tag id.

    Resolved ONCE per response. `_tag_body` used to do this itself, so a split
    into four candidates ran four full resolves of the whole request - four
    passes over every line, every part and the pricing engine - to answer one
    list (review round 2, S3).
    """
    request = PriceTagRequestService.get_request(db, request_id)
    if request is None:
        return {}
    return {
        row["tag_id"]: row
        for row in tag_data_service.resolve_request_line_data(db, request)
    }


def _tag_body(tag: PriceTagRequestTag, resolved: dict) -> dict:
    """One tag in the shape every surface reads, off the ONE resolver so the
    rail, the Lines tab and the PDF cannot disagree."""
    return PriceTagRequestService.tag_body(tag, resolved.get(tag.id))


# ---------------------------------------------------------------------------
# Tag sheet design doc
# ---------------------------------------------------------------------------


def _require_request_page(db: Session, request_id: str) -> tuple[PriceTagRequest, Page]:
    """Look up the request and its tag_sheet page, raising 404 on miss."""
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND",
        )
    if not req.page_id:
        raise AppException(
            status_code=404,
            message="No tag sheet page exists for this request. Claim the request first.",
            code="NO_PAGE",
        )
    page = db.query(Page).filter(Page.id == req.page_id).first()
    if not page:
        raise AppException(
            status_code=404, message="Tag sheet page not found.", code="NOT_FOUND",
        )
    return req, page


def _latest_version(db: Session, page: Page) -> PageVersion | None:
    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page.id)
        .order_by(PageVersion.version.desc())
        .first()
    )


def resolve_tag_sheet_design(db: Session, page: Page, *, prefer: str = "draft") -> dict:
    """The document a design VIEW should open on.

    ``prefer="draft"`` (default - the CRM designer's own GET, ``get_tag_sheet
    _design``): the autosaved draft first, else the latest saved version.
    The autosaved draft is what marketing was last looking at, and opening
    on the version instead would silently discard everything since (B1).

    ``prefer="version"`` (the portal's design preview, D11 review): the
    latest SAVED version always wins, draft or not - a salesperson must
    never see marketing's live in-progress autosave, only what was
    deliberately saved (and, from proof_ready onward, sent for their
    review).

    Shared by this route and the portal's design preview
    (``portal_price_tag.portal_get_price_tag_design``) so the two screens
    read the SAME underlying data and can never disagree about it - only
    which of the two documents they prefer differs. Returns the
    ``TagSheetDocResponse`` fields as a plain dict, not the schema itself -
    the portal route layers its own ``lines`` key on top.
    """
    latest = _latest_version(db, page)
    if prefer == "draft" and page.draft_doc is not None:
        return {
            "page_id": str(page.id),
            "version": latest.version if latest else 0,
            "doc": page.draft_doc,
            "source": "draft",
        }
    return {
        "page_id": str(page.id),
        "version": latest.version if latest else 0,
        "doc": latest.doc if latest else None,
        "source": "version",
    }


def _pins_snapshot(db: Session, page: Page) -> dict:
    """Every TAG's pinned data for the request this page belongs to (D19).

    Keyed by tag id, which is what the document keys its placements on, so a
    restore puts each pin back under the tag that was drawn from it.
    """
    request = (
        db.query(PriceTagRequest).filter(PriceTagRequest.page_id == page.id).first()
    )
    if request is None:
        return {}
    return {
        tag.id: tag.pinned_tag_data
        for line in request.lines
        for tag in line.tags or []
        if tag.pinned_tag_data is not None
    }


def _snapshot_draft(
    db: Session, page: Page, doc: dict, user_id: str | None, commit_message: str | None
) -> PageVersion:
    """Turn a document into the page's next immutable version, draft cleared.

    The one place a ``PageVersion`` is written for a tag sheet, so "a version is
    a deliberate act" cannot drift: the manual Save button and the
    proof-ready transition both come through here, and the autosave route below
    deliberately does not.
    """
    current_max = (
        db.query(func.max(PageVersion.version))
        .filter(PageVersion.page_id == page.id)
        .scalar()
    ) or 0

    version = PageVersion(
        page_id=page.id,
        version=current_max + 1,
        doc=doc,
        commit_message=commit_message,
        created_by=user_id,
        # The pins are half the version (r9 D19): a doc restored over today's
        # product data would show old artwork at new prices.
        pinned_line_data=_pins_snapshot(db, page),
    )
    db.add(version)
    # The draft has become history, so there is no work in progress left. Not
    # clearing it would make the NEXT open show the draft rather than the
    # version that was just saved from it - the same document today, but a
    # trap the moment anything edits one of the two.
    page.draft_doc = None
    return version


@router.get("/{request_id}/design", response_model=TagSheetDesignResponse)
def get_tag_sheet_design(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The document the designer should open on: the draft, else the latest version.

    Draft first (B1). The autosaved draft is what the user was last looking at;
    the latest version is what they last deliberately saved. Reopening on the
    version would silently discard everything since the last Save, which is the
    exact loss autosave exists to prevent.

    ``version`` reports the latest immutable version either way, so a draft says
    which version it is sitting on top of; ``source`` says which of the two the
    ``doc`` actually is.

    It answers the LINES and the three media maps too (r9 S1/D1), from the same
    resolver the PDF reads, so the Design section draws real artwork in one
    call instead of reaching for the library route marketing has no permission
    for.
    """
    req, page = _require_request_page(db, request_id)
    doc_fields = resolve_tag_sheet_design(db, page)
    rows, media = tag_sheet_export_service.design_media(db, req, doc_fields["doc"])
    return TagSheetDesignResponse(
        **doc_fields,
        lines=[ResolvedLineData.model_validate(row) for row in rows],
        **media,
    )


@router.put("/{request_id}/design/draft", response_model=TagSheetDocResponse)
def save_tag_sheet_draft(
    request_id: str,
    payload: TagSheetDocPayload,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """Autosave: overwrite the page's draft IN PLACE. Never writes a version.

    This is the whole point of the split (B1, captain ruling 2 Sep). The
    designer autosaves every committed change roughly once a second; routing
    that through the version route wrote an immutable row per keystroke-burst
    and buried the deliberate saves in noise. One column, overwritten.

    Same ``validate_designable`` gate as the manual Save route: a stale tab on
    an approved or void request must not be able to autosave over the record
    either.
    """
    req, page = _require_request_page(db, request_id)
    PriceTagRequestService.validate_designable(req)

    page.draft_doc = payload.doc
    db.commit()

    latest = _latest_version(db, page)
    return TagSheetDocResponse(
        page_id=str(page.id),
        version=latest.version if latest else 0,
        doc=payload.doc,
        source="draft",
    )


@router.put("/{request_id}/design", response_model=TagSheetDocResponse)
def save_tag_sheet_design(
    request_id: str,
    payload: TagSheetDocPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Manual Save: snapshot the design into a new page_version, draft cleared.

    The deliberate act. Export and proof rendering read versions only, so this
    is what makes a design printable.
    """
    req, page = _require_request_page(db, request_id)
    # The FE only ever reaches this route from a status the Lines tab / header
    # already gated Design on (review: this route wrote a PageVersion in ANY
    # status, so a stale tab on an approved/void/ready request could still
    # save a design over the record).
    PriceTagRequestService.validate_designable(req)

    version = _snapshot_draft(
        db, page, payload.doc, _user_id(user), payload.commit_message
    )
    db.commit()
    db.refresh(version)

    return TagSheetDocResponse(
        page_id=str(page.id),
        version=version.version,
        doc=version.doc,
        source="version",
    )


@router.post("/{request_id}/resolve-prices", response_model=list[ResolvedLineData])
def resolve_prices_for_lines(
    request_id: str,
    tag_ids: Optional[list[str]] = Body(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Resolved display data - including prices - for this request's TAGS (D3).

    Through ``resolve_prices`` and the product master, never off the line row:
    the document stores no figures (ADR 0008), so this is the only place the
    designer's left panel can learn what a tag costs. A marketing override on
    the tag wins over the resolved offer (D9).

    ``tag_ids`` narrows the answer; omitting it resolves every tag, which is what
    the designer asks for when it opens. The body used to be LINE ids and is tag
    ids since S3 (D3) - a line may print several tags, so a line id could no
    longer name one row.
    """
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND",
        )

    rows = tag_data_service.resolve_request_line_data(db, req)
    if tag_ids:
        wanted = set(tag_ids)
        rows = [row for row in rows if row["tag_id"] in wanted]

    return [ResolvedLineData.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.post(
    "/{request_id}/export",
    response_model=TagSheetExportOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def export_tag_sheet(
    request_id: str,
    payload: TagSheetExportIn = TagSheetExportIn(),
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Queue a tag sheet PDF export.

    202, not 201: the file does not exist yet. The response carries the download
    id so the caller can watch it in My Downloads.

    Checks:
    - Request must be in ``approved`` or ``ready`` status.
    - If the request has a promotion, it must not be expired (409).
    - On first export after ``approved``, transitions to ``ready``.

    ``request_tag_sheet_export`` itself enqueues the render (B2) - this route
    just calls it and reports the download; the CRM re-export button and
    ``transition_status``'s own auto-export on approve (D12) share the one
    enqueue.
    """
    from app.services.dealer_kit.tag_sheet_export_service import (
        request_tag_sheet_export,
    )

    download, _sheet_ids = request_tag_sheet_export(
        db,
        request_id=request_id,
        user_id=_user_id(user) or "",
        sheet_ids=payload.sheet_ids,
    )

    db.refresh(download)
    return TagSheetExportOut(
        download_id=download.id,
        status=str(download.status),
        filename=download.filename,
    )
