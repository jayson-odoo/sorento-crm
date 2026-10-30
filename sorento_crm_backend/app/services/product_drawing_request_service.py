"""A quotation line's missing technical drawing, escalated as a form-SLA task.

One task per PRODUCT (not per line, not per quotation): the first Escalate opens a
`product_drawing` task on the existing tracker table through the form-SLA orchestrator, using the
step an admin configured in SLA Management (access agent, team set, policy). Every later Escalate
while that task is open joins it as a requester, recorded as an event-log row. Nothing about the
receiving team lives here.

The team works the task the normal SLA way (Respond, Resolve). Adding a drawing does not close it:
it notifies the assignee. Resolving notifies every requester.

Hand-offs (plan rule 10) go through `NotificationService.create_with_channel_preferences`, the
call every form-SLA assignment uses: in-app always, email and WhatsApp each gated by the
recipient's own toggle and a linked WhatsApp contact.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, func, or_, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.projects import ProjectQuotation, ProjectQuotationLine, ProjectQuotationVersion
from app.models.resources import Attachment, AttachmentType
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    FormSLAConfig,
)
from app.services.error_handler import AppException, handle_not_found, handle_validation_error
from app.services.product_image_service import DRAWING_TYPE
from app.services.sla_scope import open_tracker_scope

logger = logging.getLogger(__name__)

SOURCE_TYPE = "product_drawing"
EVENT_ESCALATE = "escalate"
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


# ------------------------------------------------------------------------------ the cell state


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Tracker columns are naive UTC; the cell's clocks leave as aware UTC so a browser reads them right."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _open_tracker(db: Session, product_id: str) -> Optional[ConversationSLATracking]:
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == SOURCE_TYPE,
            ConversationSLATracking.source_entity_id == str(product_id),
            *open_tracker_scope(),
        )
        .order_by(ConversationSLATracking.initiated_at.desc())
        .first()
    )


def escalation_states(db: Session, product_ids: Iterable[Optional[str]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Per product id, the cell's escalation state, in a fixed number of queries.

    An open task reads its ids and clocks; with none open, a resolved one leaves only
    ``last_resolved_at``; a product never escalated reads None.
    """
    ids = list(dict.fromkeys(str(pid) for pid in product_ids if pid))
    if not ids:
        return {}

    # One read for the open task (with its requester count) and the resolved history: the
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
    open_rows: Dict[str, ConversationSLATracking] = {}
    counts: Dict[str, int] = {}
    resolved: Dict[str, datetime] = {}
    for tracker, requesters in (
        db.query(ConversationSLATracking, requester_count)
        .filter(
            ConversationSLATracking.source_entity_type == SOURCE_TYPE,
            ConversationSLATracking.source_entity_id.in_(ids),
            or_(
                and_(*open_tracker_scope()),
                and_(
                    ConversationSLATracking.is_resolved.is_(True),
                    ConversationSLATracking.resolved_at.isnot(None),
                ),
            ),
        )
        .order_by(ConversationSLATracking.initiated_at.desc())
        .all()
    ):
        key = str(tracker.source_entity_id)
        if tracker.is_resolved:
            if key not in resolved or tracker.resolved_at > resolved[key]:
                resolved[key] = tracker.resolved_at
        elif tracker.voided_at is None and key not in open_rows:
            open_rows[key] = tracker
            counts[str(tracker.id)] = int(requesters or 0)

    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for pid in ids:
        tracker = open_rows.get(pid)
        if tracker is not None:
            responded = bool(tracker.is_responded)
            out[pid] = {
                "tracking_id": str(tracker.id),
                "opened_at": _utc(tracker.initiated_at),
                "responded_at": _utc(tracker.responded_at or tracker.updated_at) if responded else None,
                "due_at": _utc(tracker.due_at_resolution or tracker.due_at) if responded else _utc(tracker.due_at),
                "requester_count": counts.get(str(tracker.id), 0),
                "last_resolved_at": _utc(resolved.get(pid)),
            }
        elif pid in resolved:
            out[pid] = {
                "tracking_id": None,
                "opened_at": None,
                "responded_at": None,
                "due_at": None,
                "requester_count": None,
                "last_resolved_at": _utc(resolved[pid]),
            }
        else:
            out[pid] = None
    return out


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


def _escalate_config(db: Session) -> Optional[FormSLAConfig]:
    """The active step whose start event includes `escalate`."""
    for config in (
        db.query(FormSLAConfig)
        .filter(FormSLAConfig.source_entity_type == SOURCE_TYPE, FormSLAConfig.is_active.is_(True))
        .order_by(FormSLAConfig.stage_code.asc())
        .all()
    ):
        if EVENT_ESCALATE in [t.strip() for t in str(config.start_event or "").split(",")]:
            return config
    return None


@contextmanager
def _product_lock(db: Session, product_id: str):
    """A session-level Postgres advisory lock keyed on the product, held across commits.

    A row lock would not do: assigning the task commits (the round-robin cursor), which would
    release it before the tracker exists. The lock lives on ONE connection and is released on
    that same connection. A pooled engine can hand the session a different connection after a
    commit, so the lock gets a connection of its own; a session bound to a single connection
    (a test's) uses that connection, which never changes.
    """
    key = {"k": f"{SOURCE_TYPE}:{product_id}"}
    bind = db.get_bind()
    owned = None if isinstance(bind, Connection) else bind.connect()
    conn = bind if owned is None else owned
    conn.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), key)
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


def escalate(db: Session, *, version_id: str, line_id: str, user: dict) -> Dict[str, Any]:
    """Open the product's drawing task, or join the open one. Returns ``{joined, escalation}``."""
    from app.services.form_sla_service import FormSLAOrchestrator
    from app.services.project_quotation_image_service import line_product_id

    line = _line_in_version(db, version_id, line_id)
    product_id = line_product_id(line)
    if not product_id:
        raise AppException(
            status_code=409,
            message="This line has no catalogue product to request a drawing for.",
            code="line_has_no_product",
        )
    # Through the scoped ORM: a product of a company the caller cannot see is not found, and
    # its company is the one the task is routed under.
    product = db.query(Product.id, Product.company_id).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(status_code=404, message="Product not found.", code="product_not_found")
    if has_drawing(db, product_id):
        raise AppException(
            status_code=409,
            message="This product already has a drawing.",
            code="product_has_drawing",
        )

    # Two clicks in the same second must open one task. "Is there an open task" is read then
    # write, so the product is locked from the check until the requester is recorded.
    with _product_lock(db, product_id):
        tracker = _open_tracker(db, product_id)
        joined = tracker is not None
        if tracker is None:
            config = _escalate_config(db)
            if config is None:
                db.rollback()
                raise _not_set_up()
            try:
                tracker = FormSLAOrchestrator(db)._start_for_config(
                    config, product_id, company_id=str(product.company_id) if product.company_id else None
                )
            except AppException as exc:
                db.rollback()
                if exc.status_code >= 500:
                    raise
                # The admin's setup problem, not the salesperson's: the detail names the agent
                # and the step, so it goes to the log and not to the screen.
                logger.warning("drawing request step is not usable: %s", exc.message)
                raise _not_set_up()
            except Exception:
                db.rollback()
                raise
            if tracker is None:
                db.rollback()
                raise _not_set_up()

        _record_requester(db, tracker, version_id=str(version_id), user_id=str(user["id"]))
        db.commit()
    return {"joined": joined, "escalation": escalation_states(db, [product_id])[str(product_id)]}


def _not_set_up() -> AppException:
    return AppException(
        status_code=409,
        message="No team is set up for drawing requests.",
        code="drawing_requests_not_set_up",
    )


def _record_requester(db: Session, tracker: ConversationSLATracking, *, version_id: str, user_id: str) -> None:
    """One event-log row per user per task, naming the quotation version they escalated from."""
    already = (
        db.query(ConversationSLAEventLog.id)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracker.id),
            ConversationSLAEventLog.event_type == REQUESTER_EVENT,
            ConversationSLAEventLog.triggered_by_id == user_id,
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
    if tracking.source_entity_type != SOURCE_TYPE:
        raise AppException(
            status_code=409,
            message="This task is not a drawing request.",
            code="not_a_drawing_request",
        )
    if not service.can_user_resolve_tracking(user["id"], tracking):
        raise handle_validation_error("This task is assigned to someone else, so you cannot act on it.")
    return tracking


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
    if tracking.is_resolved:
        raise AppException(status_code=409, message="This request is already resolved.", code="already_resolved")
    fields: Dict[str, Any] = {"is_resolved": True, "resolved_by": str(user["id"])}
    if not tracking.is_responded:
        fields.update(is_responded=True, responded_by=str(user["id"]))
    _update(db, tracking.id, **fields)
    db.refresh(tracking)
    _notify_requesters_resolved(db, tracking)
    return tracking


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
) -> None:
    """One notice on every channel the recipient allows. Best-effort, as `_notify_assignee` is:
    the work it announces has already committed."""
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
            send_whatsapp=True,
            whatsapp_pref_attr="notify_whatsapp_on_assignment",
            email_pref_attr="notify_email_on_assignment",
        )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("drawing request notice %s for tracker %s failed: %s", event_type, tracker.id, exc)


def notify_drawing_linked(db: Session, product_id: str) -> None:
    """H3: a drawing was linked while a request is open. Tells the assignee; closes nothing."""
    try:
        tracker = _open_tracker(db, str(product_id))
        if tracker is None or not tracker.assigned_to_id:
            return
        code = _product_code(db, str(product_id))
        _send(
            db,
            user_id=str(tracker.assigned_to_id),
            tracker=tracker,
            title=f"Drawing added for {code}",
            body=f"A drawing was added for {code}. Resolve the request when done.",
            path=f"/master-data-management/products/{product_id}",
            code=code,
            event_type="drawing_added",
        )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("drawing linked notice for product %s failed: %s", product_id, exc)


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
    """H4: every requester hears the request is resolved, once."""
    try:
        code = _product_code(db, str(tracker.source_entity_id))
        for user_id, path in _requester_paths(db, tracker).items():
            _send(
                db,
                user_id=user_id,
                tracker=tracker,
                title=f"Drawing request for {code} resolved",
                body=f"The drawing request for {code} is resolved.",
                path=path,
                code=code,
                event_type="resolved",
                dedup_key=f"drawing_resolved:{tracker.id}",
            )
    except Exception as exc:
        _safe_rollback(db)
        logger.warning("drawing resolved notices for tracker %s failed: %s", tracker.id, exc)
