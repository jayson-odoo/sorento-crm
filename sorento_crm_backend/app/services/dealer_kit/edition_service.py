"""The Edition's transitions (S2.5.2).

Every move goes through ``status_service.assert_transition_allowed`` rather
than an ``if``. The graph seeded by migration 318 is the authority on what is
legal, so adding a state later is a seeding change and not a hunt through this
file for the branch that also needs it.

**``done`` is the only thing that publishes** (AC-L7). Approving does not move
the ``published`` label; it records that a human read the catalogue. Whoever
publishes then decides WHEN, and that is a separate permission because moving
the label is what a reader actually sees.

**Both version ids are recorded, and they are not the same fact.**
``approved_version_id`` is what the Approver read; ``done_version_id`` is what
went live. They are usually equal. Storing only one would leave the deferred
price-drift work (AC-L4 to AC-L6) with nothing to compare - see
``PLAN-edition-approval.md``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dealer_kit import Edition, PageVersion
from app.models.status import Status
from app.modules.dealer_kit.bootstrap import EDITION_ENTITY
from app.services import status_service
from app.services.dealer_kit import page_service
from app.services.error_handler import AppException

DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
REJECTED = "rejected"
DONE = "done"


def _status_by_key(db: Session, key: str) -> Status:
    """The status row for a key in the DEFAULT graph.

    A missing row is a 500-shaped problem, not a user error: the graph is
    seeded by migration and its absence means the migration did not run. Said
    plainly rather than surfacing as an AttributeError three frames down.
    """
    graph = status_service.resolve_graph(db, EDITION_ENTITY, None)
    status = graph.by_key(key)
    if status is None:
        raise AppException(
            status_code=500,
            message=(
                f"The catalogue Edition status '{key}' is missing. "
                "Its status graph has not been seeded."
            ),
        )
    return status


def get_edition(db: Session, edition_id: str) -> Edition:
    """The Edition, or a 404.

    Company scope is applied by the ORM filter, so another company's Edition is
    a 404 here and never a 403 - a 403 confirms the id exists.
    """
    edition = db.query(Edition).filter(Edition.id == edition_id).first()
    if edition is None:
        raise AppException(status_code=404, message="Edition not found")
    return edition


def list_editions(db: Session, *, page_id: Optional[str] = None) -> list[Edition]:
    query = db.query(Edition)
    if page_id:
        query = query.filter(Edition.page_id == page_id)
    return query.order_by(Edition.created_at.desc()).all()


def create_edition(
    db: Session,
    *,
    page_id: str,
    name: str,
    previous_edition_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Edition:
    """Start a revision cycle over a page, at ``draft``.

    The one-open-per-page rule is a partial unique index, not a check here: a
    service-level "is one already open" read races itself between two requests
    and the loser writes the second open Edition anyway. So the write is
    attempted and the database's answer is translated - which also means the
    guarantee holds for anything else that ever inserts a row.
    """
    page_service.get_page(db, page_id)  # 404s if it is not this company's page

    initial = _status_by_key(db, DRAFT)
    edition = Edition(
        page_id=page_id,
        name=name,
        status_id=initial.id,
        status_key=initial.key,
        previous_edition_id=previous_edition_id,
        created_by=user_id,
    )
    db.add(edition)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppException(
            status_code=409,
            message=(
                "This catalogue already has an Edition in progress. "
                "Finish or reject it before starting another."
            ),
        )
    db.refresh(edition)
    return edition


def _move(
    db: Session,
    edition: Edition,
    to_key: str,
    *,
    apply: Optional[callable] = None,
) -> Edition:
    """Move an Edition to ``to_key``, or refuse because the graph says so.

    ``apply`` stamps whatever else the transition records, and runs only AFTER
    the move is known to be legal - so a rejected transition cannot leave an
    ``approved_by`` behind on a record that never moved.
    """
    target = _status_by_key(db, to_key)
    status_service.assert_transition_allowed(
        db,
        EDITION_ENTITY,
        from_status_id=edition.status_id,
        to_status_id=target.id,
    )

    edition.status_id = target.id
    # Carried in lockstep. The partial unique index reads the KEY, so a move
    # that updated only the id would leave a done Edition still occupying its
    # page's one open slot.
    edition.status_key = target.key
    if apply is not None:
        apply()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppException(
            status_code=409,
            message=(
                "This catalogue already has an Edition in progress. "
                "Finish or reject it before reopening this one."
            ),
        )
    db.refresh(edition)
    return edition


def submit(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Designer: this is ready for somebody to look at."""
    edition = get_edition(db, edition_id)

    def _stamp() -> None:
        edition.submitted_by = user_id
        edition.submitted_at = datetime.utcnow()
        # Cleared on re-submission: a reason from the previous round shown
        # beside a fresh submission reads as a fresh rejection.
        edition.rejection_reason = None

    return _move(db, edition, PENDING_APPROVAL, apply=_stamp)


def approve(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Approver: I have read this.

    Records WHICH version was read. The Approver is signing off a document, not
    a page id, and the page's newest version is what the review screen showed
    them - so that is what is stamped, and a later edit is a different document
    that has to come back round.
    """
    edition = get_edition(db, edition_id)
    latest = _latest_version(db, edition.page_id)

    def _stamp() -> None:
        edition.approved_by = user_id
        edition.approved_at = datetime.utcnow()
        edition.approved_version_id = latest.id if latest else None
        edition.rejection_reason = None

    return _move(db, edition, APPROVED, apply=_stamp)


def reject(
    db: Session, edition_id: str, *, reason: str, user_id: Optional[str] = None
) -> Edition:
    """Approver: no, and here is why.

    The reason is required by the route's schema and re-checked here. A
    rejection with no reason is a rejection the Designer cannot act on, and
    this is the last place that can refuse one.
    """
    reason = (reason or "").strip()
    if not reason:
        raise AppException(
            status_code=422,
            message="Say why it is being rejected. The Designer sees this.",
        )

    edition = get_edition(db, edition_id)

    def _stamp() -> None:
        edition.rejection_reason = reason
        edition.approved_by = None
        edition.approved_at = None

    return _move(db, edition, REJECTED, apply=_stamp)


def reopen(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Designer picking rejected work back up.

    The reason is deliberately NOT cleared here - it is cleared on the next
    submission. A Designer editing a rejected Edition should still be able to
    see what they were told.
    """
    return _move(db, get_edition(db, edition_id), DRAFT)


def publish(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Move the published label, and finish the Edition. AC-L7.

    The ONLY transition that publishes anything. The label move happens before
    the status move commits, so an Edition can never read ``done`` while the
    label still points somewhere else - the failure that would have a catalogue
    marked live that no reader can see.
    """
    edition = get_edition(db, edition_id)
    latest = _latest_version(db, edition.page_id)
    if latest is None:
        raise AppException(
            status_code=422,
            message=(
                "This catalogue has no saved version to publish. "
                "Save the page first."
            ),
        )

    def _stamp() -> None:
        edition.done_version_id = latest.id
        page_service.move_label(
            db,
            edition.page_id,
            page_service.PUBLISHED,
            version_id=latest.id,
            user_id=user_id,
        )

    return _move(db, edition, DONE, apply=_stamp)


def _latest_version(db: Session, page_id: str) -> Optional[PageVersion]:
    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page_id)
        .order_by(PageVersion.version.desc())
        .first()
    )
