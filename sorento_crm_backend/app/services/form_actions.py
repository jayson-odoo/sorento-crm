"""Concrete deferrable actions (PLAN-form-sla-undo.md §Action registry).

Every entry wraps an EXISTING service method. `execute` must not contain logic of its
own - if it did, a deferred approve would stop matching an immediate one, and the
equivalence test that pins them together is the only thing standing between us and a
silent divergence.

`columns` lists exactly what the wrapped method assigns, read out of the method bodies
rather than guessed. A reviewer should be able to diff each list against its method and
find them identical. `capture` snapshots those columns before the method runs; `invert`
writes the snapshot back. An inverse that writes a constant instead of a captured value
is a review failure.

13 actions, from 18 live (form, resolve-event) pairs. `workflow_submission` is excluded:
it carries an active config row but nothing in the codebase emits a form-SLA event for
it and it has zero trackers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.form_action_registry import FormAction, register

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Entity accessors - one per form family.
# --------------------------------------------------------------------------------------


def _pr_service(db: Session):
    from app.services.procurement_service import PurchaseRequestService

    return PurchaseRequestService(db)


def _si_service(db: Session):
    from app.services.procurement_service import StockInquiryService

    return StockInquiryService(db)


def _cx_service(db: Session):
    from app.services.complaints_service import ComplaintService

    return ComplaintService(db)


def _get_request(db: Session, payload: dict):
    return _pr_service(db).get_request(payload["request_id"])


def _get_inquiry(db: Session, payload: dict):
    return _si_service(db).get_inquiry(payload["inquiry_id"])


def _get_complaint(db: Session, payload: dict):
    return _cx_service(db).get_complaint(payload["complaint_id"])


def _get_ticket(db: Session, payload: dict):
    from app.models.tickets import Ticket

    return db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()


# --------------------------------------------------------------------------------------
# The shape every action shares.
# --------------------------------------------------------------------------------------


def _jsonable(value):
    """Snapshots round-trip through JSONB, so datetimes have to survive as text."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _restore(value):
    if isinstance(value, str):
        # Only a full ISO timestamp round-trips back to a datetime; a plain status
        # string must stay a string.
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _declare(
    *,
    key: str,
    entity_types: tuple[str, ...],
    label: str,
    getter: Callable,
    columns: Sequence[str],
    runner: Callable,
    resolve_event: Callable,
    tells_contact: bool = False,
    invertible: bool = True,
) -> FormAction:
    """Register one action from a declaration, so all 13 share one implementation of
    capture-and-restore rather than 13 hand-written near-copies."""

    def capture(db: Session, payload: dict) -> dict:
        entity = getter(db, payload)
        if entity is None:
            return {}
        return {col: _jsonable(getattr(entity, col, None)) for col in columns}

    def invert(db: Session, record) -> None:
        entity = getter(db, dict(record.payload_json or {}))
        if entity is None:
            return
        prior = dict(record.prior_state_json or {})
        for col in columns:
            if col in prior:
                setattr(entity, col, _restore(prior[col]))
        db.commit()

    return register(
        FormAction(
            key=key,
            entity_types=entity_types,
            execute=runner,
            capture=capture,
            invert=invert if invertible else None,
            resolve_event=resolve_event,
            tells_contact=tells_contact,
            label=label,
        )
    )


PR_TYPES = ("purchase_request", "sponsorship_form")

# --------------------------------------------------------------------------------------
# #3 pr.approval_decision - the incident this feature exists for.
# --------------------------------------------------------------------------------------

_declare(
    key="pr.approval_decision",
    entity_types=PR_TYPES,
    label="Approval",
    getter=_get_request,
    columns=(
        "approval_status",
        "status",
        "approved_at",
        "approved_by",
        "rejected_by_id",
        "approval_signature_ref",
        "approval_comments",
    ),
    # `decide_approval` re-asserts the request is still pending before acting, so it
    # doubles as the commit-time premise check (AC-D-8).
    runner=lambda db, p: _pr_service(db).decide_approval(
        p["request_id"],
        action=p["action"],
        approved_by=p.get("approved_by"),
        approval_comments=p.get("approval_comments"),
        actor_user_id=p.get("actor_user_id"),
    ),
    resolve_event=lambda p: (
        "approved" if p.get("action") == "approved" else "approval_rejected"
    ),
    tells_contact=True,
)

# --------------------------------------------------------------------------------------
# #1, #2, #4, #5 - the rest of the PR / SF chain.
# --------------------------------------------------------------------------------------

_declare(
    key="pr.send_for_approval",
    entity_types=PR_TYPES,
    label="Send for approval",
    getter=_get_request,
    columns=(
        "approval_status",
        "approved_at",
        "approved_by",
        "approval_signature_ref",
        "approval_comments",
        "requested_approval_by_user_id",
    ),
    runner=lambda db, p: _pr_service(db).set_pending_approval(
        p["request_id"], requested_by_user_id=p.get("actor_user_id")
    ),
    resolve_event=lambda _p: "send_for_approval",
)

_declare(
    key="pr.reject_submitted",
    entity_types=PR_TYPES,
    label="Rejection",
    getter=_get_request,
    columns=(
        "approval_status",
        "status",
        "approval_comments",
        "approved_at",
        "approved_by",
        "rejected_by_id",
        "approval_signature_ref",
        "requested_approval_by_user_id",
    ),
    runner=lambda db, p: _pr_service(db).reject_submitted(
        p["request_id"],
        rejection_reason=p.get("rejection_reason"),
        actor_user_id=p.get("actor_user_id"),
    ),
    resolve_event=lambda _p: "reject_submitted",
    tells_contact=True,
)

_declare(
    key="pr.finalize",
    entity_types=PR_TYPES,
    label="Customer service outcome",
    getter=_get_request,
    # `_finalize_request` assigns ONLY `status` - the resolved_at / resolved_by pair
    # belongs to the complaint finalize, not this one.
    columns=("status",),
    runner=lambda db, p: _pr_service(db)._finalize_request(
        p["request_id"],
        p["new_status"],
        note=p.get("note"),
        respond_user_id=p.get("respond_user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
    ),
    resolve_event=lambda _p: "resolved",
    tells_contact=True,
)

_declare(
    key="pr.void",
    entity_types=PR_TYPES,
    label="Void",
    getter=_get_request,
    columns=("status", "voided_by", "voided_at", "void_reason"),
    runner=lambda db, p: _pr_service(db).void_request(
        p["request_id"],
        void_reason=p.get("void_reason"),
        actor_user_id=p.get("actor_user_id"),
        respond_user_id=p.get("respond_user_id"),
    ),
    resolve_event=lambda _p: "voided",
)

# --------------------------------------------------------------------------------------
# #6..#10 - stock inquiry.
# --------------------------------------------------------------------------------------

_declare(
    key="si.project_sales_approve",
    entity_types=("stock_inquiry",),
    label="Project sales approval",
    getter=_get_inquiry,
    columns=("status", "rejection_reason", "rejected_at", "rejected_by", "rejected_from"),
    runner=lambda db, p: _si_service(db).project_sales_approve_inquiry(
        p["inquiry_id"],
        actor_user_id=p.get("actor_user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
        respond_user_id_fallback=p.get("respond_user_id_fallback"),
    ),
    resolve_event=lambda _p: "project_sales_approve",
    tells_contact=True,
)

_declare(
    key="si.project_sales_reject",
    entity_types=("stock_inquiry",),
    label="Project sales rejection",
    getter=_get_inquiry,
    columns=("status", "rejected_from", "rejection_reason", "rejected_at", "rejected_by"),
    runner=lambda db, p: _si_service(db).project_sales_reject_inquiry(
        p["inquiry_id"],
        reason=p.get("reason"),
        user_id=p.get("user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
        respond_user_id_fallback=p.get("respond_user_id_fallback"),
    ),
    resolve_event=lambda _p: "project_sales_reject",
    tells_contact=True,
)

_declare(
    key="si.purchasing_decide",
    entity_types=("stock_inquiry",),
    label="Purchasing decision",
    getter=_get_inquiry,
    columns=("status", "rejected_from", "rejection_reason", "rejected_at", "rejected_by"),
    runner=lambda db, p: _si_service(db).purchasing_reject_inquiry(
        p["inquiry_id"],
        reason=p.get("reason"),
        user_id=p.get("user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
        respond_user_id_fallback=p.get("respond_user_id_fallback"),
    ),
    resolve_event=lambda _p: "purchasing_decide",
    tells_contact=True,
)

def _si_respond_runner(db: Session, p: dict):
    """Rehydrate the payload dict back into the schema the service expects.

    The route holds a `StockInquiryUpdate`; the deferral parks it in JSONB as a plain
    dict (`model_dump(mode="json", exclude_unset=True)`). Passing that dict straight
    through would crash at commit time - the service reads model attributes, and the
    crash would land 10 seconds after the user clicked, on a code path they cannot see.
    """
    from app.schemas.procurement import StockInquiryUpdate

    return _si_service(db).update_inquiry_and_reply(
        p["inquiry_id"],
        inquiry_data=StockInquiryUpdate(**(p.get("inquiry_data") or {})),
        respond_user_id=p.get("respond_user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
        request_url=p.get("request_url", ""),
    )


_declare(
    key="si.purchasing_respond",
    entity_types=("stock_inquiry",),
    label="Purchasing response",
    getter=_get_inquiry,
    columns=("status", "last_responded_by", "last_responded_at"),
    runner=_si_respond_runner,
    resolve_event=lambda _p: "purchasing_respond",
    # The whole point of this action is the message to the contact. An undo restores the
    # state but cannot recall what they already read - the dialog says so.
    tells_contact=True,
)

_declare(
    key="si.void",
    entity_types=("stock_inquiry",),
    label="Void",
    getter=_get_inquiry,
    columns=("status", "voided_by", "voided_at", "void_reason"),
    runner=lambda db, p: _si_service(db).void_inquiry(
        p["inquiry_id"],
        void_reason=p.get("void_reason"),
        actor_user_id=p.get("actor_user_id"),
        respond_user_id=p.get("respond_user_id"),
    ),
    resolve_event=lambda _p: "voided",
)

# --------------------------------------------------------------------------------------
# #11, #12 - complaint.
# --------------------------------------------------------------------------------------

_declare(
    key="cx.decide",
    entity_types=("complaint",),
    label="Decision",
    getter=_get_complaint,
    columns=(
        "status",
        "last_responded_by",
        "last_responded_at",
        "rejection_reason",
        "rejected_at",
        "rejected_by",
    ),
    runner=lambda db, p: _cx_service(db).decide_complaint(
        p["complaint_id"],
        decision=p["decision"],
        respond_user_id=p.get("respond_user_id"),
        request_url=p.get("request_url", ""),
        crm_sender_user_id=p.get("crm_sender_user_id"),
        rejection_reason=p.get("rejection_reason"),
    ),
    # 'approved' is the only decision that advances to customer service; the others
    # close the stage where it stands.
    resolve_event=lambda p: str(p.get("decision") or "approved"),
    tells_contact=True,
)

_declare(
    key="cx.finalize",
    entity_types=("complaint",),
    label="Resolution",
    getter=_get_complaint,
    columns=("status", "resolved_at", "resolved_by"),
    runner=lambda db, p: _cx_service(db)._finalize_complaint(
        p["complaint_id"],
        p["new_status"],
        note=p.get("note"),
        respond_user_id=p.get("respond_user_id"),
        crm_sender_user_id=p.get("crm_sender_user_id"),
    ),
    resolve_event=lambda _p: "resolved",
    tells_contact=True,
)

# --------------------------------------------------------------------------------------
# #13 - ticket.
# --------------------------------------------------------------------------------------

_declare(
    key="tk.resolve",
    entity_types=("ticket",),
    label="Resolution",
    getter=_get_ticket,
    columns=(
        "resolution_html",
        "resolution_text",
        "resolved_by",
        "resolved_at",
        "resolution_time_hours",
        "status",
    ),
    runner=lambda db, p: __import__(
        "app.services.tickets_service", fromlist=["update_resolution_and_reply"]
    ).update_resolution_and_reply(
        db,
        ticket_id=p["ticket_id"],
        resolution_html=p.get("resolution_html") or "",
        resolution_text=p.get("resolution_text"),
        current_user=p.get("current_user") or {},
    ),
    resolve_event=lambda _p: "resolved",
    tells_contact=True,
)
