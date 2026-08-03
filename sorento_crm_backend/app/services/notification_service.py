"""Notification service: create, list, mark read/archive/resolve, delete."""
import logging
import re
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import desc, and_, or_
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDelivery

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _split_entity_and_dedup(
    source_entity_id: Optional[str], dedup_key: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Derive (entity_uuid_or_none, dedup_scope) from the create args.

    `source_entity_id` used to carry two things at once: the entity a
    notification is about, AND the idempotency scope — which for batched /
    periodic notifications was a synthetic string with no entity behind it
    (`alert:...`, `digest:<date>`, `{type}_{batch}`). Now they are separate
    columns: `source_entity_id` is a uuid (or NULL), `dedup_key` is the scope.

    This keeps every caller working unchanged. The dedup scope defaults to the
    passed `source_entity_id`, so passing a uuid de-duplicates exactly as before
    and passing a synthetic string still de-duplicates on that string; only a
    real uuid survives into the `source_entity_id` column.
    """
    dedup = dedup_key if dedup_key is not None else source_entity_id
    entity = (
        source_entity_id
        if source_entity_id and _UUID_RE.match(str(source_entity_id))
        else None
    )
    return entity, dedup


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Optional[Notification]:
        """Create a notification. If idempotency keys are set and a matching notification exists, returns existing (no duplicate)."""
        # create() unconditionally fans out to all three channels on the new-row
        # path below; the idempotent branch ensures those same channels exist on
        # an already-present row. These locals were referenced there but never
        # defined — the branch NameError'd on every duplicate until now.
        send_in_app = send_email = send_web_push = True
        entity_id, dedup = _split_entity_and_dedup(source_entity_id, dedup_key)
        if source_entity_type and dedup and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.source_entity_type == source_entity_type,
                    Notification.dedup_key == dedup,
                    Notification.event_type == event_type,
                )
                .first()
            )
            if existing:
                # Idempotent record already exists; ensure requested channels exist on it.
                existing_deliveries = {
                    d.channel: d
                    for d in self.db.query(NotificationDelivery)
                    .filter(NotificationDelivery.notification_id == existing.id)
                    .all()
                }
                now = datetime.utcnow()
                created_pending_delivery = False
                if send_in_app and "in_app" not in existing_deliveries:
                    self.db.add(
                        NotificationDelivery(
                            notification_id=existing.id,
                            channel="in_app",
                            status="sent",
                            sent_at=now,
                        )
                    )
                if send_email and "email" not in existing_deliveries:
                    self.db.add(
                        NotificationDelivery(
                            notification_id=existing.id,
                            channel="email",
                            status="pending",
                        )
                    )
                    created_pending_delivery = True
                if send_web_push and "web_push" not in existing_deliveries:
                    self.db.add(
                        NotificationDelivery(
                            notification_id=existing.id,
                            channel="web_push",
                            status="pending",
                        )
                    )
                    created_pending_delivery = True
                if created_pending_delivery:
                    self.db.commit()
                    try:
                        from app.services.queue_service import enqueue_job
                        from app.tasks import notification_tasks

                        enqueue_job(
                            notification_tasks.send_notification_deliveries,
                            str(existing.id),
                            queue_name="notifications",
                        )
                    except Exception as e:
                        logger.warning("Failed to enqueue notification deliveries: %s", e)
                return existing
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            data=data or {},
            source_entity_type=source_entity_type,
            source_entity_id=entity_id,
            dedup_key=dedup,
            event_type=event_type,
        )
        self.db.add(notification)
        self.db.flush()
        # In-app delivery record (always created)
        self.db.add(NotificationDelivery(
            notification_id=notification.id,
            channel="in_app",
            status="sent",
            sent_at=datetime.utcnow(),
        ))
        # Pending deliveries for async send (email, web_push)
        self.db.add(NotificationDelivery(
            notification_id=notification.id,
            channel="email",
            status="pending",
        ))
        self.db.add(NotificationDelivery(
            notification_id=notification.id,
            channel="web_push",
            status="pending",
        ))
        self.db.commit()
        self.db.refresh(notification)
        try:
            from app.services.queue_service import enqueue_job
            from app.tasks import notification_tasks
            enqueue_job(
                notification_tasks.send_notification_deliveries,
                str(notification.id),
                queue_name="notifications",
            )
        except Exception as e:
            logger.warning("Failed to enqueue notification deliveries: %s", e)
        return notification

    def create_in_app_only(
        self,
        user_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Optional[Notification]:
        """Create a notification with in-app delivery only (no email or web_push). Used when sending one email to many recipients."""
        entity_id, dedup = _split_entity_and_dedup(source_entity_id, dedup_key)
        if source_entity_type and dedup and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.source_entity_type == source_entity_type,
                    Notification.dedup_key == dedup,
                    Notification.event_type == event_type,
                )
                .first()
            )
            if existing:
                return existing
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            data={},
            source_entity_type=source_entity_type,
            source_entity_id=entity_id,
            dedup_key=dedup,
            event_type=event_type,
        )
        self.db.add(notification)
        self.db.flush()
        self.db.add(NotificationDelivery(
            notification_id=notification.id,
            channel="in_app",
            status="sent",
            sent_at=datetime.utcnow(),
        ))
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def create_with_channel_preferences(
        self,
        user_id: Optional[str] = None,
        *,
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
        event_type: Optional[str] = None,
        send_in_app: bool = True,
        send_email: bool = True,
        send_web_push: bool = False,
        send_whatsapp: bool = False,
        whatsapp_pref_attr: str = "notify_whatsapp",
        email_pref_attr: Optional[str] = None,
        respond_contact_id: Optional[str] = None,
        enqueue_delivery: bool = True,
    ) -> Optional[Notification]:
        """
        Create notification and only create deliveries for selected channels.
        Enqueues async processing when email/web_push/whatsapp deliveries are pending.

        send_whatsapp is "this event is WhatsApp-eligible" (escalation / assignment,
        TCK-29). A whatsapp delivery is created ONLY when the recipient also has
        notify_whatsapp on AND a resolvable RespondContact — otherwise it is skipped
        silently so other channels still fire.

        **Two kinds of recipient, one function** (AC-H2). Pass ``user_id`` for staff or
        ``respond_contact_id`` for a customer, never both and never neither: a second
        ``create_for_contact()`` is how the dedupe rules drift apart, and a row
        addressed to two people fans out to whichever one the reader happens to pick.

        A CONTACT gets ``whatsapp`` + ``in_app``, always (AC-H3), where ``in_app`` IS
        the portal record they read through the portal link. The per-user preference
        attributes are ignored outright rather than defaulted: they read a ``users``
        row that does not exist for a contact, so the lookup resolves to None and
        turns WhatsApp OFF — the exact opposite of what AC-H3 asks for (AC-H3a).

        ``enqueue_delivery=False`` records the notification and its delivery rows but
        does not hand them to the worker; the caller is sending synchronously and will
        settle the delivery rows itself (``workflow_submission_notify``).
        """
        if bool(user_id) == bool(respond_contact_id):
            raise ValueError(
                "Exactly one of user_id / respond_contact_id must be set: a "
                "notification addressed to nobody is undeliverable, and one addressed "
                "to both fans out to two different people."
            )

        if respond_contact_id:
            return self._create_for_contact(
                respond_contact_id=respond_contact_id,
                type=type,
                title=title,
                body=body,
                data=data,
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id,
                dedup_key=dedup_key,
                event_type=event_type,
                enqueue_delivery=enqueue_delivery,
            )

        # Gate WhatsApp on the recipient's opt-in + reachability.
        if send_whatsapp:
            from app.models.user import User as _User
            from app.services.respond_link_service import resolve_user_respond_io_id

            _user = self.db.query(_User).filter(_User.id == user_id).first()
            send_whatsapp = bool(
                _user
                and getattr(_user, whatsapp_pref_attr, False)
                and resolve_user_respond_io_id(self.db, _user)
            )
        # Gate email on a per-event user opt-in when the caller supplies the pref
        # attr (SLA assign/escalate). Default (None) keeps email unconditional for
        # every other caller.
        if send_email and email_pref_attr:
            from app.models.user import User as _UserE

            _ue = self.db.query(_UserE).filter(_UserE.id == user_id).first()
            send_email = bool(_ue and getattr(_ue, email_pref_attr, True))
        # Web push mirrors in-app for users with an active subscription (TCK-33).
        # The browser subscription IS the opt-in — no separate pref column.
        # Best-effort: a lookup failure (e.g. table absent in a partial test DB)
        # must never block the notification.
        if send_in_app and not send_web_push:
            try:
                from app.models.notification import PushSubscription

                has_sub = (
                    self.db.query(PushSubscription.id)
                    .filter(PushSubscription.user_id == user_id)
                    .first()
                    is not None
                )
                if has_sub:
                    send_web_push = True
            except Exception:
                self.db.rollback()
        if not send_in_app and not send_email and not send_web_push and not send_whatsapp:
            raise ValueError("At least one delivery channel must be enabled")
        entity_id, dedup = _split_entity_and_dedup(source_entity_id, dedup_key)
        if source_entity_type and dedup and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.source_entity_type == source_entity_type,
                    Notification.dedup_key == dedup,
                    Notification.event_type == event_type,
                )
                .first()
            )
            if existing:
                return existing
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            data=data or {},
            source_entity_type=source_entity_type,
            source_entity_id=entity_id,
            dedup_key=dedup,
            event_type=event_type,
        )
        self.db.add(notification)
        self.db.flush()
        now = datetime.utcnow()
        if send_in_app:
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="in_app",
                    status="sent",
                    sent_at=now,
                )
            )
        if send_email:
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="email",
                    status="pending",
                )
            )
        if send_web_push:
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="web_push",
                    status="pending",
                )
            )
        if send_whatsapp:
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="whatsapp",
                    status="pending",
                )
            )
        self.db.commit()
        self.db.refresh(notification)
        if enqueue_delivery and (send_email or send_web_push or send_whatsapp):
            self._enqueue_deliveries(notification)
        return notification

    def _create_for_contact(
        self,
        *,
        respond_contact_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
        event_type: Optional[str] = None,
        enqueue_delivery: bool = True,
    ) -> Optional[Notification]:
        """The contact half of the spine (AC-H3). WhatsApp plus the portal, always.

        No email and no web push: both address a staff surface a contact cannot reach.
        No preference lookup either — see the caller's docstring for why reading one
        silently disables the only channel that matters.

        WhatsApp is created only when the contact actually has an address. A contact
        synced without a ``respond_io_id`` still gets the ``in_app`` row, because that
        IS what they see when they next open their portal link; a pending whatsapp
        delivery for an unaddressable contact would sit failed forever and pollute the
        outbox with a send that was never possible.
        """
        from app.models.access import RespondContact

        contact = (
            self.db.query(RespondContact)
            .filter(RespondContact.id == str(respond_contact_id))
            .first()
        )
        if contact is None:
            raise ValueError(
                f"No respond_contacts row {respond_contact_id}; a notification "
                "addressed to an unknown contact reaches nobody."
            )
        send_whatsapp = bool(str(getattr(contact, "respond_io_id", "") or "").strip())

        entity_id, dedup = _split_entity_and_dedup(source_entity_id, dedup_key)
        if source_entity_type and dedup and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.respond_contact_id == str(respond_contact_id),
                    Notification.source_entity_type == source_entity_type,
                    Notification.dedup_key == dedup,
                    Notification.event_type == event_type,
                )
                .first()
            )
            if existing:
                # The partial unique index is the backstop; resolving here is what
                # stops a post-commit side effect handing its caller an
                # IntegrityError for a message that was already delivered.
                return existing

        notification = Notification(
            user_id=None,
            respond_contact_id=str(respond_contact_id),
            type=type,
            title=title,
            body=body,
            data=data or {},
            source_entity_type=source_entity_type,
            source_entity_id=entity_id,
            dedup_key=dedup,
            event_type=event_type,
        )
        self.db.add(notification)
        self.db.flush()
        self.db.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel="in_app",
                status="sent",
                sent_at=datetime.utcnow(),
            )
        )
        if send_whatsapp:
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="whatsapp",
                    status="pending",
                )
            )
        self.db.commit()
        self.db.refresh(notification)
        if enqueue_delivery and send_whatsapp:
            # The respond_io queue, NOT notifications. `notifications` is drained on a
            # daemon thread inside the API process so a logged-in user does not wait a
            # scheduler heartbeat for their bell; a customer's WhatsApp message has no
            # such interactive requirement, and the RQ worker is already the documented
            # owner of every Respond.io send. Keeping it there also keeps an outbound
            # customer message off a thread that shares uvicorn's connection pool.
            self._enqueue_deliveries(notification, queue_name="respond_io")
        return notification

    def _enqueue_deliveries(
        self, notification: Notification, queue_name: str = "notifications"
    ) -> None:
        """Hand the pending deliveries to the worker. Never raises: the thing the
        notification is about has already committed."""
        try:
            from app.services.queue_service import enqueue_job
            from app.tasks import notification_tasks

            enqueue_job(
                notification_tasks.send_notification_deliveries,
                str(notification.id),
                queue_name=queue_name,
            )
        except Exception as e:
            logger.warning("Failed to enqueue notification deliveries: %s", e)

    def list(
        self,
        user_id: str,
        tab: Optional[str] = None,
        status: Optional[str] = None,
        type_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Notification], int]:
        """List notifications for user. tab: 'all' | 'inbox' (unarchived) | 'archived'. status: 'read' | 'unread'."""
        q = self.db.query(Notification).filter(Notification.user_id == user_id)
        if tab == "archived":
            q = q.filter(Notification.archived_at.isnot(None))
        elif tab == "inbox" or tab is None:
            q = q.filter(Notification.archived_at.is_(None))
        if status == "read":
            q = q.filter(Notification.read_at.isnot(None))
        elif status == "unread":
            q = q.filter(Notification.read_at.is_(None))
        if type_filter:
            q = q.filter(Notification.type == type_filter)
        q = q.order_by(desc(Notification.created_at))
        total = q.count()
        offset = (page - 1) * limit
        items = q.offset(offset).limit(limit).all()
        return items, total

    def unread_count(self, user_id: str, include_archived: bool = False) -> int:
        q = self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        if not include_archived:
            q = q.filter(Notification.archived_at.is_(None))
        return q.count()

    def get(self, notification_id: str, user_id: str) -> Optional[Notification]:
        return (
            self.db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )

    def mark_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        n = self.get(notification_id, user_id)
        if n and not n.read_at:
            n.read_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(n)
        return n

    def mark_unread(self, notification_id: str, user_id: str) -> Optional[Notification]:
        """Clear read_at so notification appears unread again."""
        n = self.get(notification_id, user_id)
        if n and n.read_at:
            n.read_at = None
            self.db.commit()
            self.db.refresh(n)
        return n

    def mark_all_read(self, user_id: str, archived: Optional[bool] = None) -> int:
        q = self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        if archived is False:
            q = q.filter(Notification.archived_at.is_(None))
        elif archived is True:
            q = q.filter(Notification.archived_at.isnot(None))
        count = q.update({Notification.read_at: datetime.utcnow()}, synchronize_session=False)
        self.db.commit()
        return count

    def archive(self, notification_id: str, user_id: str) -> Optional[Notification]:
        n = self.get(notification_id, user_id)
        if n and not n.archived_at:
            n.archived_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(n)
        return n

    def archive_all(self, user_id: str) -> int:
        count = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.archived_at.is_(None),
            )
            .update({Notification.archived_at: datetime.utcnow()}, synchronize_session=False)
        )
        self.db.commit()
        return count

    def resolve(self, notification_id: str, user_id: str) -> Optional[Notification]:
        n = self.get(notification_id, user_id)
        if n and not n.resolved_at:
            n.resolved_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(n)
        return n

    def delete(self, notification_id: str, user_id: str) -> bool:
        """Permanently remove a notification (cascades to notification_deliveries)."""
        n = self.get(notification_id, user_id)
        if not n:
            return False
        self.db.delete(n)
        self.db.commit()
        return True

    def delete_many(self, notification_ids: List[str], user_id: str) -> int:
        """Permanently remove notifications that belong to the user. Returns rows deleted."""
        if not notification_ids:
            return 0
        deleted = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.id.in_(notification_ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def delete_all(self, user_id: str) -> int:
        """Permanently remove all notifications for the user."""
        deleted = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def record_delivery(
        self,
        notification_id: str,
        channel: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        delivery = NotificationDelivery(
            notification_id=notification_id,
            channel=channel,
            status=status,
            sent_at=datetime.utcnow() if status == "sent" else None,
            error_message=error_message,
        )
        self.db.add(delivery)
        self.db.commit()
