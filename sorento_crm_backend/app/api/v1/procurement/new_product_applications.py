"""New product application staff API (NEW-PRODUCT-APP).

Rules live in `new_product_application_service`; this module resolves who is asking and maps
the HTTP shape. Every move commits first and notifies after (`svc.notify`), so a notification
failure never undoes the move. Literal paths (`/prefill`, `/products`) are
declared before `/{application_id}`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import get_current_user, require_any_permission, require_permission
from app.schemas.new_product_application import (
    FeedbackIn,
    AttachmentLinkIn,
    LinkIn,
    NewProductApplicationWrite,
    PurchasingResponseIn,
    ReasonIn,
)
from app.services import new_product_application_service as svc
from app.services import npa_xlsx
from app.services.error_handler import AppException
from app.utils.multi_value import multi_uuids, multi_values
from app.services.uuid_path_param import validate_uuid_path
from app.utils.http import content_disposition

#: The product page's own view slug: its Lineage tab reads this route.
PRODUCTS_VIEW = "master_data.products.view"

router = APIRouter()

_ANY = (svc.VIEW, svc.VIEW_OWN, svc.CREATE, svc.APPROVE, svc.OPEN_CODE)


def _actor(db: Session, user: dict, slugs=None) -> svc.Actor:
    from app.services import own_scope

    slugs = permission_slugs(db, user["id"]) if slugs is None else slugs
    actor = svc.actor_from_slugs(user["id"], slugs)
    if actor.own_only:
        actor.own_contact_id = own_scope.me(db, user["id"]).contact_id
    return actor


def _own(db: Session, user: dict, app) -> svc.Actor:
    """The actor for a write. A `.view_own` holder gets a row that is not theirs as not
    found, before the write's own owner rule (403) answers (PORTAL-P2-ONLY-THEIRS)."""
    actor = _actor(db, user)
    if actor.own_only:
        svc.assert_can_view(app, actor)
    return actor


def _any_actor(db: Session, user: dict) -> svc.Actor:
    slugs = permission_slugs(db, user["id"])
    if not set(slugs) & set(_ANY):
        raise AppException(
            status_code=403, message=f"Permission required: {svc.VIEW}", code="FORBIDDEN"
        )
    return _actor(db, user, slugs)


def _load(db: Session, application_id: str, *, for_update: bool = False):
    return svc.get_for(
        db,
        validate_uuid_path(application_id, resource="New product application"),
        for_update=for_update,
    )


def _done(db: Session, app, event: Optional[str] = None, actor_id: Optional[str] = None):
    """Commit, then tell whoever now has to act, then answer with the fresh record."""
    db.commit()
    if event:
        svc.notify(db, app, event, actor_id=actor_id)
        db.commit()
    db.refresh(app)
    return svc.serialize_detail(db, app)


@router.get("/prefill")
def prefill(
    stock_inquiry_id: str = Query(...),
    _user: dict = Depends(require_permission(svc.CREATE)),
    db: Session = Depends(get_db),
):
    return svc.prefill(db, stock_inquiry_id)


@router.get("/products")
def search_products(
    q: str = Query(""),
    # The applicant picks current codes here too (NPA-FROM-SI rule 4), purchasing the new code.
    _user: dict = Depends(require_any_permission([svc.CREATE, svc.OPEN_CODE])),
    db: Session = Depends(get_db),
):
    return svc.search_products(db, q)


def _id_list(raw: str) -> list:
    return [part.strip() for part in (raw or "").split(",") if part.strip()][:20]


@router.get("/reuse-suggestions")
def reuse_suggestions(
    product_ids: str = Query(""),
    _user: dict = Depends(
        require_any_permission([svc.CREATE, svc.VIEW, svc.APPROVE, svc.OPEN_CODE])
    ),
    db: Session = Depends(get_db),
):
    """NPA-FROM-SI rule 6: codes created before from exactly these current codes (a suggestion).
    The earlier application's remark only for NPA view-all holders (security review round 3)."""
    actor = svc.actor_from_slugs(_user["id"], permission_slugs(db, _user["id"]))
    return svc.reuse_suggestions(db, _id_list(product_ids), full_why=actor.can_view_all)


@router.get("/lineage")
def product_lineage(
    product_id: str = Query(...),
    user: dict = Depends(
        require_any_permission([svc.VIEW, svc.APPROVE, svc.OPEN_CODE, PRODUCTS_VIEW])
    ),
    db: Session = Depends(get_db),
):
    """NPA-FROM-SI rule 5: a product's lineage. Application links only for NPA viewers."""
    actor = svc.actor_from_slugs(user["id"], permission_slugs(db, user["id"]))
    return svc.lineage(db, product_id, can_view_applications=actor.can_view_all)


@router.get("")
def list_applications(
    status_filter: Optional[list[str]] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    stock_inquiry_id: Optional[str] = Query(None),
    applicant_id: Optional[list[str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statuses = multi_values(status_filter)
    applicant_ids = multi_uuids(applicant_id, "Applicant")
    return svc.list_for(
        db,
        actor=_any_actor(db, user),
        statuses=statuses,
        q=q,
        stock_inquiry_id=stock_inquiry_id,
        applicant_id=applicant_ids,
        page=page,
        limit=limit,
        sort=sort,
        direction=dir,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    payload: NewProductApplicationWrite,
    user: dict = Depends(require_permission(svc.CREATE)),
    db: Session = Depends(get_db),
):
    try:
        app = svc.create_draft(db, applicant_id=user["id"], data=payload.model_dump(exclude_unset=True))
        return _done(db, app)
    except Exception:
        db.rollback()
        raise


@router.get("/{application_id}")
def get_application(
    application_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _load(db, application_id)
    actor = _actor(db, user)
    svc.assert_can_view(app, actor)
    # A salesperson limited to their own applications reads the portal's shape: no item group,
    # base UOM or list price (PORTAL-P4-REQUESTS S5).
    return svc.serialize_detail(db, app, portal=actor.own_only)


@router.put("/{application_id}")
def update_application(
    application_id: str,
    payload: NewProductApplicationWrite,
    user: dict = Depends(require_permission(svc.CREATE)),
    db: Session = Depends(get_db),
):
    try:
        app = _load(db, application_id, for_update=True)
        svc.update(db, app, actor=_own(db, user, app), data=payload.model_dump(exclude_unset=True))
        return _done(db, app)
    except Exception:
        db.rollback()
        raise


@router.get("/{application_id}/download")
def download_application(
    application_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The paper sheet as a workbook (AC-NPA-77), for whoever can view the record."""
    app = _load(db, application_id)
    svc.assert_can_view(app, _actor(db, user))
    content, filename = npa_xlsx.to_xlsx(db, app)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename)},
    )


def _move(db: Session, user: dict, application_id: str, fn, **kw):
    try:
        app = _load(db, application_id, for_update=True)
        actor = _actor(db, user)
        svc.assert_can_view(app, actor)
        event = fn(db, app, actor=actor, **kw)
        return _done(db, app, event, actor.user_id)
    except Exception:
        db.rollback()
        raise


@router.post("/{application_id}/submit")
def submit(application_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, user, application_id, svc.submit)


@router.post("/{application_id}/approve")
def approve(application_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, user, application_id, svc.approve)


@router.post("/{application_id}/reject")
def reject(
    application_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, application_id, svc.reject, reason=payload.reason)


@router.post("/{application_id}/revise")
def revise(
    application_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, application_id, svc.revise, reason=payload.reason)


@router.post("/{application_id}/cancel")
def cancel(
    application_id: str,
    payload: Optional[ReasonIn] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, application_id, svc.cancel, reason=payload.reason if payload else None)


def _line_move(db: Session, user: dict, application_id: str, line_id: str, fn, **kw):
    try:
        app = _load(db, application_id, for_update=True)
        actor = _actor(db, user)
        svc.assert_can_view(app, actor)
        event = fn(db, app, validate_uuid_path(line_id, resource="Line"), actor=actor, **kw)
        return _done(db, app, event, actor.user_id)
    except Exception:
        db.rollback()
        raise


@router.post("/{application_id}/lines/{line_id}/link")
def link_line(
    application_id: str,
    line_id: str,
    payload: LinkIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _line_move(db, user, application_id, line_id, svc.link_line, product_id=payload.product_id)


@router.post("/{application_id}/lines/{line_id}/close")
def close_line(
    application_id: str,
    line_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _line_move(db, user, application_id, line_id, svc.close_line, reason=payload.reason)


@router.post("/{application_id}/lines/{line_id}/undo")
def undo_line(
    application_id: str,
    line_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _line_move(db, user, application_id, line_id, svc.undo_line)


@router.post("/{application_id}/new-code/link")
def link_new_code(
    application_id: str,
    payload: LinkIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """NPA-FROM-SI: the ONE new product code (owner, mock v3)."""
    return _move(db, user, application_id, svc.link_new_code, product_id=payload.product_id)


@router.post("/{application_id}/new-code/close")
def close_new_code(
    application_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, application_id, svc.close_new_code, reason=payload.reason)


@router.post("/{application_id}/new-code/undo")
def undo_new_code(application_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, user, application_id, svc.undo_new_code)


@router.post("/{application_id}/purchasing-reject")
def purchasing_reject(
    application_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner 8 Nov 09:30: purchasing's Reject, as on the stock inquiry page."""
    return _move(db, user, application_id, svc.purchasing_reject, reason=payload.reason)


@router.post("/{application_id}/purchasing-response/reply")
def save_purchasing_response_and_reply(
    application_id: str,
    payload: PurchasingResponseIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner 8 Nov 15:10: the stock inquiry's "Update & Reply" on the NPA. Saves like Save only,
    then sends the reply to the salesperson through the linked stock inquiry's conversation, with
    the stock inquiry's own chat send (`enqueue_chat_send`, use case stock_inquiry_chat)."""
    from app.api.v1._respond_chat_template_routes import enqueue_chat_send
    from app.api.v1.procurement import stock_inquiries as si_routes
    from app.services.error_handler import AppException

    def refuse(message: str, field: str) -> AppException:
        return AppException(status_code=422, message=message, code="VALIDATION_ERROR", details={"field": field})

    if not (payload.purchasing_response or "").strip():
        raise refuse("Enter a purchasing response first.", "purchasing_response")
    try:
        app = _load(db, application_id, for_update=True)
        actor = _actor(db, user)
        svc.assert_can_view(app, actor)
        event = svc.save_purchasing_response(db, app, actor=actor, data=payload.model_dump(exclude_unset=True))
        if not app.stock_inquiry_id:
            raise refuse("Only an application raised from a stock inquiry can reply.", "stock_inquiry_id")
        identifier, contact_id = si_routes._resolve_stock_inquiry_chat_contact(db, str(app.stock_inquiry_id))
        if not identifier:
            raise refuse("The stock inquiry has no Respond.io contact to reply to.", "stock_inquiry_id")
        # The send's own DB-only precheck (template / window) BEFORE the commit, so a reply that
        # cannot be sent refuses with nothing saved (review round 6).
        from app.services.respond_chat_template_service import precheck_chat_send

        precheck_chat_send(db, identifier=identifier, respond_contact_id=contact_id, chat_use_case="stock_inquiry_chat")
        message = svc.reply_message(db, app)
        inquiry_id = str(app.stock_inquiry_id)
        detail = _done(db, app, event, actor.user_id)
    except Exception:
        db.rollback()
        raise
    enqueue_chat_send(
        db,
        identifier=identifier,
        respond_contact_id=contact_id,
        chat_use_case="stock_inquiry_chat",
        business_table="stock_inquiries",
        entity_id=inquiry_id,
        text=message,
        current_user=user,
        context_builder=si_routes._build_stock_inquiry_chat_context,
    )
    return detail


@router.put("/{application_id}/purchasing-response")
def save_purchasing_response(
    application_id: str,
    payload: PurchasingResponseIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner 8 Nov: purchasing's one dialog (outcome, lead time, cost)."""
    return _move(
        db, user, application_id, svc.save_purchasing_response, data=payload.model_dump(exclude_unset=True)
    )


@router.put("/{application_id}/feedback")
def save_feedback(
    application_id: str,
    payload: FeedbackIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, application_id, svc.save_feedback, data=payload.model_dump(exclude_unset=True))


@router.post("/{application_id}/attachments", status_code=status.HTTP_201_CREATED)
def link_attachment(
    application_id: str,
    payload: AttachmentLinkIn,
    user: dict = Depends(require_permission(svc.CREATE)),
    db: Session = Depends(get_db),
):
    """Link a file from the attachment library (the Stock Inquiry flow); unlink is a pending action."""
    try:
        app = _load(db, application_id, for_update=True)
        svc.link_attachment(db, app, actor=_own(db, user, app), attachment_id=payload.attachment_id)
        return _done(db, app)
    except Exception:
        db.rollback()
        raise
