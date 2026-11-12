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

13 actions, from 18 live (form, resolve-event) pairs, plus the order change notice's run
of the purchase request chain (`_declare_approval_chain`, OCN-ORDER-CHANGE-NOTICE).
`workflow_submission` is excluded: it carries an active config row but nothing in the
codebase emits a form-SLA event for it and it has zero trackers.
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
    """Snapshots round-trip through JSONB, so datetimes survive as a MARKED wrapper.

    The marker matters: restoring by "does it parse as ISO?" coerces user-typed free
    text too - an approver whose comment is "2025-10-01" would get a datetime written
    back into a String column on undo. Only values that WERE datetimes at capture
    time come back as datetimes.
    """
    if hasattr(value, "isoformat"):
        return {"$dt": value.isoformat()}
    return value


def _restore(value):
    if isinstance(value, dict) and set(value.keys()) == {"$dt"}:
        try:
            return datetime.fromisoformat(value["$dt"])
        except (TypeError, ValueError):
            return value["$dt"]
    # Plain strings stay strings. Legacy snapshots (pre-marker) stored datetimes as
    # bare ISO text; Postgres casts those into timestamp columns on write, so passing
    # them through unchanged is still correct - and free text is never mangled.
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
    payload_columns: Optional[Callable[[dict], Sequence[str]]] = None,
) -> FormAction:
    """Register one action from a declaration, so all 13 share one implementation of
    capture-and-restore rather than 13 hand-written near-copies.

    `payload_columns` is for the one action shape whose write set is NOT fixed: a
    method that applies whatever fields the caller submitted must have those fields
    snapshotted too, or the inverse restores a half-reverted record.
    """

    def capture(db: Session, payload: dict) -> dict:
        entity = getter(db, payload)
        if entity is None:
            return {}
        cols = list(columns)
        if payload_columns is not None:
            for extra in payload_columns(dict(payload or {})):
                if extra not in cols and hasattr(entity, extra):
                    cols.append(extra)
        return {col: _jsonable(getattr(entity, col, None)) for col in cols}

    def invert(db: Session, record) -> None:
        entity = getter(db, dict(record.payload_json or {}))
        if entity is None:
            return
        # Iterate the SNAPSHOT, not the declared columns: capture decides the scope
        # once (including any payload-derived extras), and the inverse restores
        # exactly what was captured - never more, never less.
        prior = dict(record.prior_state_json or {})
        for col, value in prior.items():
            if hasattr(entity, col):
                setattr(entity, col, _restore(value))
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
OCN_TYPES = ("order_change_notice",)


def _ocn_service(db: Session):
    """The order change notice's chain runner: the purchase request service's method names
    and signatures over the OCN (OCN-ORDER-CHANGE-NOTICE)."""
    from app.services.order_change_notice_service import ChainRunner

    return ChainRunner(db)


def _get_ocn(db: Session, payload: dict):
    from app.services import order_change_notice_service

    return order_change_notice_service.find(db, payload["ocn_id"])


def _declare_approval_chain(
    prefix: str,
    entity_types: tuple[str, ...],
    getter: Callable,
    service: Callable,
    id_key: str,
    *,
    extra_columns: Optional[dict] = None,
) -> None:
    """The purchase request approval chain's five actions, for one form family.

    Declared once and called per family (`pr.*` for the purchase request / sponsorship form,
    `ocn.*` for the order change notice), so the two chains cannot drift: the same columns,
    the same runner method names (`service(db)` must offer `decide_approval`,
    `set_pending_approval`, `reject_submitted`, `_finalize_request`, `void_request`, each
    taking the record id first) and the same resolve events. `extra_columns` widens one
    action's capture for a family that writes a column the other has not got.
    """
    extra = dict(extra_columns or {})

    def cols(action: str, base: tuple[str, ...]) -> tuple[str, ...]:
        return base + tuple(extra.get(action, ()))

    # #3 approval_decision - the incident this feature exists for.
    _declare(
        key=f"{prefix}.approval_decision",
        entity_types=entity_types,
        label="Approval",
        getter=getter,
        columns=cols("approval_decision", (
            "approval_status",
            "status",
            "approved_at",
            "approved_by",
            "rejected_by_id",
            "approval_signature_ref",
            "approval_comments",
        )),
        # `decide_approval` re-asserts the record is still pending before acting, so it
        # doubles as the commit-time premise check (AC-D-8).
        runner=lambda db, p: service(db).decide_approval(
            p[id_key],
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

    # #1, #2, #4, #5 - the rest of the chain.
    _declare(
        key=f"{prefix}.send_for_approval",
        entity_types=entity_types,
        label="Send for approval",
        getter=getter,
        columns=cols("send_for_approval", (
            "approval_status",
            "approved_at",
            "approved_by",
            "approval_signature_ref",
            "approval_comments",
            "requested_approval_by_user_id",
        )),
        runner=lambda db, p: service(db).set_pending_approval(
            p[id_key], requested_by_user_id=p.get("actor_user_id")
        ),
        resolve_event=lambda _p: "send_for_approval",
        # set_pending_approval messages the contact ("sent for approval") since the
        # 2026-08 fix - the undo dialog must disclose that a correction will follow.
        tells_contact=True,
    )

    _declare(
        key=f"{prefix}.reject_submitted",
        entity_types=entity_types,
        label="Rejection",
        getter=getter,
        columns=cols("reject_submitted", (
            "approval_status",
            "status",
            "approval_comments",
            "approved_at",
            "approved_by",
            "rejected_by_id",
            "approval_signature_ref",
            "requested_approval_by_user_id",
        )),
        runner=lambda db, p: service(db).reject_submitted(
            p[id_key],
            rejection_reason=p.get("rejection_reason"),
            actor_user_id=p.get("actor_user_id"),
        ),
        resolve_event=lambda _p: "reject_submitted",
        tells_contact=True,
    )

    _declare(
        key=f"{prefix}.finalize",
        entity_types=entity_types,
        label="Customer service outcome",
        getter=getter,
        # `_finalize_request` assigns ONLY `status` - the resolved_at / resolved_by pair
        # belongs to the complaint finalize, not this one.
        columns=cols("finalize", ("status",)),
        runner=lambda db, p: service(db)._finalize_request(
            p[id_key],
            p["new_status"],
            note=p.get("note"),
            respond_user_id=p.get("respond_user_id"),
            crm_sender_user_id=p.get("crm_sender_user_id"),
        ),
        resolve_event=lambda _p: "resolved",
        tells_contact=True,
    )

    _declare(
        key=f"{prefix}.void",
        entity_types=entity_types,
        label="Void",
        getter=getter,
        columns=cols("void", ("status", "approval_status", "voided_by", "voided_at", "void_reason")),
        runner=lambda db, p: service(db).void_request(
            p[id_key],
            void_reason=p.get("void_reason"),
            actor_user_id=p.get("actor_user_id"),
            respond_user_id=p.get("respond_user_id"),
        ),
        resolve_event=lambda _p: "voided",
    )


_declare_approval_chain("pr", PR_TYPES, _get_request, _pr_service, "request_id")
# OCN-ORDER-CHANGE-NOTICE: the order change notice's Done also stores the CS comment.
_declare_approval_chain(
    "ocn",
    OCN_TYPES,
    _get_ocn,
    _ocn_service,
    "ocn_id",
    extra_columns={"finalize": ("cs_comment",)},
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
    # `update_inquiry_and_reply` setattr's EVERY submitted field (model_dump over the
    # whole StockInquiryUpdate) and recomputes the respond linkage columns - so the
    # snapshot must widen to whatever this particular payload touches, or an undo
    # restores the status while silently keeping the edited prices/remarks/contact.
    payload_columns=lambda p: list((p.get("inquiry_data") or {}).keys())
    + ["respond_inbox_url", "contact_id", "space_id"]
    # NPA-FROM-SI: the server stamps who / when beside the flag, so an undo restores all three.
    + (["npa_requested_by", "npa_requested_at"] if "npa_requested" in (p.get("inquiry_data") or {}) else []),
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
