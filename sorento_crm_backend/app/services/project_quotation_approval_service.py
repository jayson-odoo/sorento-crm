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
from decimal import Decimal
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
from app.services import status_service, submission_status
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

ENTITY_TYPE = "quotation"

# The project rung a discount request moves a project to (B2). Prod made it in the admin editor.
FINAL_NEGOTIATION_KEY = "final_negotiation"

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending_approval"
# A rejected quotation asked again (RESUBMITTED-STATUS): decided exactly like pending.
STATUS_RESUBMITTED = submission_status.RESUBMITTED
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_ISSUED = "issued"

APPROVE_PERMISSION = "projects.quotations.approve"
# What opening a quotation of another salesperson's project needs (quotation_documents.READ).
VIEW_PERMISSION = "projects.projects.view"

# The rungs a salesperson may move to themselves. Everything else on the graph belongs to an act
# with its own rules (a permission, a reason, an actual issue), so the generic move route refuses
# them even where the edge exists.
# `draft` is not here: a rejected quotation resubmits straight to pending (C1, C2), and revise has
# its own act.
SELF_SERVE_KEYS = frozenset({STATUS_PENDING})

# The rungs a manager decides from.
AWAITING_KEYS = frozenset(submission_status.awaiting_review_statuses(STATUS_PENDING))

# While the document stands on one of these rungs, nobody edits it (D1, D2). Revise is the way out.
LOCKED_KEYS = frozenset({*AWAITING_KEYS, STATUS_APPROVED})


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
            ProjectQuotationLine.is_section.is_(False),
        )
        .scalar()
        or 0
    )


def below_proposal_line_count(db: Session, document: ProjectQuotationDocument) -> int:
    """PS-PROPOSAL-QUOTATION rule 5: how many lines of a QUOTATION are priced below the same
    product's price on the proposal revision it was made from (a further discount).

    Always 0 for a proposal. The baseline is the source ISSUE's frozen lines, which nobody can
    edit, so a price lowered on the quotation's own first version still counts. A product that
    was not on the proposal has no baseline and is left to the minimum-price rule.
    """
    if getattr(document, "kind", None) != "quotation" or not document.source_issue_id:
        return 0
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_document_service as documents

    source = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == document.source_issue_id)
        .first()
    )
    if source is None:
        return 0
    baseline = documents.issue_price_map(db, source)
    version_ids = current_version_ids(db, document)
    if not baseline or not version_ids:
        return 0
    count = 0
    for line in (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id.in_(version_ids))
        .all()
    ):
        key = documents.line_key(line)
        if line.is_rate_only or key not in baseline:
            continue
        if Decimal(line.unit_price or 0) < baseline[key]:
            count += 1
    return count


def _flagged_line_count(db: Session, document: ProjectQuotationDocument, flag) -> int:
    """How many current lines carry ``flag``, read from the STORED flag (AC-E7)."""
    version_ids = current_version_ids(db, document)
    if not version_ids:
        return 0
    return int(
        db.query(func.count(ProjectQuotationLine.id))
        .filter(
            ProjectQuotationLine.version_id.in_(version_ids),
            flag.is_(True),
            # Heading rows are never flagged; filtered all the same (PROPOSAL-FORM-COLLAPSE).
            ProjectQuotationLine.is_section.is_(False),
        )
        .scalar()
        or 0
    )


def discounted_line_count(db: Session, document: ProjectQuotationDocument) -> int:
    """Lines priced below their default price (PS-QUOTE-RULES R1): any discount."""
    return _flagged_line_count(db, document, ProjectQuotationLine.is_discounted)


def off_series_line_count(db: Session, document: ProjectQuotationDocument) -> int:
    """Lines outside the scope's series (B1)."""
    return _flagged_line_count(db, document, ProjectQuotationLine.is_non_standard)


def counts(db: Session, document: ProjectQuotationDocument) -> Dict[str, int]:
    """Every reason, together, for messages and the payload (one query for the three line flags;
    the below-proposal count compares against the source proposal's frozen lines)."""
    from sqlalchemy import Integer, cast

    version_ids = current_version_ids(db, document)
    if not version_ids:
        return {"discounted": 0, "below_floor": 0, "off_series": 0, "below_proposal": 0}
    row = (
        db.query(
            func.coalesce(func.sum(cast(ProjectQuotationLine.is_discounted, Integer)), 0),
            func.coalesce(func.sum(cast(ProjectQuotationLine.is_below_floor, Integer)), 0),
            func.coalesce(func.sum(cast(ProjectQuotationLine.is_non_standard, Integer)), 0),
        )
        .filter(
            ProjectQuotationLine.version_id.in_(version_ids),
            ProjectQuotationLine.is_section.is_(False),
        )
        .one()
    )
    return {
        "discounted": int(row[0]),
        "below_floor": int(row[1]),
        "off_series": int(row[2]),
        # PS-PROPOSAL-QUOTATION: a quotation priced below the proposal it was made from.
        "below_proposal": below_proposal_line_count(db, document),
    }


def _reasons_lower(db: Session, document: ProjectQuotationDocument) -> str:
    text = reasons_text(counts(db, document)) or "no line needs it now"
    return text[:1].lower() + text[1:]


def _needs(c: Dict[str, int]) -> bool:
    return bool(c["discounted"] or c["below_floor"] or c["off_series"] or c["below_proposal"])


def requires_approval(db: Session, document: ProjectQuotationDocument) -> bool:
    """Any discount (a below-floor line is one too), any off-series line (R2), or a quotation
    priced below its proposal (PS-PROPOSAL-QUOTATION)."""
    return _needs(counts(db, document))


def _lines(n: int) -> str:
    return "One line is" if n == 1 else f"{n} lines are"


def reasons_text(c: Dict[str, int]) -> str:
    """"1 line is outside the project's series and 2 lines are below the minimum price".

    Below-floor outranks plain discount in the wording, because it is the stronger fact; a
    discount that stays above the minimum price is "priced below the default price".
    """
    parts = []
    if c.get("off_series"):
        parts.append(f"{_lines(c['off_series'])} outside the project's series")
    if c.get("below_floor"):
        parts.append(f"{_lines(c['below_floor'])} priced below the minimum price")
    other = max(0, (c.get("discounted") or 0) - (c.get("below_floor") or 0))
    if other:
        parts.append(f"{_lines(other)} priced below the default price")
    if c.get("below_proposal"):
        parts.append(f"{_lines(c['below_proposal'])} priced below the proposal")
    text = " and ".join(parts)
    # Only the first word keeps its capital.
    return text[:1] + text[1:].replace("One line", "one line")


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


# ------------------------------------------------------------------ the routing
#
# PS-QUOTE-RULES R4-R7 (owner ruling 2 Nov ~21:20): one approver per request, from data an admin
# edits, never a hard-coded person. Walked in order, the first eligible candidate wins:
#   1. an off-series line -> System Settings "off-series approver" (CK today);
#   2. the project's own override (`projects.discount_approver_user_id`);
#   3. the project owner's superior, and up THEIR superior line (regional manager, then CK);
#   4. the configured default quotation approver (System Settings);
#   5. nobody resolves -> Send for approval is refused, never "anyone holding the grant".
# A candidate is skipped when inactive, when it is the requester, or when it lacks the grant;
# a skipped superior hands on to their own superior.

_ADMIN_ROLE_SLUGS = frozenset({"admin", "superadmin"})
_CHAIN_LIMIT = 10  # a superior loop in the data must end the walk, not hang the request


def _user(db: Session, user_id: Optional[str]):
    from app.models.user import User

    if not user_id:
        return None
    return db.query(User).filter(User.id == str(user_id)).first()


def _eligible(
    db: Session,
    user_id: Optional[str],
    *,
    requester_id: Optional[str],
    company_id: Optional[str],
) -> bool:
    """Active, a person, holds the grant AND the project view, and may work in the quotation's
    company (the company rule ``project_notify_service.approver_user_ids`` applies): an approver
    who cannot open the project cannot decide it."""
    from app.models.company import UserCompany
    from app.models.user import UserStatus
    from app.services.user_service import UserPermissionService

    user = _user(db, user_id)
    if user is None or str(user.id) == str(requester_id or ""):
        return False
    if user.status != UserStatus.ACTIVE.value or user.is_trashed or user.is_integration:
        return False
    if company_id and (
        db.query(UserCompany.id)
        .filter(UserCompany.user_id == user.id, UserCompany.company_id == str(company_id))
        .first()
        is None
    ):
        return False
    slugs = UserPermissionService(db).get_user_permission_slugs(user.id)
    # Crew B1 (3 Nov): holding the grant is not enough, the approver must be able to OPEN the
    # quotation, which needs the full project view (`view_own` reaches only their own projects).
    return APPROVE_PERMISSION in slugs and VIEW_PERMISSION in slugs


def superior_chain(db: Session, user_id: Optional[str]) -> list[str]:
    """``user_id``'s superiors, nearest first, cycle-safe."""
    chain: list[str] = []
    seen = {str(user_id)} if user_id else set()
    current = _user(db, user_id)
    while current is not None and current.superior_id and len(chain) < _CHAIN_LIMIT:
        nxt = str(current.superior_id)
        if nxt in seen:
            break
        seen.add(nxt)
        chain.append(nxt)
        current = _user(db, nxt)
    return chain


def _first_eligible_from(
    db: Session,
    user_id: Optional[str],
    *,
    requester_id: Optional[str],
    company_id: Optional[str],
) -> Optional[str]:
    """``user_id`` if eligible, else the nearest eligible superior above them."""
    if not user_id:
        return None
    for candidate in [str(user_id), *superior_chain(db, user_id)]:
        if _eligible(db, candidate, requester_id=requester_id, company_id=company_id):
            return candidate
    return None


def _setting(db: Session, column: str) -> Optional[str]:
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    return getattr(row, column, None) if row is not None else None


def off_series_approver_id(db: Session) -> Optional[str]:
    return _setting(db, "off_series_approver_user_id")


def default_approver_id(db: Session) -> Optional[str]:
    """The configured last resort (crew answer to R4.4): never "anyone holding the grant",
    because on prod that grant is also held by customer-service staff and an integration."""
    return _setting(db, "default_quotation_approver_user_id")


def route_approver(
    db: Session,
    document: ProjectQuotationDocument,
    *,
    requester_id: Optional[str],
) -> Optional[str]:
    """Who this request goes to (R4). The one resolver, also for the quotation after WON (R8)."""
    project = _project_of(db, document)
    candidates: list[Optional[str]] = []
    if off_series_line_count(db, document):
        candidates.append(off_series_approver_id(db))
    if project is not None:
        candidates.append(getattr(project, "discount_approver_user_id", None))
        # The owner's superior: the discount is the owner's even when a colleague pressed Send.
        # No owner, or an owner with no superior: the requester's own superior.
        owner = project.owner_user_id
        start = superior_chain(db, owner)[:1] if owner else []
        if not start and requester_id:
            start = superior_chain(db, requester_id)[:1]
        candidates.extend(start)
    candidates.append(default_approver_id(db))
    # No per-size tiers (owner 2 Nov ~21:40): the discount ceiling is the series' own max
    # discount, which the minimum price already enforces; every request has ONE approver.
    for candidate in candidates:
        found = _first_eligible_from(
            db, candidate, requester_id=requester_id, company_id=document.company_id
        )
        if found:
            return found
    return None


def _is_admin(db: Session, user_id: Optional[str]) -> bool:
    from app.services.user_service import UserPermissionService

    if not user_id:
        return False
    return bool(UserPermissionService(db).get_user_role_slugs(user_id) & _ADMIN_ROLE_SLUGS)


def may_decide(
    db: Session,
    document: ProjectQuotationDocument,
    *,
    actor_user_id: Optional[str],
    permissions: Iterable[str],
) -> bool:
    """R5: the routed approver, anyone above them on the superior line, or an admin, and in
    every case NOT the person who asked (security review: being above the routed approver, an
    admin, or in a superior loop must not let anyone approve their own discount).

    A request with no routed approver is decided as before (any holder of the grant) only when
    it was raised before routing existed. One that WAS routed and lost its approver (their
    account deleted, the column set NULL) goes to an admin, never back to every grant holder.
    """
    if APPROVE_PERMISSION not in set(permissions or ()):
        return False
    actor = str(actor_user_id or "")
    event = _requested_event(db, document)
    if event is not None and event.actor_id and str(event.actor_id) == actor:
        return False
    routed = getattr(document, "approver_user_id", None)
    if not routed:
        was_routed = event is not None and "approver_user_id" in (event.system_payload or {})
        return _is_admin(db, actor_user_id) if was_routed else True
    if actor == str(routed) or actor in superior_chain(db, routed):
        return True
    return _is_admin(db, actor_user_id)


# ------------------------------------------------------------------- the gate


def assert_issuable(db: Session, document: ProjectQuotationDocument) -> None:
    """Refuse to issue a discounted or off-series quotation that nobody has approved.

    Says how many lines and why, because the block on the screen has to be actionable. The
    code stays ``quotation_below_floor_pending_approval`` whenever a line is below the minimum
    price (the screen already handles it), ``quotation_off_series_pending_approval`` when the
    only reason is the series, else ``quotation_discount_pending_approval``.
    """
    c = counts(db, document)
    if not _needs(c):
        return
    if current_key(db, document) == STATUS_APPROVED:
        return
    if c["below_floor"]:
        code = "quotation_below_floor_pending_approval"
    elif c["below_proposal"]:
        code = "quotation_below_proposal_pending_approval"
    elif c["off_series"] and not c["discounted"]:
        code = "quotation_off_series_pending_approval"
    else:
        code = "quotation_discount_pending_approval"
    raise AppException(
        status_code=422,
        message=(
            f"{reasons_text(c)}, so this quotation needs a manager's approval before it can be "
            "sent to the customer."
        ),
        code=code,
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


def source_prices_approved(db: Session, source: ProjectQuotationDocument) -> bool:
    """The source's lines, as they stand, are prices a manager approved (QUOTE-DUPLICATE-PARTY).

    True while it stands on ``approved`` (locked, so its lines cannot have moved since), or on
    ``issued`` when every scope's current version is the one its latest revision went out with:
    sending spends the approval, and a send that needed one could not have happened without it.
    """
    key = current_key(db, source)
    if key == STATUS_APPROVED:
        return True
    if key != STATUS_ISSUED:
        return False
    from app.models.projects import ProjectQuotationIssue, ProjectQuotationIssueScope

    latest = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == source.id)
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .first()
    )
    if latest is None:
        return False
    sent = {
        str(row[0])
        for row in db.query(ProjectQuotationIssueScope.version_id)
        .filter(ProjectQuotationIssueScope.issue_id == latest.id)
        .all()
    }
    current = {str(v) for v in current_version_ids(db, source)}
    return bool(current) and current == sent


def carry_approval(
    db: Session,
    *,
    copy: ProjectQuotationDocument,
    source: ProjectQuotationDocument,
    actor_user_id: Optional[str] = None,
) -> bool:
    """Give a duplicate the source's approval when it needs one and the source's prices were
    approved as they stand. The copy then sits on ``approved`` like any approved document:
    locked, and spent by its own first send. Returns whether it was carried."""
    if not requires_approval(db, copy):
        return False
    if not source_prices_approved(db, source):
        return False
    _set_status(db, copy, _status_by_key(db, STATUS_APPROVED))
    copy.approver_user_id = source.approver_user_id
    # Its own event (security review N1): the copy's approver never saw the copy, so the feed
    # says whose approval it is and who carried it, rather than a second "approved".
    _record(
        db,
        copy,
        template="quotation_approval_carried",
        body_text=(
            f"{_actor_name(db, actor_user_id)} carried the approval of {source.document_no} "
            f"to {copy.document_no}"
        ),
        actor_user_id=actor_user_id,
        payload={"source_document_id": str(source.id), "source_document_no": source.document_no},
    )
    db.flush()
    return True


def assert_unlocked(db: Session, document: Optional[ProjectQuotationDocument]) -> None:
    """Refuse an edit to a quotation a manager is looking at, or has already approved."""
    if document is None:
        return
    if current_key(db, document) in LOCKED_KEYS:
        raise AppException(
            status_code=422,
            message=(
                "This quotation is with a manager or already approved, so it cannot be "
                "edited. Revise it first."
            ),
            code="quotation_locked_for_approval",
        )


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


def _requested_event(db: Session, document: ProjectQuotationDocument):
    """The newest `quotation_approval_requested` row naming THIS document, or None."""
    from app.models.activities import ActivityEvent

    project = _project_of(db, document)
    if project is None:
        return None
    return (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.entity_type == "project",
            ActivityEvent.entity_id == str(project.id),
            ActivityEvent.system_template == "quotation_approval_requested",
            ActivityEvent.system_payload["document_id"].astext == str(document.id),
        )
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .first()
    )


def _press_count(db: Session, document: ProjectQuotationDocument) -> int:
    """How many times this document has been sent for approval: the per-press dedup key."""
    from app.models.activities import ActivityEvent

    project = _project_of(db, document)
    if project is None:
        return 0
    return (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.entity_type == "project",
            ActivityEvent.entity_id == str(project.id),
            ActivityEvent.system_template == "quotation_approval_requested",
            ActivityEvent.system_payload["document_id"].astext == str(document.id),
        )
        .count()
    )


def requester_id(db: Session, document: ProjectQuotationDocument) -> Optional[str]:
    """Who pressed Send for approval last; the project owner when no such row exists.

    The owner fallback skips an integration user: a bot has nobody to read the message.
    """
    event = _requested_event(db, document)
    if event is not None and event.actor_id:
        return str(event.actor_id)
    project = _project_of(db, document)
    if project is None or not project.owner_user_id:
        return None
    from app.models.user import User

    owner = db.query(User).filter(User.id == project.owner_user_id).first()
    if owner is None or owner.is_integration:
        return None
    return str(project.owner_user_id)


def move(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    to_status_id: str,
    actor_user_id: str,
) -> ProjectQuotationDocument:
    """The salesperson's one self-serve move: ask for approval.

    From Rejected the same press resubmits: the graph has no rejected -> pending edge, so both
    edges it does have (rejected -> draft -> pending) are checked and the document lands on
    pending in one step, with one `quotation_approval_requested` row. There is no back-to-draft
    move. The edit rights the route checks are the only grant needed.
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

    from_id = _from_status_id(db, document)
    if target.key == STATUS_PENDING and current_key(db, document) == STATUS_REJECTED:
        # Resubmit (C1): the graph has no rejected -> pending edge, so walk the two it has.
        draft = _status_by_key(db, STATUS_DRAFT)
        status_service.assert_transition_allowed(
            db, ENTITY_TYPE, from_id, draft.id, scope_id=None
        )
        from_id = draft.id
        # ...and land on Resubmitted (RESUBMITTED-STATUS), unless an admin deleted that rung,
        # in which case the press still works and lands on pending as it always did.
        resubmitted = graph(db).by_key(STATUS_RESUBMITTED)
        if resubmitted is not None:
            target = resubmitted
            to_status_id = resubmitted.id
    status_service.assert_transition_allowed(
        db, ENTITY_TYPE, from_id, to_status_id, scope_id=None
    )
    routed_to = None
    if target.key in AWAITING_KEYS:
        # R4: routed once per press and frozen, so a later change of superior or override does
        # not move a request that is already waiting. Resolved BEFORE the rung moves, so a
        # refusal leaves the document exactly where it was.
        routed_to = route_approver(db, document, requester_id=actor_user_id)
        if routed_to is None:
            raise AppException(
                status_code=422,
                message=(
                    "Nobody is set up to approve this quotation. Ask an admin to set your "
                    "superior, this project's discount approver, or the default quotation "
                    "approver in Settings."
                ),
                code="quotation_approver_not_configured",
            )
    _set_status(db, document, target)

    if target.key in AWAITING_KEYS:
        c = counts(db, document)
        document.approver_user_id = routed_to
        db.flush()
        approver = _user(db, document.approver_user_id)
        reasons = reasons_text(c) if any(c.values()) else "no line needs it"
        routed = f" Sent to {approver.name}." if approver is not None and approver.name else ""
        _record(
            db,
            document,
            template="quotation_approval_requested",
            body_text=(
                f"{_actor_name(db, actor_user_id)} asked for approval on quotation "
                f"{document.document_no} ({reasons[:1].lower() + reasons[1:]}).{routed}"
            ),
            actor_user_id=actor_user_id,
            payload={
                "below_floor_line_count": c["below_floor"],
                "discounted_line_count": c["discounted"],
                "off_series_line_count": c["off_series"],
                "below_proposal_count": c["below_proposal"],
                "approver_user_id": document.approver_user_id,
            },
        )
        if c["discounted"] or c["below_floor"]:
            _enter_final_negotiation(db, document, actor_user_id=actor_user_id)
    return document


def _enter_final_negotiation(
    db: Session, document: ProjectQuotationDocument, *, actor_user_id: Optional[str]
) -> None:
    """B2: a discount request puts the project in Final Negotiation (owner ruling 2 Nov).

    Raises the critical flag (its clock starts only on the way in), and moves the stage forward
    to the `final_negotiation` rung when the project's graph has one and the project sits on an
    open rung before it. A system move, like PO received: Spec In has no edge to Final
    Negotiation on prod and the rule is the owner's, not the graph's. Never backwards, never
    out of a closed rung, and nothing undoes it when the discount is withdrawn or rejected (R8 of
    the card): the negotiation happened.
    """
    project = _project_of(db, document)
    if project is None:
        return
    from app.services.project_service import set_critical

    set_critical(project, True)

    # The project's OWN graph (a fork is used exclusively when it exists), and only a live rung:
    # never a default-graph status on a forked project, never an archived or inactive one.
    target = status_service.graph_for_record(db, "project", project).by_key(FINAL_NEGOTIATION_KEY)
    if target is not None and (not target.is_active or target.is_archived):
        target = None
    current = (
        db.query(Status).filter(Status.id == project.status_id).first()
        if project.status_id
        else None
    )
    if target is None:
        logger.info(
            "project %s: no '%s' rung configured; critical flag raised only",
            project.id,
            FINAL_NEGOTIATION_KEY,
        )
        db.flush()
        return
    if current is None or current.id == target.id or current.is_terminal:
        db.flush()
        return
    if (current.sort_order or 0) >= (target.sort_order or 0):
        db.flush()
        return
    project.status_id = target.id
    db.flush()
    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template="stage_changed",
        payload={"to_status_id": str(target.id), "reason": "discount_requested"},
        actor_id=actor_user_id,
    )
    db.flush()


def _assert_can_decide(
    db: Session,
    document: ProjectQuotationDocument,
    actor_user_id: Optional[str],
    permissions: Iterable[str],
) -> None:
    if APPROVE_PERMISSION not in set(permissions or ()):
        raise AppException(
            status_code=403,
            message=(
                "Only a sales manager can approve or reject a discount or an off-series line "
                "on a quotation."
            ),
            code="quotation_approval_forbidden",
        )
    if not may_decide(db, document, actor_user_id=actor_user_id, permissions=permissions):
        event = _requested_event(db, document)
        if event is not None and str(event.actor_id or "") == str(actor_user_id or ""):
            raise AppException(
                status_code=403,
                message="You sent this for approval, so somebody else has to decide it.",
                code="quotation_approval_own_request",
            )
        approver = _user(db, document.approver_user_id)
        who = approver.name if approver is not None and approver.name else "another approver"
        raise AppException(
            status_code=403,
            message=(
                f"This approval is with {who}. Only they, someone they report to, or an "
                "admin can decide it."
            ),
            code="quotation_approval_not_routed_to_you",
        )


def approve(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    permissions: Iterable[str],
) -> ProjectQuotationDocument:
    """The manager accepts the below-floor pricing. The next Issue press then proceeds."""
    _assert_can_decide(db, document, actor_user_id, permissions)
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
            f"{_actor_name(db, actor_user_id)} approved quotation {document.document_no} "
            f"({_reasons_lower(db, document)})."
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
    _assert_can_decide(db, document, actor_user_id, permissions)
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


def revise_approval(
    db: Session,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    reason: Optional[str],
) -> ProjectQuotationDocument:
    """The creator takes a Pending or Approved quotation back to Draft to change it (D3-D5).

    A system move like ``mark_issued``: the graph has no edge for it, the two rungs it leaves
    are simply the two the lock guards. The reason is required and lands in the feed.
    """
    cleaned = " ".join((reason or "").split())
    if not cleaned:
        raise AppException(
            status_code=422,
            message="Say what changed and why, so the manager can see it.",
            code="quotation_revise_reason_required",
        )
    was = current_key(db, document)
    if was not in LOCKED_KEYS:
        raise AppException(
            status_code=422,
            message="Only a quotation that is pending or approved needs revising.",
            code="quotation_not_revisable",
        )
    _set_status(db, document, _status_by_key(db, STATUS_DRAFT))
    _record(
        db,
        document,
        template="quotation_approval_revised",
        body_text=(
            f"{_actor_name(db, actor_user_id)} reopened quotation {document.document_no} "
            f"for changes: {cleaned}"
        ),
        actor_user_id=actor_user_id,
        payload={"reason": cleaned},
    )
    return document


# ---------------------------------------------------------------- notifications
#
# Called by the ROUTES after they commit the status. Best effort, each with its own try/except:
# a notification fault never fails the action and never undoes the committed rung. A fault that
# poisons the session is rolled back here, which is harmless because the status is already
# committed.


def _best_effort(kind: str, db: Session, send) -> None:
    try:
        send()
    except Exception as exc:  # noqa: BLE001
        logger.warning("quotation approval notification failed: kind=%s (%s)", kind, exc)
    finally:
        # A statement that failed inside the sender (swallowed per recipient) leaves the
        # transaction aborted; the status is committed already, so rolling back loses nothing
        # and lets the route go on to read the document.
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def notify_requested(
    db: Session, document: ProjectQuotationDocument, actor_user_id: Optional[str]
) -> None:
    def send() -> None:
        project = _project_of(db, document)
        if project is None:
            return
        from app.services import project_notify_service as notify

        c = counts(db, document)
        notify.notify_quotation_approval_requested(
            db,
            project=project,
            document=document,
            resubmitted=current_key(db, document) == STATUS_RESUBMITTED,
            press=str(_press_count(db, document)),
            below=c["below_floor"],
            reasons=reasons_text(c) if any(c.values()) else None,
            requester_id=actor_user_id,
            requester_name=_actor_name(db, actor_user_id),
        )

    _best_effort("requested", db, send)


def notify_decided(
    db: Session,
    document: ProjectQuotationDocument,
    actor_user_id: Optional[str],
    *,
    approved: bool,
    reason: Optional[str] = None,
) -> None:
    def send() -> None:
        project = _project_of(db, document)
        if project is None:
            return
        from app.services import project_notify_service as notify

        notify.notify_quotation_approval_decided(
            db,
            project=project,
            document=document,
            approved=approved,
            recipient_id=requester_id(db, document),
            decider_id=actor_user_id,
            decider_name=_actor_name(db, actor_user_id),
            reason=reason,
        )

    _best_effort("approved" if approved else "rejected", db, send)


def notify_withdrawn(
    db: Session,
    document: ProjectQuotationDocument,
    actor_user_id: Optional[str],
    reason: Optional[str],
) -> None:
    def send() -> None:
        project = _project_of(db, document)
        if project is None:
            return
        from app.services import project_notify_service as notify

        notify.notify_quotation_approval_withdrawn(
            db,
            project=project,
            document=document,
            actor_id=actor_user_id,
            actor_name=_actor_name(db, actor_user_id),
            reason=reason,
        )

    _best_effort("withdrawn", db, send)


# ------------------------------------------------------------------ serialize


def serialize_approval(
    db: Session, document: ProjectQuotationDocument, *, viewer_id: Optional[str] = None
) -> Dict[str, Any]:
    """The approval block of the document payload.

    Its own function so ``serialize_document`` cannot drift from it, and so every one of these
    keys is present on EVERY document - absent would be as bad as wrong, because the screen
    reads them to decide whether to render the gate at all.
    """
    status = status_of(db, document)
    c = counts(db, document)
    approver = _user(db, getattr(document, "approver_user_id", None))
    return {
        "approval_status_id": str(status.id) if status is not None else None,
        "approval_status_key": status.key if status is not None else None,
        "approval_status_label": status.label if status is not None else None,
        "approval_rejected_reason": document.approval_rejected_reason,
        "requires_approval": _needs(c),
        "below_floor_line_count": c["below_floor"],
        "below_proposal_count": c["below_proposal"],
        "discounted_line_count": c["discounted"],
        "off_series_line_count": c["off_series"],
        "approval_reasons": reasons_text(c) if any(c.values()) else None,
        "approver_user_id": str(approver.id) if approver is not None else None,
        "approver_name": (approver.name or approver.email) if approver is not None else None,
        # Whether THIS viewer may approve or reject the request now (R5), so the screen offers
        # the decision only to someone the server will accept. None when no viewer is known.
        "viewer_may_decide": _viewer_may_decide(db, document, viewer_id),
    }


def _viewer_may_decide(
    db: Session, document: ProjectQuotationDocument, viewer_id: Optional[str]
) -> Optional[bool]:
    if not viewer_id:
        return None
    if current_key(db, document) not in AWAITING_KEYS:
        return False
    from app.services.user_service import UserPermissionService

    permissions = UserPermissionService(db).get_user_permission_slugs(viewer_id)
    return may_decide(db, document, actor_user_id=viewer_id, permissions=permissions)
