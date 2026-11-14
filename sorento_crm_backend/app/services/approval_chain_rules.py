"""The purchase request approval chain's rules, shared by every form that runs that chain.

OCN-ORDER-CHANGE-NOTICE (plan "Shared once, never copied"): these were `PurchaseRequestService`
methods and class constants. They read and write only the chain's own columns (`status`,
`approval_status`, `approved_at`, `approved_by`, `approval_comments`, `rejected_by_id`,
`approval_signature_ref`, `requested_approval_by_user_id`, `voided_by` / `voided_at` /
`void_reason`), so they take the row and nothing else. The purchase request / sponsorship form
service calls them, and so does the order change notice service; neither keeps a copy.

What stays with each form: who may act, its own status checks around these, its notifications
and when it emits the SLA event. `noun` names the record in a refusal ("request" for the
purchase request, whose sentences are pinned by tests/test_pr_shared_rules_regression.py), and
`invalid` is the form's own refusal for a missing reason (the purchase request answers 400,
the order change notice 422).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException, handle_conflict, handle_validation_error

#: Void is refused once the form is closed. A rejected form sets BOTH `status` and
#: `approval_status` to rejected, so either signal blocks a void (`assert_voidable`).
VOID_BLOCKED_STATUSES: frozenset[str] = frozenset({"voided", "rejected", "closed", "processed_by_cs"})

#: Customer service finalizes only an approved form (the CS stage starts on `approved`).
FINALIZE_FROM_STATUSES: tuple[str, ...] = ("approved",)

#: The approval decision's two outcomes.
DECISIONS: tuple[str, ...] = ("approved", "rejected")

Invalid = Callable[[str], AppException]


def _lower(value) -> str:
    return (value or "").strip().lower()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def refuse_if_voided(row, doing: str, *, noun: str = "request") -> None:
    """Void is terminal (PLAN-form-void D3/D6): no approval step may touch a voided form,
    whichever door it comes through."""
    if _lower(getattr(row, "status", None)) == "voided":
        raise handle_conflict(f"This {noun} has been voided and can no longer be {doing}.")


def assert_voidable(row, *, noun: str = "request") -> None:
    """Void only from an open state: never once closed, rejected or already voided."""
    current = _lower(getattr(row, "status", None))
    approval = _lower(getattr(row, "approval_status", None))
    if current in VOID_BLOCKED_STATUSES or approval == "rejected":
        raise handle_conflict(
            f"This {noun} cannot be voided from its current state ({current or 'unknown'})."
        )


def void_reason(reason: Optional[str], *, invalid: Invalid = handle_validation_error) -> str:
    """The reason a void stores, or the refusal: at least 3 characters."""
    text = (reason or "").strip()
    if len(text) < 3:
        raise invalid("A void reason of at least 3 characters is required.")
    return text


def apply_void(row, *, reason: str, actor_user_id: Optional[str], noun: str = "request") -> None:
    """The void's writes: the form closes, and an open approval closes with it so no approval
    queue still lists it as waiting on a decision."""
    assert_voidable(row, noun=noun)
    approval = _lower(getattr(row, "approval_status", None))
    row.status = "voided"
    if approval == "pending":
        row.approval_status = "voided"
    row.voided_by = actor_user_id
    row.voided_at = _now()
    row.void_reason = reason


def apply_send_for_approval(
    row,
    *,
    requested_by_user_id: Optional[str],
    rejected_message: str,
    noun: str = "request",
) -> bool:
    """Send for approval's writes. Refused once the approval was rejected (the raiser amends
    and resubmits instead). Returns True when it was ALREADY pending: a redundant call (a
    double click, a retry) must not re-emit `send_for_approval`, which would start a second
    approval stage."""
    refuse_if_voided(row, "sent for approval", noun=noun)
    current = _lower(getattr(row, "approval_status", None))
    if current == "rejected":
        raise handle_conflict(rejected_message)
    already_pending = current == "pending"
    row.approval_status = "pending"
    row.approved_at = None
    row.approved_by = None
    if hasattr(row, "approval_signature_ref"):
        row.approval_signature_ref = None
    row.approval_comments = None
    if requested_by_user_id is not None:
        row.requested_approval_by_user_id = requested_by_user_id
    return already_pending


def existing_user_id(db: Session, user_id: Optional[str]) -> Optional[str]:
    """`user_id` when it names a real users row, else None: a non-user actor id must never
    abort a decision on the `rejected_by_id` foreign key."""
    from app.models.user import User

    uid = (user_id or "").strip() if user_id else None
    if uid and db.query(User.id).filter(User.id == uid).first():
        return uid
    return None


def apply_reject_submitted(
    db: Session,
    row,
    *,
    reason: Optional[str],
    actor_user_id: Optional[str],
    actor_display_name: Optional[str],
    noun: str = "request",
    invalid: Invalid = handle_validation_error,
) -> None:
    """Send back (reject before approval)'s writes. Only before the form was sent for
    approval; the reason is required."""
    text = (reason or "").strip()
    if not text:
        raise invalid("Rejection reason is required.")
    refuse_if_voided(row, "rejected", noun=noun)
    current = _lower(getattr(row, "approval_status", None))
    if current and current not in ("", "draft"):
        raise handle_conflict(
            f"Cannot reject submitted: approval_status is already '{current}'. "
            "Reject is only available before sending for approval."
        )
    row.approval_status = "rejected"
    row.status = "rejected"
    row.approval_comments = text
    row.approved_at = _now()
    # A display name, never a raw id: the "Rejected by" field renders a person.
    row.approved_by = actor_display_name
    row.rejected_by_id = existing_user_id(db, actor_user_id)
    if hasattr(row, "approval_signature_ref"):
        row.approval_signature_ref = None
    if actor_user_id is not None:
        row.requested_approval_by_user_id = actor_user_id


def assert_decidable(row, *, noun: str = "request") -> None:
    """The in-system decision's premise: not voided, and still awaiting a decision
    (approval_status == 'pending')."""
    refuse_if_voided(row, "approved or rejected", noun=noun)
    approval = _lower(getattr(row, "approval_status", None))
    if approval in DECISIONS:
        raise handle_conflict(f"This {noun} has already been {approval}.")
    if approval != "pending":
        raise handle_conflict(f"This {noun} is not pending approval. Send it for approval first.")


def decision_comments(
    action: str, approval_comments: Optional[str], *, invalid: Invalid = handle_validation_error
) -> Optional[str]:
    """The comments a decision stores, or the refusal: a rejection needs a reason."""
    if action not in DECISIONS:
        raise handle_conflict("action must be 'approved' or 'rejected'.")
    if action == "rejected":
        rejection_notes = (approval_comments or "").strip()
        if not rejection_notes:
            raise invalid("Rejection reason is required.")
        return rejection_notes
    return approval_comments


def apply_decision(
    row,
    action: str,
    *,
    approved_by: Optional[str],
    approval_comments: Optional[str],
    rejected_by_id: Optional[str],
    approval_signature_ref: Optional[str] = None,
    noun: str = "request",
) -> None:
    """The approval decision's writes. Both statuses move, so every view reflects it."""
    refuse_if_voided(row, "approved or rejected", noun=noun)
    row.approval_status = action
    row.status = action
    row.approved_at = datetime.now(timezone.utc)
    row.approved_by = approved_by
    if action == "rejected":
        row.rejected_by_id = rejected_by_id
    if hasattr(row, "approval_signature_ref"):
        row.approval_signature_ref = approval_signature_ref
    row.approval_comments = approval_comments


def can_finalize(row) -> bool:
    """Customer service may finalize it (it is approved)."""
    return _lower(getattr(row, "status", None)) in FINALIZE_FROM_STATUSES
