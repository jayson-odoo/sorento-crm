"""The price-floor approval gate on a quotation document (S14-S16).

Price floors already existed and already flagged a line: ``project_quotation_service._apply_guardrails``
stores ``is_below_floor`` / ``floor_value_applied`` on every line from
``project_pricing_service.resolve_floor``. Nothing enforced them, so a quotation with every line
below floor issued exactly as freely as one that was never discounted. This module is the
enforcement, and it is the whole of it.

Four rules are worth stating here rather than leaving to a reader of the code:

1. **The ordinary quotation never touches the graph.** ``approval_status_id`` stays NULL until a
   below-floor line makes a manager necessary, so no status row is written, no rung is entered,
   and the Issue flow for the common case is byte-for-byte what it was. A document defaulted to
   `draft` on create would enrol every quotation in an approval lifecycle for the sake of the
   minority that discount past the floor. NULL therefore reads as "sitting at the graph's initial
   rung, and has never had to say so" - which is why ``move`` resolves the initial rung as the
   from-position when the column is empty, instead of demanding a first move to get onto a graph
   the user never asked to be on.

2. **The gate is at ISSUE, not at Sign.** The internal signature is readiness, not dispatch: a
   person may sign a quotation at any price. What they may not do is send it.

3. **Issuing spends the approval.** A manager approved THOSE prices, so ``mark_issued`` moves the
   document to `issued` and the next revision that dips below the floor has to be approved on its
   own merits. Leaving it on `approved` for good would be the gate quietly disabling itself after
   one use.

4. **Approve and reject are not generic status moves.** Both edges exist on the graph, and both
   are refused on the generic move route, because approving carries a permission and rejecting
   carries a required reason. A route that asked for neither would make both rules decorative.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    Project,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from app.models.status import Status
from app.services import status_service
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

ENTITY_TYPE = "quotation"

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_ISSUED = "issued"

APPROVE_PERMISSION = "projects.quotations.approve"

# The rungs a salesperson may move to themselves. Everything else on the graph belongs to an act
# with its own rules (a permission, a reason, an actual issue), so the generic move route refuses
# them even where the edge exists.
SELF_SERVE_KEYS = frozenset({STATUS_DRAFT, STATUS_PENDING})


# ------------------------------------------------------------------ the floor


def current_version_ids(db: Session, document: ProjectQuotationDocument) -> list[str]:
    """The version each scope would contribute if this document were issued right now.

    Same rule ``issue()`` itself uses (MAX(version_no) per scope), because the gate has to be
    asking about the rows that would actually go out. Asking about every version a scope ever
    had would block on a price somebody already corrected.
    """
    scope_ids = [
        row[0]
        for row in db.query(ProjectQuotation.id)
        .filter(ProjectQuotation.document_id == document.id)
        .all()
    ]
    if not scope_ids:
        return []
    latest = (
        db.query(
            ProjectQuotationVersion.quotation_id.label("quotation_id"),
            func.max(ProjectQuotationVersion.version_no).label("version_no"),
        )
        .filter(ProjectQuotationVersion.quotation_id.in_(scope_ids))
        .group_by(ProjectQuotationVersion.quotation_id)
        .subquery()
    )
    rows = (
        db.query(ProjectQuotationVersion.id)
        .join(
            latest,
            (ProjectQuotationVersion.quotation_id == latest.c.quotation_id)
            & (ProjectQuotationVersion.version_no == latest.c.version_no),
        )
        .all()
    )
    return [row[0] for row in rows]


def below_floor_line_count(db: Session, document: ProjectQuotationDocument) -> int:
    """How many lines this document would send out priced below their floor.

    Read from the STORED per-line flag, never re-resolved: the floor that applies is the one
    that applied when the line was priced (AC-E7). Re-resolving here would let a policy edited
    after the fact retroactively block a quotation nobody has changed.
    """
    version_ids = current_version_ids(db, document)
    if not version_ids:
        return 0
    return int(
        db.query(func.count(ProjectQuotationLine.id))
        .filter(
            ProjectQuotationLine.version_id.in_(version_ids),
            ProjectQuotationLine.is_below_floor.is_(True),
        )
        .scalar()
        or 0
    )


def requires_approval(db: Session, document: ProjectQuotationDocument) -> bool:
    return below_floor_line_count(db, document) > 0


# ------------------------------------------------------------------ the graph


def graph(db: Session) -> status_service.StatusGraph:
    """The one ``quotation`` graph. No scoped forks: a price floor is a company policy."""
    return status_service.resolve_graph(db, ENTITY_TYPE, None)


def status_of(db: Session, document: ProjectQuotationDocument) -> Optional[Status]:
    if not document.approval_status_id:
        return None
    return (
        db.query(Status).filter(Status.id == document.approval_status_id).first()
    )


def current_key(db: Session, document: ProjectQuotationDocument) -> Optional[str]:
    """The rung's machine key, or None while the document has never needed one."""
    status = status_of(db, document)
    return status.key if status is not None else None


def _from_status_id(db: Session, document: ProjectQuotationDocument) -> str:
    """Where a move starts from.

    A document with no position is sitting at the graph's initial rung without having had to
    say so, so that is what a move is checked against. The alternative - refusing every move
    until somebody "enters" the graph - would make asking for approval two presses, the first
    of which means nothing to anybody.
    """
    if document.approval_status_id:
        return document.approval_status_id
    return status_service.initial_status(db, ENTITY_TYPE, None).id


def _status_by_key(db: Session, key: str) -> Status:
    row = graph(db).by_key(key)
    if row is None:
        raise AppException(
            status_code=422,
            message=(
                f"The quotation approval graph has no '{key}' status. "
                "Restore it in Setup > Status Graphs."
            ),
            code="status_graph_missing",
        )
    return row


# ------------------------------------------------------------------- the gate


def assert_issuable(db: Session, document: ProjectQuotationDocument) -> None:
    """Refuse to issue a below-floor quotation that no manager has approved.

    Says how many lines rather than only that something is wrong, because the block on the
    screen has to be actionable: "two lines" tells the salesperson there is a second one to
    look at after they have fixed the obvious one.
    """
    below = below_floor_line_count(db, document)
    if not below:
        return
    if current_key(db, document) == STATUS_APPROVED:
        return
    raise AppException(
        status_code=422,
        message=(
            f"{'One line is' if below == 1 else f'{below} lines are'} priced below the "
            "floor, so this quotation needs a manager's approval before it can be sent "
            "to the customer."
        ),
        code="quotation_below_floor_pending_approval",
    )


def mark_issued(db: Session, document: ProjectQuotationDocument) -> None:
    """Spend the approval, if there was one. Called from ``issue()`` after the revision lands.

    Only moves a document that is actually standing on `approved`. A quotation that never needed
    a manager stays off the graph entirely (DoD item 1), and one sitting at `draft` or `rejected`
    with nothing below the floor is issuing on its own merits, so there is no approval to spend.
    """
    if not document.approval_status_id:
        return
    if current_key(db, document) != STATUS_APPROVED:
        return
    _set_status(db, document, _status_by_key(db, STATUS_ISSUED))


# ------------------------------------------------------------------ the moves


def _set_status(db: Session, document: ProjectQuotationDocument, status: Status) -> None:
    document.approval_status_id = status.id
    if status.key != STATUS_REJECTED:
        # The reason explains a state the document is no longer in. Leaving it would have the
        # screen quoting a rejection that has already been answered.
        document.approval_rejected_reason = None
    db.flush()


def _project_of(db: Session, document: ProjectQuotationDocument) -> Optional[Project]:
    return db.query(Project).filter(Project.id == document.project_id).first()


def _actor_name(db: Session, actor_user_id: Optional[str]) -> str:
    from app.models.user import User

    if not actor_user_id:
        return "Somebody"
    user = db.query(User).filter(User.id == actor_user_id).first()
    return (user.name if user and user.name else None) or "Somebody"


def _record(
    db: Session,
    document: ProjectQuotationDocument,
    *,
    template: str,
    body_text: str,
    actor_user_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """One activity row per decision, on the PROJECT's feed.

    A discount below the floor is exactly the decision somebody asks about six months later, so
    who asked, who decided and why it was sent back all have to be recoverable from the project's
    own history rather than from a manager's memory.

    Deliberately NOT added to ``project_activity_service.MEANINGFUL_TEMPLATES``: that whitelist
    drives the staleness clock, and its own rule is that a new event type stays silent until
    somebody decides it counts as work on the pursuit.
    """
    project = _project_of(db, document)
    if project is None:
        return
    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template=template,
        payload={
            "document_id": str(document.id),
            "document_no": document.document_no,
            **(payload or {}),
        },
        actor_id=actor_user_id,
        body_text=body_text,
    )


def move(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    to_status_id: str,
    actor_user_id: str,
) -> ProjectQuotationDocument:
    """The salesperson's own moves: ask for approval, or take a rejected quotation back to draft.

    Taking a rejected quotation back to draft is just "edit and re-price", so it carries no grant
    beyond the edit rights needed to change the quotation at all. The route's own
    ``assert_can_edit_project`` is that check; adding a second one here would be a different rule
    wearing the same name.
    """
    target = graph(db).by_id(to_status_id)
    if target is None:
        raise AppException(
            status_code=422,
            message="That status does not belong to the quotation approval graph.",
            code="status_not_in_graph",
        )
    if target.key not in SELF_SERVE_KEYS:
        raise AppException(
            status_code=422,
            message=(
                f"'{target.label}' is not a move you can make here. Approving and rejecting "
                "are the manager's own actions, and 'Issued' is stamped by issuing the "
                "quotation."
            ),
            code="quotation_status_not_self_serve",
        )

    status_service.assert_transition_allowed(
        db, ENTITY_TYPE, _from_status_id(db, document), to_status_id, scope_id=None
    )
    _set_status(db, document, target)

    if target.key == STATUS_PENDING:
        below = below_floor_line_count(db, document)
        _record(
            db,
            document,
            template="quotation_approval_requested",
            body_text=(
                f"{_actor_name(db, actor_user_id)} asked for approval on quotation "
                f"{document.document_no} ({below} line{'' if below == 1 else 's'} below floor)."
            ),
            actor_user_id=actor_user_id,
            payload={"below_floor_line_count": below},
        )
    return document


def _assert_can_decide(permissions: Iterable[str]) -> None:
    if APPROVE_PERMISSION not in set(permissions or ()):
        raise AppException(
            status_code=403,
            message=(
                "Only a sales manager can approve or reject below-floor pricing on a "
                "quotation."
            ),
            code="quotation_approval_forbidden",
        )


def approve(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    permissions: Iterable[str],
) -> ProjectQuotationDocument:
    """The manager accepts the below-floor pricing. The next Issue press then proceeds."""
    _assert_can_decide(permissions)
    target = _status_by_key(db, STATUS_APPROVED)
    status_service.assert_transition_allowed(
        db, ENTITY_TYPE, _from_status_id(db, document), target.id, scope_id=None
    )
    _set_status(db, document, target)
    _record(
        db,
        document,
        template="quotation_approval_granted",
        body_text=(
            f"{_actor_name(db, actor_user_id)} approved the below-floor pricing on "
            f"quotation {document.document_no}."
        ),
        actor_user_id=actor_user_id,
    )
    return document


def reject(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    reason: Optional[str],
    permissions: Iterable[str],
) -> ProjectQuotationDocument:
    """The manager sends it back, and the reason is required.

    Checked BEFORE the permission would let anything move, and stored on the document rather
    than only in the feed: "rejected" with no reason leaves the salesperson guessing which line
    to move, which is the conversation this gate exists to make explicit.
    """
    _assert_can_decide(permissions)
    cleaned = " ".join((reason or "").split())
    if not cleaned:
        raise AppException(
            status_code=422,
            message="Say why you are sending this back, so the salesperson knows what to change.",
            code="quotation_reject_reason_required",
        )

    target = _status_by_key(db, STATUS_REJECTED)
    status_service.assert_transition_allowed(
        db, ENTITY_TYPE, _from_status_id(db, document), target.id, scope_id=None
    )
    _set_status(db, document, target)
    document.approval_rejected_reason = cleaned
    db.flush()
    _record(
        db,
        document,
        template="quotation_approval_rejected",
        body_text=(
            f"{_actor_name(db, actor_user_id)} sent quotation {document.document_no} "
            f"back: {cleaned}"
        ),
        actor_user_id=actor_user_id,
        payload={"reason": cleaned},
    )
    return document


# ------------------------------------------------------------------ serialize


def serialize_approval(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """The approval block of the document payload.

    Its own function so ``serialize_document`` cannot drift from it, and so every one of these
    keys is present on EVERY document - absent would be as bad as wrong, because the screen
    reads them to decide whether to render the gate at all.
    """
    status = status_of(db, document)
    below = below_floor_line_count(db, document)
    return {
        "approval_status_id": str(status.id) if status is not None else None,
        "approval_status_key": status.key if status is not None else None,
        "approval_status_label": status.label if status is not None else None,
        "approval_rejected_reason": document.approval_rejected_reason,
        "requires_approval": below > 0,
        "below_floor_line_count": below,
    }
