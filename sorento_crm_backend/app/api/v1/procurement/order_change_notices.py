"""Order change notice staff API (OCN-ORDER-CHANGE-NOTICE).

Rules live in `order_change_notice_service`; this module resolves who is asking and maps the
HTTP shape. Every move commits first and notifies after (`svc.finish`), so a notification
failure never undoes the move. Every move route carries the revision fence, and the
purchase request chain's stage work (send for approval, send back, the decision, done) runs
through the deferred-action dispatcher under the `ocn.*` keys, behind the handling lock.
Literal paths (`/change-types`, `/products`) are declared before `/{ocn_id}`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.order_change_notice import DecisionIn, DoneIn, OrderChangeNoticeWrite, ReasonIn
from app.services import order_change_notice_service as svc
from app.services.error_handler import AppException
from app.services.handling_lock_service import assert_can_act_on_form
from app.services.revision_fence import require_current_revision
from app.services.uuid_path_param import validate_uuid_path
from app.utils.multi_value import multi_uuids, multi_values

router = APIRouter()


def _actor(db: Session, user: dict) -> svc.Actor:
    return svc.actor_from_slugs(user["id"], permission_slugs(db, user["id"]))


def _reader(db: Session, user: dict) -> svc.Actor:
    actor = _actor(db, user)
    if not svc.can_view(actor):
        raise AppException(status_code=403, message=f"Permission required: {svc.VIEW}", code="FORBIDDEN")
    return actor


def _load(db: Session, ocn_id: str, *, for_update: bool = False):
    return svc.get_for(db, validate_uuid_path(ocn_id, resource="Order change notice"), for_update=for_update)


def _readable(db: Session, user: dict, ocn_id: str, *, for_update: bool = False):
    """The notice and the actor, after the reader check: a grant first (403 without one), then
    the row in the caller's company and `assert_can_view` (404 when it is not theirs to see)."""
    actor = _reader(db, user)
    row = _load(db, ocn_id, for_update=for_update)
    svc.assert_can_view(row, actor)
    return row, actor


#: What each stage move needs, checked BEFORE the dispatcher may park it (security review M1):
#: a user without it gets 403 at once, never a countdown that fails at commit.
_MOVE_NEEDS = {
    "edit": ("can_edit", "You cannot send order change notices for approval or back."),
    "approve": ("can_approve", "You cannot approve or reject order change notices."),
    "process": ("can_process", "You cannot mark order change notices done."),
}


def _move(db: Session, user: dict, ocn_id: str, fn, **kw):
    """The raiser's and the editor's own moves (submit, void, revise): no stage lock."""
    try:
        row, actor = _readable(db, user, ocn_id, for_update=True)
        event = fn(db, row, actor=actor, **kw)
        return svc.finish(db, row, event, actor.user_id)
    except Exception:
        db.rollback()
        raise


def _stage_work(db: Session, user: dict, request: Request, ocn_id: str, *, action_key: str,
                entity_type: str, payload: dict, event_name: str, needs: str):
    """A stage move: the record is checked and the handling lock applied here, then the
    deferred-action dispatcher runs it now or parks it (`form_actions` `ocn.*`). A parked one
    answers the dispatcher's 202 body as is."""
    from app.services.form_action_dispatch import dispatch_or_defer

    try:
        row, actor = _readable(db, user, ocn_id)
        flag, refusal = _MOVE_NEEDS[needs]
        if not getattr(actor, flag):
            raise AppException(status_code=403, message=refusal, code="FORBIDDEN")
        assert_can_act_on_form(db, str(row.id), user, source_entity_type=svc.ENTITY)
        outcome = dispatch_or_defer(
            db,
            user,
            request,
            action_key=action_key,
            entity_type=entity_type,
            entity_id=str(row.id),
            payload={"ocn_id": str(row.id), **payload},
            event_name=event_name,
        )
    except Exception:
        db.rollback()
        raise
    return outcome


@router.get("/change-types")
def list_change_types(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _reader(db, user)
    return svc.change_types(db)


@router.get("/products")
def search_products(q: str = Query(""), user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """The line picker: active catalogue products only (no free-text line), the sample request's
    own product search."""
    from app.services import sample_request_service

    _reader(db, user)
    return sample_request_service.search_products(db, q)


@router.get("")
def list_notices(
    status_filter: Optional[list[str]] = Query(None, alias="status"),
    change_type_id: Optional[list[str]] = Query(None),
    risk_level: Optional[list[str]] = Query(None),
    q: Optional[str] = Query(None),
    # The DataGrid's standard search key (`buildDataGridParams`); `q` stays for API callers.
    query: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_for(
        db,
        actor=_reader(db, user),
        statuses=multi_values(status_filter),
        change_type_ids=multi_uuids(change_type_id, "Change type"),
        risk_levels=multi_values(risk_level),
        q=query or q,
        page=page,
        limit=limit,
        sort=sort,
        direction=dir,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_notice(
    payload: OrderChangeNoticeWrite,
    user: dict = Depends(require_permission(svc.CREATE)),
    db: Session = Depends(get_db),
):
    try:
        row = svc.create_draft(db, actor=_actor(db, user), data=payload.model_dump(exclude_unset=True))
        return svc.finish(db, row, None, user["id"])
    except Exception:
        db.rollback()
        raise


@router.get("/{ocn_id}")
def get_notice(ocn_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    row, _actor_ = _readable(db, user, ocn_id)
    return svc.serialize_detail(db, row)


@router.put(
    "/{ocn_id}",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def update_notice(
    ocn_id: str,
    payload: OrderChangeNoticeWrite,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row, actor = _readable(db, user, ocn_id, for_update=True)
        svc.update(db, row, actor=actor, data=payload.model_dump(exclude_unset=True))
        return svc.finish(db, row, None, actor.user_id)
    except Exception:
        db.rollback()
        raise


@router.post(
    "/{ocn_id}/submit",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def submit(ocn_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _move(db, user, ocn_id, svc.submit)


@router.post(
    "/{ocn_id}/send-for-approval",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def send_for_approval(
    ocn_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _stage_work(
        db, user, request, ocn_id,
        action_key="ocn.send_for_approval",
        entity_type="order_change_notice",
        needs="edit",
        payload={"actor_user_id": user.get("id")},
        event_name="send_for_approval",
    )


@router.post(
    "/{ocn_id}/reject-submitted",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def reject_submitted(
    ocn_id: str,
    payload: ReasonIn,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _stage_work(
        db, user, request, ocn_id,
        action_key="ocn.reject_submitted",
        entity_type="order_change_notice",
        needs="edit",
        payload={"rejection_reason": payload.reason, "actor_user_id": user.get("id")},
        event_name="reject_submitted",
    )


@router.post(
    "/{ocn_id}/approval-decision",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def approval_decision(
    ocn_id: str,
    payload: DecisionIn,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _stage_work(
        db, user, request, ocn_id,
        action_key="ocn.approval_decision",
        entity_type="order_change_notice",
        needs="approve",
        payload={
            "action": payload.action,
            "approval_comments": payload.comments,
            "actor_user_id": user.get("id"),
        },
        event_name="approved" if payload.action == "approved" else "approval_rejected",
    )


@router.post(
    "/{ocn_id}/done",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def mark_done(
    ocn_id: str,
    request: Request,
    payload: Optional[DoneIn] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _stage_work(
        db, user, request, ocn_id,
        action_key="ocn.finalize",
        entity_type="order_change_notice",
        needs="process",
        payload={
            "new_status": svc.DONE,
            "note": payload.cs_comment if payload else None,
            "crm_sender_user_id": user.get("id"),
        },
        event_name="resolved",
    )


@router.post(
    "/{ocn_id}/void",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def void(
    ocn_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, ocn_id, svc.void, reason=payload.reason)


@router.post(
    "/{ocn_id}/revise",
    dependencies=[Depends(require_current_revision("order_change_notice", "ocn_id"))],
)
def revise(
    ocn_id: str,
    payload: ReasonIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _move(db, user, ocn_id, svc.revise, reason=payload.reason)

