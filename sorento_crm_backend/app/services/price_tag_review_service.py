"""Pinned change requests on a price tag design (r9 S2/D4-D6).

The salesperson stopped describing a change and started pointing at it. Three
things here are easy for a route to get wrong quietly, so they live in one
service instead of in whichever endpoint needed them first:

* **The anchor is the TAG, not the page.** ``x/y/w/h`` are fractions of the
  tag's own box, so re-arranging the sheet leaves every pin on the thing it was
  put on. The service refuses anything outside 0..1 rather than storing a
  coordinate that will draw off the tag.
* **``round`` is stored, not derived.** It is the number of ``Marked proof
  ready`` snapshots the design had when the round was SENT. Recomputing it at
  read time would renumber round 1 the moment marketing sends a third proof.
* **Done belongs to marketing.** The salesperson may read their own comments
  and never close one; the route enforces the permission, and this module
  records who closed it and when.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import PageVersion
from app.models.price_tag import PriceTagRequest, PriceTagReviewComment
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

#: What `_snapshot_draft` writes when marketing sends a proof. A round counts
#: these, so the string has to be the same one the transition writes.
PROOF_READY_COMMIT_MESSAGE = "Marked proof ready"


def _fraction(value, field: str) -> Optional[float]:
    """A fraction of the tag box, or a 422 naming the field."""
    if value is None:
        return None
    number = float(value)
    if number < 0 or number > 1:
        raise AppException(
            status_code=422,
            message=f"{field} must be a fraction of the tag between 0 and 1.",
            code="INVALID_PIN",
        )
    return number


def current_round(db: Session, request: PriceTagRequest) -> int:
    """How many proofs this design has been through, at least one.

    A request whose page carries no ``Marked proof ready`` snapshot is still on
    its first round - the design was sent by a path that predates the snapshot
    (or by the seed of a test), and numbering it 0 would read as "before the
    first round" rather than "during it".
    """
    if not request.page_id:
        return 1
    proofs = (
        db.query(PageVersion)
        .filter(
            PageVersion.page_id == request.page_id,
            PageVersion.commit_message == PROOF_READY_COMMIT_MESSAGE,
        )
        .count()
    )
    return max(1, proofs)


def create_comments(
    db: Session,
    request: PriceTagRequest,
    *,
    comments: Iterable[dict],
    note: Optional[str] = None,
    author_contact_id: Optional[str] = None,
    author_user_id: Optional[str] = None,
) -> list[PriceTagReviewComment]:
    """One round: every pin, plus the general note if there is one.

    Written in one call because that is what a round IS - the pins are placed
    locally and nothing reaches the server until Send, so a salesperson can put
    five pins down, delete two, and the request changes state exactly once.
    """
    pins = list(comments or [])
    note = (note or "").strip()
    if not pins and not note:
        raise AppException(
            status_code=422,
            message="Say what needs to change before sending.",
            code="EMPTY_CHANGE_REQUEST",
        )

    round_no = current_round(db, request)
    created: list[PriceTagReviewComment] = []

    for pin in pins:
        body = (pin.get("body") or "").strip()
        if not body:
            raise AppException(
                status_code=422,
                message="A pin with no comment says nothing.",
                code="EMPTY_CHANGE_REQUEST",
            )
        created.append(
            PriceTagReviewComment(
                id=str(uuid.uuid4()),
                request_id=request.id,
                line_id=pin.get("line_id"),
                round=round_no,
                x=_fraction(pin.get("x"), "x"),
                y=_fraction(pin.get("y"), "y"),
                w=_fraction(pin.get("w"), "w"),
                h=_fraction(pin.get("h"), "h"),
                body=body,
                author_contact_id=author_contact_id,
                author_user_id=author_user_id,
                company_id=request.company_id,
            )
        )

    if note:
        created.append(
            PriceTagReviewComment(
                id=str(uuid.uuid4()),
                request_id=request.id,
                line_id=None,
                round=round_no,
                body=note,
                author_contact_id=author_contact_id,
                author_user_id=author_user_id,
                company_id=request.company_id,
            )
        )

    for row in created:
        db.add(row)
    db.flush()
    return created


def list_comments(db: Session, request_id: str) -> list[PriceTagReviewComment]:
    """Every round, oldest first: a second round is read against the first."""
    return (
        db.query(PriceTagReviewComment)
        .filter(PriceTagReviewComment.request_id == request_id)
        .order_by(PriceTagReviewComment.created_at, PriceTagReviewComment.id)
        .all()
    )


def get_comment(
    db: Session, request_id: str, comment_id: str
) -> PriceTagReviewComment:
    row = (
        db.query(PriceTagReviewComment)
        .filter(
            PriceTagReviewComment.id == comment_id,
            PriceTagReviewComment.request_id == request_id,
        )
        .first()
    )
    if not row:
        raise AppException(
            status_code=404,
            message="Change request not found.",
            code="NOT_FOUND",
        )
    return row


def set_resolved(
    db: Session,
    request_id: str,
    comment_id: str,
    *,
    resolved: bool,
    user_id: Optional[str],
) -> PriceTagReviewComment:
    """Tick a change request Done, or put it back."""
    row = get_comment(db, request_id, comment_id)
    row.resolved_at = datetime.utcnow() if resolved else None
    row.resolved_by_id = user_id if resolved else None
    db.flush()
    db.commit()
    db.refresh(row)
    return row


def open_count(db: Session, request_id: str) -> int:
    """Change requests nobody has ticked off. What the CTA's count reads."""
    return (
        db.query(PriceTagReviewComment)
        .filter(
            PriceTagReviewComment.request_id == request_id,
            PriceTagReviewComment.resolved_at.is_(None),
        )
        .count()
    )


def to_responses(db: Session, rows: Iterable[PriceTagReviewComment]) -> list[dict]:
    """Rows as both surfaces read them, with the two names resolved.

    Names, never ids: a pin says who asked for the change and who closed it,
    and no id reaches a screen. Resolved in one query per kind rather than per
    row, because a busy second round is a dozen comments by the same person.
    """
    from app.models.access import RespondContact
    from app.models.user import User

    rows = list(rows)
    contact_ids = {row.author_contact_id for row in rows if row.author_contact_id}
    user_ids = {row.author_user_id for row in rows if row.author_user_id}
    user_ids |= {row.resolved_by_id for row in rows if row.resolved_by_id}

    contact_names: dict[str, str] = {}
    if contact_ids:
        contact_names = {
            contact.id: (contact.name or contact.phone_number or "")
            for contact in db.query(RespondContact)
            .filter(RespondContact.id.in_(contact_ids))
            .all()
        }
    user_names: dict[str, str] = {}
    if user_ids:
        user_names = {
            user.id: (user.name or user.email or "")
            for user in db.query(User).filter(User.id.in_(user_ids)).all()
        }

    return [
        {
            "id": row.id,
            "request_id": row.request_id,
            "line_id": row.line_id,
            "round": row.round,
            "x": None if row.x is None else float(row.x),
            "y": None if row.y is None else float(row.y),
            "w": None if row.w is None else float(row.w),
            "h": None if row.h is None else float(row.h),
            "body": row.body,
            "author_name": (
                contact_names.get(row.author_contact_id)
                if row.author_contact_id
                else user_names.get(row.author_user_id)
            ),
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
            "resolved_by_name": user_names.get(row.resolved_by_id)
            if row.resolved_by_id
            else None,
        }
        for row in rows
    ]
