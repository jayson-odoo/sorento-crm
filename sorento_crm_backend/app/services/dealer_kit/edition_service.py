"""The Edition's transitions (S2.5.2).

Every move goes through ``status_service.assert_transition_allowed`` rather
than an ``if``. The graph seeded by migration 318 is the authority on what is
legal, so adding a state later is a seeding change and not a hunt through this
file for the branch that also needs it.

**``done`` is the only transition HERE that publishes** (AC-L7). Approving does
not move the ``published`` label; it records that a human read the catalogue.
Whoever publishes then decides WHEN, and that is a separate permission because
moving the label is what a reader actually sees.

That used to be written as "the only thing that publishes", full stop, and it
was not true: ``PUT /pages/{id}/labels/published`` moves the label at any
version on ``page.publish`` alone, and the page editor wires its header Publish
button straight to it. The workflow was advisory until
``page_service._assert_no_open_edition_bypass`` closed it. Read that function
alongside this file - between them they are the guarantee, and neither is it
on its own.

**Both version ids are recorded, and they are not the same fact.**
``approved_version_id`` is what the Approver read; ``done_version_id`` is what
went live. On any row that reaches ``done`` they are now necessarily EQUAL,
because publish refuses unless the latest version is the approved one. The
columns stay separate because the deferred price-drift work (AC-L4 to AC-L6)
relaxes exactly that refusal, at which point they diverge again - see
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

# The states that occupy a page's one open slot. Same set as the partial unique
# index `uq_dealer_kit_edition_one_open_per_page` and migration 318's
# `_OPEN_KEYS`, and named rather than derived as "not done" so a state added
# later has to be classified on purpose.
OPEN_STATUS_KEYS = (DRAFT, PENDING_APPROVAL, APPROVED, REJECTED)


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


def _void_approval(edition: Edition) -> None:
    """Forget an approval that no longer holds.

    All THREE fields, always. An `approved_by` left on a row that has gone back
    in the queue reads as approved to every screen that shows it, and an
    `approved_version_id` left behind is what `publish` compares against - so a
    stale one is not cosmetic, it decides whether a publish is allowed.
    """
    edition.approved_by = None
    edition.approved_at = None
    edition.approved_version_id = None


def submit(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Designer: this is ready for somebody to look at.

    Refused when the catalogue has never been saved, and refused HERE rather
    than at publish. A brand new page has no version, so without this an
    Edition could be sent, approved, and only then rejected by the publish
    guard - by which point an Approver had already spent their attention on it
    and ``approved_version_id`` had been stamped NULL, claiming somebody read a
    document that did not exist. The person who can fix it is the Designer, so
    the Designer is who the refusal has to reach.
    """
    edition = get_edition(db, edition_id)
    if _latest_version(db, edition.page_id) is None:
        raise AppException(
            status_code=422,
            message=(
                "This catalogue has no saved version to send for approval. "
                "Open the page and save it first."
            ),
        )

    def _stamp() -> None:
        edition.submitted_by = user_id
        edition.submitted_at = datetime.utcnow()
        # Cleared on re-submission: a reason from the previous round shown
        # beside a fresh submission reads as a fresh rejection.
        edition.rejection_reason = None
        # This function serves TWO edges - draft -> pending_approval and
        # approved -> pending_approval - and on the second one the approval it
        # is leaving behind is void. Left stamped, the detail page renders
        # "Approved: <date>" beside a "Pending approval" pill.
        _void_approval(edition)

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
        _void_approval(edition)

    return _move(db, edition, REJECTED, apply=_stamp)


def reopen(db: Session, edition_id: str, *, user_id: Optional[str] = None) -> Edition:
    """Designer picking rejected work back up.

    The reason is deliberately NOT cleared here - it is cleared on the next
    submission. A Designer editing a rejected Edition should still be able to
    see what they were told.
    """
    return _move(db, get_edition(db, edition_id), DRAFT)


def send_back_on_edit(db: Session, page_id: str) -> Optional[Edition]:
    """A save invalidates an approval. Move the Edition back to the Approver.

    This is what performs the ``approved -> pending_approval`` edge that
    migration 318 seeded and described. For a while nothing did, and an Approver
    could sign off version 3 while version 4 went live.

    Blunt on purpose. AC-L4/L5 wanted price-only edits to keep the approval
    alive; that is deferred because the document stores no prices and an Edition
    cannot detect a price change by diffing its own versions. Sending back too
    often is a nuisance; not sending back ships a document nobody read.

    Returns the Edition it moved, or None when there was nothing to move - AND
    None when company scope hid it. Every caller today is request-scoped and the
    page id already partitions the query, so the injected predicate is
    redundant. Under UNSET scope (a worker, a backfill) it is `false()`, this
    returns None, and `save_version`'s best-effort wrapper logs NOTHING, because
    nothing raised. If this ever gains a background caller, read it under
    `company_scope(db, None)` the way `bootstrap._count_editions` does.
    """
    edition = (
        db.query(Edition)
        .filter(Edition.page_id == page_id, Edition.status_key == APPROVED)
        .first()
    )
    if edition is None:
        return None

    return _move(db, edition, PENDING_APPROVAL, apply=lambda: _void_approval(edition))


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
    if latest.id != edition.approved_version_id:
        # The invariant, and it holds even if send_back_on_edit never ran - it
        # is best-effort by design, and this is not. Publishing a version other
        # than the approved one is the exact failure the workflow exists to
        # stop: a document going live that nobody signed off.
        raise AppException(
            status_code=422,
            message=(
                "This catalogue has changed since it was approved. "
                "Send it for approval again before publishing."
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
