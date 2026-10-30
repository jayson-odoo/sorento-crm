"""A quotation line's missing technical drawing or photo, escalated to the marketing product team.

Two kinds, `drawing` and `photo`, one task per (kind, PRODUCT, REQUESTER): a salesperson's first
Escalate opens their own task on the tracker table, their later ones (any quotation) join it (an
event-log row per quotation version). A second salesperson opens a task of their own, as chat
escalations are one ticket per person (PLAN-quote-media-chat-30oct B1). The task rides the
WhatsApp bot's general-enquiries route and nothing is configured for it: the agent coded
`general_enquiries`, the team set named by the chatbot domain `product_attachment`, the tier-1
team of that set in the PRODUCT'S company, an assignee drawn round-robin narrowed by the product's
brand, the policy bound to that team set. No team, agent or policy code is written here.

The team works the task the normal SLA way (Respond, Resolve). Adding a file does not close it: it
notifies the assignee. Resolving notifies the requester.

When the requester's user row is linked to a WhatsApp contact, the task carries that contact: the
requester gets one acknowledgement on WhatsApp, the PIC replies in the ticket conversation panel
(a reply is the Respond), and resolving closes it the way a chat ticket closes (B2 to B6).

Hand-offs (plan rule 10) go through `NotificationService.create_with_channel_preferences`, the
call every form-SLA assignment uses: in-app always, email and WhatsApp each gated by the
recipient's own toggle and a linked WhatsApp contact.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, exists as db_exists, func, or_, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, RespondContact
from app.models.chatbot_policy import ChatbotDomain
from app.models.product import Product, ProductAttachment
from app.models.projects import ProjectQuotation, ProjectQuotationLine, ProjectQuotationVersion
from app.models.resources import Attachment, AttachmentType
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking, SLAPolicyTier
from app.services.error_handler import AppException, handle_not_found, handle_validation_error
from app.services.product_image_service import DRAWING_TYPE
from app.services.sla_scope import open_tracker_scope

logger = logging.getLogger(__name__)

#: kind -> the tracker's source_entity_type.
SOURCE_TYPES = {"drawing": "product_drawing", "photo": "product_photo"}
KIND_NOUN = {"drawing": "drawing", "photo": "photo"}
#: The chatbot's escalation route for product attachment asks: agent and domain row.
AGENT_CODE = "general_enquiries"
DOMAIN_NAME = "product_attachment"
#: How long an escalation waits for another click on the same product before answering busy.
LOCK_TIMEOUT_SECONDS = 10
REQUESTER_EVENT = "requester"
_VERSION_REASON_PREFIX = "quotation_version:"


def _is_drawing_file():
    """The file conditions that make an attachment a drawing: not deleted, an image or a PDF."""
    return (
        Attachment.is_deleted.is_(False),
        or_(Attachment.mime_type.ilike("image/%"), Attachment.mime_type == "application/pdf"),
    )


def has_drawing(db: Session, product_id: str) -> bool:
    """A non-deleted file typed "Technical Specifications", image or PDF, is linked to the product."""
    found = (
        db.query(ProductAttachment.id)
        .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(
            ProductAttachment.product_id == str(product_id),
            AttachmentType.type_name == DRAWING_TYPE,
            *_is_drawing_file(),
        )
        .first()
    )
    return found is not None


def attachment_is_drawing(db: Session, attachment_id: str) -> bool:
    """Whether this one attachment counts as a drawing (what a product link has just added)."""
    found = (
        db.query(Attachment.id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(
            Attachment.id == str(attachment_id),
            AttachmentType.type_name == DRAWING_TYPE,
            *_is_drawing_file(),
        )
        .first()
    )
    return found is not None


def has_photo(db: Session, product_id: str) -> bool:
    """Any photograph the cell counts: an image, not deleted, not typed "Technical Specifications"."""
    from app.services import product_image_service as images

    return any(not f.is_drawing for f in images.files_for(db, [str(product_id)]).get(str(product_id), []))


def attachment_kind(db: Session, attachment_id: str) -> Optional[str]:
    """What a newly linked attachment is to a request: `drawing`, `photo`, or nothing."""
    if attachment_is_drawing(db, attachment_id):
        return "drawing"
    found = (
        db.query(Attachment.id)
        .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(
            Attachment.id == str(attachment_id),
            Attachment.is_deleted.is_(False),
            Attachment.mime_type.ilike("image/%"),
            func.coalesce(AttachmentType.type_name, "") != DRAWING_TYPE,
        )
        .first()
    )
    return "photo" if found is not None else None


# ------------------------------------------------------------------------------ the cell state


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Tracker columns are naive UTC; the cell's clocks leave as aware UTC so a browser reads them right."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _raised_by(requester_id: str):
    """The tracker has a requester row naming this user: the task is theirs (one requester per
    task, B1)."""
    return (
        db_exists(ConversationSLAEventLog.id)
        .where(
            ConversationSLAEventLog.sla_tracking_id == ConversationSLATracking.id,
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
            ConversationSLAEventLog.triggered_by_id == str(requester_id),
        )
        .correlate(ConversationSLATracking)
    )


def _open_tracker(
    db: Session, product_id: str, source: str, requester_id: Optional[str] = None
) -> Optional[ConversationSLATracking]:
    """The product's open task of this kind; with ``requester_id``, that requester's own."""
    query = db.query(ConversationSLATracking).filter(
        ConversationSLATracking.source_entity_type == source,
        ConversationSLATracking.source_entity_id == str(product_id),
        *open_tracker_scope(),
    )
    if requester_id:
        query = query.filter(_raised_by(requester_id))
    return query.order_by(ConversationSLATracking.initiated_at.desc()).first()


def _open_trackers(db: Session, product_id: str, source: str) -> List[ConversationSLATracking]:
    """Every open task of this kind for the product (one per requester)."""
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == source,
            ConversationSLATracking.source_entity_id == str(product_id),
            *open_tracker_scope(),
        )
        .order_by(ConversationSLATracking.initiated_at.asc())
        .all()
    )


def escalation_states_by_kind(
    db: Session, product_ids: Iterable[Optional[str]], requester_id: Optional[str] = None
) -> Dict[str, Dict[str, Optional[Dict[str, Any]]]]:
    """``{kind: {product id: the cell's escalation state}}`` for both kinds, in a fixed number of
    queries (ONE for the trackers and their requester counts).

    An open task reads its ids and clocks; with none open, a resolved one leaves only
    ``last_resolved_at``; a product never escalated reads None. With ``requester_id`` only that
    requester's own tasks count (B8: a colleague's open request does not hide Escalate).
    """
    ids = list(dict.fromkeys(str(pid) for pid in product_ids if pid))
    out: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {kind: {} for kind in SOURCE_TYPES}
    if not ids:
        return out
    kind_of = {source: kind for kind, source in SOURCE_TYPES.items()}

    # One read for the open tasks (with their requester counts) and the resolved history: the
    # latter only feeds "last resolved", and a product's history is a handful of rows.
    requester_count = (
        db.query(func.count(func.distinct(ConversationSLAEventLog.triggered_by_id)))
        .filter(
            ConversationSLAEventLog.sla_tracking_id == ConversationSLATracking.id,
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
        )
        .correlate(ConversationSLATracking)
        .scalar_subquery()
    )
    open_rows: Dict[tuple, ConversationSLATracking] = {}
    counts: Dict[str, int] = {}
    resolved: Dict[tuple, datetime] = {}
    query = db.query(ConversationSLATracking, requester_count).filter(
        ConversationSLATracking.source_entity_type.in_(list(kind_of)),
        ConversationSLATracking.source_entity_id.in_(ids),
        or_(
            and_(*open_tracker_scope()),
            and_(
                ConversationSLATracking.is_resolved.is_(True),
                ConversationSLATracking.resolved_at.isnot(None),
            ),
        ),
    )
    if requester_id:
        query = query.filter(_raised_by(requester_id))
    for tracker, requesters in query.order_by(ConversationSLATracking.initiated_at.desc()).all():
        key = (kind_of[tracker.source_entity_type], str(tracker.source_entity_id))
        if tracker.is_resolved:
            if key not in resolved or tracker.resolved_at > resolved[key]:
                resolved[key] = tracker.resolved_at
        elif tracker.voided_at is None and key not in open_rows:
            open_rows[key] = tracker
            counts[str(tracker.id)] = int(requesters or 0)

    for kind in SOURCE_TYPES:
        for pid in ids:
            tracker = open_rows.get((kind, pid))
            if tracker is not None:
                responded = bool(tracker.is_responded)
                out[kind][pid] = {
                    "tracking_id": str(tracker.id),
                    "opened_at": _utc(tracker.initiated_at),
                    "responded_at": _utc(tracker.responded_at or tracker.updated_at) if responded else None,
                    "due_at": _utc(tracker.due_at_resolution or tracker.due_at) if responded else _utc(tracker.due_at),
                    "requester_count": counts.get(str(tracker.id), 0),
                    "last_resolved_at": _utc(resolved.get((kind, pid))),
                }
            elif (kind, pid) in resolved:
                out[kind][pid] = {
                    "tracking_id": None,
                    "opened_at": None,
                    "responded_at": None,
                    "due_at": None,
                    "requester_count": None,
                    "last_resolved_at": _utc(resolved[(kind, pid)]),
                }
            else:
                out[kind][pid] = None
    return out


def escalation_states(
    db: Session,
    product_ids: Iterable[Optional[str]],
    kind: str = "drawing",
    requester_id: Optional[str] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """The cell's escalation state per product for one kind."""
    return escalation_states_by_kind(db, product_ids, requester_id=requester_id)[kind]


# --------------------------------------------------------------------------------- escalate


def _line_in_version(db: Session, version_id: str, line_id: str) -> ProjectQuotationLine:
    line = (
        db.query(ProjectQuotationLine)
        .join(ProjectQuotationVersion, ProjectQuotationVersion.id == ProjectQuotationLine.version_id)
        .filter(ProjectQuotationLine.id == str(line_id), ProjectQuotationVersion.id == str(version_id))
        .first()
    )
    if line is None:
        raise handle_not_found("Quotation line", str(line_id))
    return line


@contextmanager
def _product_lock(db: Session, source: str, product_id: str, user_id: Optional[str] = None):
    """A session-level Postgres advisory lock keyed on the kind, product and requester, held
    across commits (one task per requester, so two people never wait on each other).

    A row lock would not do: assigning the task commits (the round-robin cursor), which would
    release it before the tracker exists. The lock lives on ONE connection and is released on
    that same connection, inside the one transaction that connection keeps open from lock to
    unlock (no COMMIT in between: behind a transaction-mode pooler a commit would hand the
    connection back and the unlock would run on another one). The timeout is transaction-local,
    so it ends with that transaction. A pooled engine can hand the session a different connection after a
    commit, so the lock gets a connection of its own; a session bound to a single connection
    (a test's) uses that connection, which never changes.
    """
    key = {"k": ":".join(str(part) for part in (source, product_id, user_id) if part)}
    bind = db.get_bind()
    owned = None if isinstance(bind, Connection) else bind.connect()
    conn = bind if owned is None else owned
    # The wait is bounded, so a hung holder cannot block later escalations of the product for
    # ever. The session's own connection goes through the session so a timeout rolls back to its
    # savepoint; a connection of the lock's own is rolled back directly.
    runner = db if owned is None else owned
    try:
        runner.execute(
            text("SELECT set_config('lock_timeout', :v, true)"),
            {"v": f"{int(LOCK_TIMEOUT_SECONDS * 1000)}ms"},
        )
        runner.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), key)
    except DBAPIError as exc:
        runner.rollback()
        if owned is not None:
            owned.close()
        if getattr(exc.orig, "sqlstate", None) == "55P03" or "lock timeout" in str(exc.orig).lower():
            raise AppException(
                status_code=409,
                message="Someone else is escalating this product, try again.",
                code="drawing_request_busy",
            )
        raise
    try:
        yield
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), key)
        except Exception:
            logger.warning("could not release the drawing request lock for %s", product_id, exc_info=True)
            if owned is not None:
                owned.invalidate()
        finally:
            if owned is not None:
                owned.close()


def escalate(db: Session, *, version_id: str, line_id: str, user: dict, kind: str) -> Dict[str, Any]:
    """Open the caller's task of this kind for the product, or join their open one. Returns
    ``{joined, escalation}``."""
    from app.services.project_quotation_image_service import line_product_id

    source = SOURCE_TYPES.get(kind)
    if source is None:
        raise AppException(
            status_code=400, message="Ask for a drawing or a photo.", code="unknown_request_kind"
        )
    line = _line_in_version(db, version_id, line_id)
    product_id = line_product_id(line)
    if not product_id:
        raise AppException(
            status_code=409,
            message="This line has no catalogue product to request a file for.",
            code="line_has_no_product",
        )
    # Through the scoped ORM: a product of a company the caller cannot see is not found, and
    # its company is the one the task is routed under.
    product = db.query(Product.id, Product.company_id).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(status_code=404, message="Product not found.", code="product_not_found")
    if kind == "drawing" and has_drawing(db, product_id):
        raise AppException(
            status_code=409, message="This product already has a drawing.", code="product_has_drawing"
        )
    if kind == "photo" and has_photo(db, product_id):
        raise AppException(
            status_code=409, message="This product already has a photo.", code="product_has_photo"
        )

    # Two clicks in the same second must open one task. "Is there an open task of mine" is read
    # then write, so the (product, requester) is locked from the check until the requester is
    # recorded.
    user_id = str(user["id"])
    ack: Optional[tuple] = None
    with _product_lock(db, source, product_id, user_id):
        tracker = _open_tracker(db, product_id, source, requester_id=user_id)
        joined = tracker is not None
        if tracker is None:
            tracker = _open_task(
                db,
                source,
                product_id,
                str(product.company_id) if product.company_id else None,
                requester_id=user_id,
                version_id=str(version_id),
                kind=kind,
            )
            if tracker.respond_contact_id:
                ack = (
                    str(tracker.respond_contact_id),
                    _ack_text(db, kind, product_id, str(version_id)),
                    str(tracker.id),
                )
        _record_requester(db, tracker, version_id=str(version_id), user_id=user_id)
        db.commit()
    if ack is not None:
        # After the commit, so a queued message never names a task that rolled back (B3).
        contact_id, ack_text, tracking_id = ack
        enqueue_request_ack(contact_id, ack_text, tracking_id=tracking_id)
    return {
        "joined": joined,
        "escalation": escalation_states(db, [product_id], kind, requester_id=user_id)[str(product_id)],
    }


def _not_set_up() -> AppException:
    return AppException(
        status_code=409,
        message="The marketing product team is not set up for this company",
        # Empty, not null: nothing more is said to the screen (the log has the detail).
        detail="",
        code="marketing_team_not_set_up",
    )


def _quotation_no(db: Session, version_id: str) -> str:
    """The number the quotation page prints for this version: its document's number."""
    from app.models.projects import ProjectQuotationDocument

    number = (
        db.query(ProjectQuotationDocument.document_no)
        .join(ProjectQuotation, ProjectQuotation.document_id == ProjectQuotationDocument.id)
        .join(ProjectQuotationVersion, ProjectQuotationVersion.quotation_id == ProjectQuotation.id)
        .filter(ProjectQuotationVersion.id == str(version_id))
        .scalar()
    )
    return number or "a quotation"


#: kind -> how the ticket names the file asked for (source text and acknowledgement).
_ASK_NOUN = {"drawing": "technical drawing", "photo": "product photo"}


def _source_text(db: Session, kind: str, product_id: str, version_id: str) -> str:
    """The ticket's enquiry line: what the chat drawer quotes and the resolved message excerpts."""
    noun = _ASK_NOUN[kind]
    return f"{noun[0].upper()}{noun[1:]} for {_product_code(db, product_id)} ({_quotation_no(db, version_id)})"


def _ack_text(db: Session, kind: str, product_id: str, version_id: str) -> str:
    return (
        f"Your project request: {_ASK_NOUN[kind]} for {_product_code(db, product_id)} "
        f"({_quotation_no(db, version_id)}). Routed to your PIC, they will reply shortly."
    )


def _requester_contact_id(db: Session, user_id: str) -> Optional[str]:
    """The requester's linked WhatsApp contact, only when that contact row exists and carries a
    Respond.io id (B2): without one the panel could not send, so the task stays a form row."""
    from app.models.user import User

    contact_id = db.query(User.respond_contact_id).filter(User.id == str(user_id)).scalar()
    if not contact_id:
        return None
    found = (
        db.query(RespondContact.id)
        .filter(
            RespondContact.id == str(contact_id),
            func.coalesce(func.trim(RespondContact.respond_io_id), "") != "",
        )
        .first()
    )
    return str(found[0]) if found is not None else None


def enqueue_request_ack(contact_id: str, text: str, tracking_id: Optional[str] = None) -> None:
    """Queue the requester's one WhatsApp acknowledgement of a new task (B3) on the `respond_io`
    queue; ``tracking_id`` is the task its outbox row hangs off. Best-effort: the task has
    already committed, so a queue that is away is logged."""
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.respond_io_tasks import send_media_request_ack

        enqueue_job(
            send_media_request_ack,
            str(contact_id),
            text,
            str(tracking_id) if tracking_id else None,
            queue_name="respond_io",
            job_timeout=120,
        )
    except Exception as exc:  # noqa: BLE001 - enqueue is best-effort
        logger.warning("media request acknowledgement enqueue failed for contact %s: %s", contact_id, exc)


def _open_task(
    db: Session,
    source: str,
    product_id: str,
    company_id: Optional[str],
    *,
    requester_id: str,
    version_id: str,
    kind: str,
) -> ConversationSLATracking:
    """Create the task on the general-enquiries route and tell its assignee (H1).

    The route is the one the bot's product-attachment asks take: the agent, the team set the
    chatbot domain names, the tier-1 team of that set in the product's company, a round-robin
    draw narrowed by the product's brand, the team set's own policy. Any missing piece is the
    same plain 409; the detail goes to the log, because it names agents and team sets.
    """
    from app.services.chatbot.lanes.escalation_services import focus_product_origin
    from app.services.coverage_subscription_service import (
        coverage_note,
        resolve_assignee_with_coverage,
    )
    from app.services.form_sla_service import (
        FormSLAOrchestrator,
        _utc_naive_now,
        _working_clock_start_naive,
        _working_due_naive,
    )
    from app.services.user_service import AccessAgentService

    def refuse(why: str) -> AppException:
        db.rollback()
        logger.warning("media request for product %s cannot be routed: %s", product_id, why)
        return _not_set_up()

    agent = db.query(AccessAgent).filter(AccessAgent.code == AGENT_CODE).first()
    if agent is None:
        raise refuse(f"no access agent coded {AGENT_CODE}")
    domain = db.query(ChatbotDomain).filter(ChatbotDomain.name == DOMAIN_NAME).first()
    team_set = (domain.escalation_team_code or "").strip() if domain is not None else ""
    if not team_set:
        raise refuse(f"chatbot domain {DOMAIN_NAME} names no escalation team set")
    if not company_id:
        raise refuse("the product has no company")

    agents = AccessAgentService(db)
    resolved = agents.resolve_team_with_tier_fallback(
        str(agent.id), 1, team_set_code=team_set, company_id=company_id
    )
    if not resolved:
        raise refuse(f"team set {team_set} has no team for company {company_id}")
    team_id, tier = resolved
    try:
        policy_id = agents.resolve_policy_id_for(str(agent.id), team_set, company_id=company_id)
    except AppException as exc:
        if exc.status_code >= 500:
            raise
        raise refuse(f"policy binding of {team_set}: {exc.message}")
    if not policy_id:
        raise refuse(f"team set {team_set} has no SLA policy bound")
    tier_row = (
        db.query(SLAPolicyTier)
        .filter(SLAPolicyTier.policy_id == policy_id, SLAPolicyTier.tier_level == tier)
        .first()
    )
    if tier_row is None:
        raise refuse(f"SLA policy {policy_id} has no tier {tier}")

    # What the bot's escalation reads: the brand is the product's, lower-cased. A bare id string
    # is ignored by this helper, so the focus entry is the dict shape.
    brand = focus_product_origin(db, [{"uuid": str(product_id), "hint": "product"}])["brand"]
    assignee = agents.get_next_assignee(str(agent.id), team_id, brand_code=brand or None)
    if not assignee:
        raise refuse(f"no member in the tier {tier} team of {team_set}")
    assignee, covered_for_id = resolve_assignee_with_coverage(db, assignee)

    now = _utc_naive_now()
    clock_start = _working_clock_start_naive(db, now)
    response_hours = float(getattr(tier_row, "response_hours", 24) or 24)
    resolution_hours = float(getattr(tier_row, "resolution_hours", 24) or 24)
    tracker = ConversationSLATracking(
        policy_id=policy_id,
        current_tier=tier,
        assigned_to=str(assignee.get("respond_user_id")) if assignee.get("respond_user_id") else None,
        assigned_to_id=assignee["id"],
        initiated_at=now,
        current_tier_started_at=clock_start,
        due_at=_working_due_naive(db, clock_start, response_hours),
        due_at_resolution=_working_due_naive(db, clock_start, resolution_hours),
        is_responded=False,
        is_resolved=False,
        company_id=company_id,
        source_entity_type=source,
        source_entity_id=str(product_id),
        agent_id=str(agent.id),
        team_set_code=team_set,
        brand_code=brand or None,
        # B2: the ticket sits on the requester's WhatsApp contact (none: a plain form row).
        respond_contact_id=_requester_contact_id(db, requester_id),
        source_message_text=_source_text(db, kind, product_id, version_id),
    )
    db.add(tracker)
    db.commit()
    db.refresh(tracker)

    orchestrator = FormSLAOrchestrator(db)
    if covered_for_id:
        orchestrator._write_event_log(
            tracker_id=str(tracker.id),
            event_type="assign",
            from_tier=tier,
            to_tier=tier,
            reason=f"Initial assignment{coverage_note(db, covered_for_id)}",
            assigned_to_id=assignee["id"],
            due_at=tracker.due_at,
            trigger="auto",
        )
    orchestrator._notify_assignee(tracker, kind="assigned")
    return tracker


def _record_requester(db: Session, tracker: ConversationSLATracking, *, version_id: str, user_id: str) -> None:
    """One event-log row per quotation version the requester escalated from (the task's
    "Waiting on this" list); a second click from the same version adds nothing."""
    already = (
        db.query(ConversationSLAEventLog.id)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracker.id),
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
            ConversationSLAEventLog.triggered_by_id == user_id,
            ConversationSLAEventLog.reason == f"{_VERSION_REASON_PREFIX}{version_id}",
        )
        .first()
    )
    if already is not None:
        return
    db.add(
        ConversationSLAEventLog(
            sla_tracking_id=str(tracker.id),
            event_type=REQUESTER_EVENT,
            reason=f"{_VERSION_REASON_PREFIX}{version_id}",
            trigger="manual",
            triggered_by_id=user_id,
        )
    )
    db.flush()


# ------------------------------------------------------------------------ respond and resolve


def _tracker_for_actor(db: Session, tracking_id: str, user: dict) -> ConversationSLATracking:
    """The same gates as the SLA resolve route: 404 when unseen, 400 when seen but not theirs."""
    from app.services.sla_service import ConversationSLATrackingService

    service = ConversationSLATrackingService(db)
    tracking = service.get_tracking(str(tracking_id), load_event_logs=False)
    if not tracking:
        raise handle_not_found("Conversation SLA tracking", str(tracking_id))
    if not service.can_user_act_on_tracking(user["id"], tracking):
        raise handle_not_found("Conversation SLA tracking", str(tracking_id))
    if tracking.source_entity_type not in SOURCE_TYPES.values():
        raise AppException(
            status_code=409,
            message="This task is not a drawing or photo request.",
            code="not_a_media_request",
        )
    if not service.can_user_resolve_tracking(user["id"], tracking):
        raise handle_validation_error("This task is assigned to someone else, so you cannot act on it.")
    return tracking


def media_request_detail(db: Session, tracking_id: str, user: dict, *, has_resolve_permission: bool) -> Dict[str, Any]:
    """Everything the side panel shows for one drawing or photo task.

    Same gates as respond/resolve for seeing it: 404 when the viewer cannot see the task, 409 when
    it is not a media task. Acting on it is a separate question (`can_resolve`).
    """
    from app.models.user import User
    from app.services.sla_service import ConversationSLATrackingService, _tracking_company_id
    from app.services.user_service import AccessAgentService

    service = ConversationSLATrackingService(db)
    tracking = service.get_tracking(str(tracking_id), load_event_logs=False)
    if not tracking or not service.can_user_act_on_tracking(user["id"], tracking):
        raise handle_not_found("Conversation SLA tracking", str(tracking_id))
    if tracking.source_entity_type not in SOURCE_TYPES.values():
        raise AppException(
            status_code=409,
            message="This task is not a drawing or photo request.",
            code="not_a_media_request",
        )
    kind = "photo" if tracking.source_entity_type == SOURCE_TYPES["photo"] else "drawing"
    product_id = str(tracking.source_entity_id)
    product = db.query(Product.product_code, Product.product_name).filter(Product.id == product_id).first()

    assignee_name = None
    if tracking.assigned_to_id:
        assignee = db.query(User.name, User.email).filter(User.id == str(tracking.assigned_to_id)).first()
        assignee_name = ((assignee[0] or assignee[1]) if assignee else None)

    team_id = None
    if tracking.agent_id:
        team_id = AccessAgentService(db).get_team_id_by_tier(
            str(tracking.agent_id),
            tracking.current_tier,
            team_set_code=tracking.team_set_code,
            company_id=_tracking_company_id(tracking),
        )

    # The requester's escalations in order; each names one quotation version (the reason).
    rows = (
        db.query(ConversationSLAEventLog.triggered_by_id, ConversationSLAEventLog.reason)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracking.id),
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
            ConversationSLAEventLog.triggered_by_id.isnot(None),
        )
        .order_by(ConversationSLAEventLog.event_at.asc(), ConversationSLAEventLog.id.asc())
        .all()
    )
    # One requester per task (B1): the first requester row names them.
    requester_name = None
    if rows:
        requester = db.query(User.name, User.email).filter(User.id == str(rows[0][0])).first()
        requester_name = (requester[0] or requester[1]) if requester else None

    version_ids = list(
        dict.fromkeys(
            reason[len(_VERSION_REASON_PREFIX):]
            for _uid, reason in rows
            if (reason or "").startswith(_VERSION_REASON_PREFIX)
        )
    )
    quotations: List[Dict[str, Any]] = []
    if version_ids:
        from app.models.projects import ProjectQuotationDocument

        found = {
            str(version_id): (str(quotation_id), str(project_id), scope_label, document_no)
            for version_id, quotation_id, project_id, scope_label, document_no in db.query(
                ProjectQuotationVersion.id,
                ProjectQuotation.id,
                ProjectQuotation.project_id,
                ProjectQuotation.scope_label,
                ProjectQuotationDocument.document_no,
            )
            .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationVersion.quotation_id)
            .outerjoin(ProjectQuotationDocument, ProjectQuotationDocument.id == ProjectQuotation.document_id)
            .filter(ProjectQuotationVersion.id.in_(version_ids))
            .all()
        }
        seen = set()
        for version_id in version_ids:
            hit = found.get(version_id)
            if hit is None or hit[0] in seen:
                continue
            seen.add(hit[0])
            quotation_id, project_id, scope_label, document_no = hit
            quotations.append(
                {
                    "quotation_id": quotation_id,
                    "project_id": project_id,
                    "label": " · ".join(part for part in (document_no, scope_label) if part),
                    "href": f"/project-sales/{project_id}/quotations/{quotation_id}",
                }
            )

    is_assignee = bool(tracking.assigned_to_id) and str(tracking.assigned_to_id) == str(user["id"])
    return {
        "tracking_id": str(tracking.id),
        "kind": kind,
        "product_id": product_id,
        "product_code": product[0] if product else None,
        "product_name": product[1] if product else None,
        "product_href": f"/master-data-management/products/{product_id}",
        "resources_href": "/resource-management/attachment-directories",
        "assignee_name": assignee_name,
        "requester_name": requester_name,
        "assignee_team_id": str(team_id) if team_id else None,
        "is_assignee": is_assignee,
        "can_resolve": bool(
            has_resolve_permission and service.can_user_resolve_tracking(user["id"], tracking)
        ),
        "is_responded": bool(tracking.is_responded),
        "responded_at": _utc(tracking.responded_at),
        "is_resolved": bool(tracking.is_resolved),
        "resolved_at": _utc(tracking.resolved_at),
        "due_at": _utc(tracking.due_at),
        "due_at_resolution": _utc(tracking.due_at_resolution),
        "current_tier": tracking.current_tier,
        "escalated_at": _utc(tracking.escalated_at),
        "extension_count": int(tracking.extension_count or 0),
        "quotations": quotations,
        # B5: the panel mounts the ticket conversation instead of the Respond button.
        "has_conversation": bool(tracking.respond_contact_id),
    }


def _update(db: Session, tracking_id: str, **fields) -> None:
    """The write the SLA resolve route makes: straight onto the tracker by id, so a blank event
    name or a changed team set on the step can never strand a task."""
    from app.schemas.sla import ConversationSLATrackingUpdate
    from app.services.sla_service import ConversationSLATrackingService

    ConversationSLATrackingService(db).update_tracking(
        str(tracking_id), ConversationSLATrackingUpdate(**fields)
    )


def respond(db: Session, tracking_id: str, user: dict) -> ConversationSLATracking:
    tracking = _tracker_for_actor(db, tracking_id, user)
    if tracking.is_resolved:
        raise AppException(status_code=409, message="This request is already resolved.", code="already_resolved")
    if tracking.is_responded:
        return tracking
    _update(db, tracking.id, is_responded=True, responded_by=str(user["id"]))
    db.refresh(tracking)
    return tracking


def resolve(db: Session, tracking_id: str, user: dict) -> ConversationSLATracking:
    tracking = _tracker_for_actor(db, tracking_id, user)
    # Read under a row lock held until the resolve commits: of two resolves in the same second
    # only one gets past here, so the requester's notice and the chat closing message go once.
    already = (
        db.query(ConversationSLATracking.is_resolved)
        .filter(ConversationSLATracking.id == str(tracking.id))
        .with_for_update()
        .scalar()
    )
    if already or tracking.is_resolved:
        _safe_rollback(db)
        raise AppException(status_code=409, message="This request is already resolved.", code="already_resolved")
    fields: Dict[str, Any] = {"is_resolved": True, "resolved_by": str(user["id"])}
    if not tracking.is_responded:
        fields.update(is_responded=True, responded_by=str(user["id"]))
    _update(db, tracking.id, **fields)
    db.refresh(tracking)
    _notify_requesters_resolved(db, tracking)
    if tracking.respond_contact_id:
        _close_like_a_chat_ticket(db, tracking)
    return tracking


def _close_like_a_chat_ticket(db: Session, tracking: ConversationSLATracking) -> None:
    """B6: what a chat resolve does after its commit, through the chat resolve's own helpers.
    The resolved message always; the Respond close (and n8n's close hook) only when no other
    open row shares the contact, by the chat resolve's own rule. Each helper is best-effort and
    never raises."""
    from app.services.sla_service import ConversationSLATrackingService

    try:
        service = ConversationSLATrackingService(db)
        service._enqueue_ticket_resolved_message_best_effort(tracking)
        if not service._contact_has_other_open_tickets(tracking):
            service._close_respond_conversation_best_effort(tracking)
            service._notify_close_convo_webhook_best_effort(tracking)
    except Exception as exc:  # noqa: BLE001 - the resolve already committed
        _safe_rollback(db)
        logger.warning("chat close for media request %s failed: %s", tracking.id, exc)


# ------------------------------------------------------------------------------ hand-off notices


def _safe_rollback(db: Session) -> None:
    """A failed notice must not leave the session in an aborted transaction for what follows."""
    try:
        db.rollback()
    except Exception:
        logger.warning("rollback after a failed drawing request notice also failed", exc_info=True)


def _base_url() -> str:
    from app.config import settings

    return (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")


def _product_code(db: Session, product_id: str) -> str:
    code = db.query(Product.product_code).filter(Product.id == str(product_id)).scalar()
    return code or "this product"


def _send(
    db: Session,
    *,
    user_id: str,
    tracker: ConversationSLATracking,
    title: str,
    body: str,
    path: str,
    code: str,
    event_type: str,
    dedup_key: Optional[str] = None,
    whatsapp: bool = True,
) -> None:
    """One notice on every channel the recipient allows. Best-effort, as `_notify_assignee` is:
    the work it announces has already committed. ``whatsapp=False`` keeps it to in-app and email
    (the requester's notices: their WhatsApp is the ticket conversation, Q5)."""
    from app.models.user import User
    from app.services.notification_service import NotificationService

    try:
        base = _base_url()
        link = f"{base}{path}"
        text = f"{body}\n\nOpen: {link}"
        recipient = db.query(User).filter(User.id == str(user_id)).first()
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%d/%m/%Y")
        NotificationService(db).create_with_channel_preferences(
            user_id=str(user_id),
            type="form_sla",
            title=title,
            body=text,
            data={
                "tracking_id": str(tracker.id),
                "source_entity_type": tracker.source_entity_type,
                "source_entity_id": tracker.source_entity_id,
                "link": path,
                "whatsapp_use_case": "sla_assignment",
                "whatsapp_text": text,
                "whatsapp_context_vars": {
                    "contact_name": (recipient.name or recipient.email or "there") if recipient else "there",
                    "entity_number": code,
                    "reason": "",
                    "respond_due_at": "",
                    "resolve_due_at": "",
                    "today_date": today,
                    "system_url": base,
                    "form_url": link,
                    "portal_url": link,
                    "message": text,
                },
            },
            source_entity_type="form_sla_tracking",
            source_entity_id=str(tracker.id),
            event_type=event_type,
            dedup_key=dedup_key,
            send_in_app=True,
            send_email=True,
            send_web_push=False,
            send_whatsapp=whatsapp,
            whatsapp_pref_attr="notify_whatsapp_on_assignment",
            email_pref_attr="notify_email_on_assignment",
        )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("drawing request notice %s for tracker %s failed: %s", event_type, tracker.id, exc)


def _notify_file_linked(db: Session, product_id: str, kind: str) -> None:
    """H3: a file of this kind was linked while requests for it are open. Tells the assignee of
    every open task of that kind for the product, once each; closes nothing."""
    noun = KIND_NOUN[kind]
    try:
        # Only for a product this session can see: a file linked by another company's user must
        # not prompt this company's assignee.
        if db.query(Product.id).filter(Product.id == str(product_id)).first() is None:
            return
        told: set = set()
        code = None
        for tracker in _open_trackers(db, str(product_id), SOURCE_TYPES[kind]):
            assignee = str(tracker.assigned_to_id) if tracker.assigned_to_id else None
            if assignee is None or assignee in told:
                continue
            told.add(assignee)
            code = code or _product_code(db, str(product_id))
            _send(
                db,
                user_id=assignee,
                tracker=tracker,
                title=f"{noun.capitalize()} added for {code}",
                body=f"A {noun} was added for {code}. Resolve the request when done.",
                path=f"/master-data-management/products/{product_id}",
                code=code,
                event_type=f"{noun}_added",
            )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("%s linked notice for product %s failed: %s", noun, product_id, exc)


def notify_drawing_linked(db: Session, product_id: str) -> None:
    _notify_file_linked(db, product_id, "drawing")


def notify_photo_linked(db: Session, product_id: str) -> None:
    _notify_file_linked(db, product_id, "photo")


def _requester_paths(db: Session, tracker: ConversationSLATracking) -> Dict[str, str]:
    """Per requester, the quotation page they escalated from (their earliest escalation)."""
    rows = (
        db.query(ConversationSLAEventLog.triggered_by_id, ConversationSLAEventLog.reason)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracker.id),
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
            ConversationSLAEventLog.triggered_by_id.isnot(None),
        )
        .order_by(ConversationSLAEventLog.event_at.asc(), ConversationSLAEventLog.id.asc())
        .all()
    )
    first_version: Dict[str, str] = {}
    for user_id, reason in rows:
        if str(user_id) not in first_version and (reason or "").startswith(_VERSION_REASON_PREFIX):
            first_version[str(user_id)] = reason[len(_VERSION_REASON_PREFIX):]
        else:
            first_version.setdefault(str(user_id), "")
    where = {
        str(vid): (str(project_id), str(quotation_id))
        for vid, quotation_id, project_id in db.query(
            ProjectQuotationVersion.id, ProjectQuotation.id, ProjectQuotation.project_id
        )
        .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationVersion.quotation_id)
        .filter(ProjectQuotationVersion.id.in_([v for v in first_version.values() if v]))
        .all()
    } if any(first_version.values()) else {}
    out: Dict[str, str] = {}
    for user_id, version_id in first_version.items():
        project_id, quotation_id = where.get(version_id, (None, None))
        out[user_id] = (
            f"/project-sales/{project_id}/quotations/{quotation_id}"
            if project_id
            else f"/master-data-management/products/{tracker.source_entity_id}"
        )
    return out


def _notify_requesters_resolved(db: Session, tracker: ConversationSLATracking) -> None:
    """H4: the requester hears the request is resolved, once, in-app and by email (never on
    WhatsApp: with a contact, the chat resolve message already tells them there, Q5)."""
    try:
        code = _product_code(db, str(tracker.source_entity_id))
        noun = "photo" if tracker.source_entity_type == SOURCE_TYPES["photo"] else "drawing"
        for user_id, path in _requester_paths(db, tracker).items():
            _send(
                db,
                user_id=user_id,
                tracker=tracker,
                title=f"Product {noun} request for {code} resolved",
                body=f"The {noun} request for {code} is resolved.",
                path=path,
                code=code,
                event_type="resolved",
                dedup_key=f"media_resolved:{tracker.id}",
                whatsapp=False,
            )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("drawing resolved notices for tracker %s failed: %s", tracker.id, exc)
