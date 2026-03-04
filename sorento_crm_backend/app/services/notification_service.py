"""Notification service: create, list, mark read/archive/resolve."""
import logging
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import desc, and_, or_
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDelivery

logger = logging.getLogger(__name__)


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
        event_type: Optional[str] = None,
    ) -> Optional[Notification]:
        """Create a notification. If idempotency keys are set and a matching notification exists, returns existing (no duplicate)."""
        if source_entity_type and source_entity_id and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.source_entity_type == source_entity_type,
                    Notification.source_entity_id == source_entity_id,
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
            source_entity_id=source_entity_id,
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
                queue_name="imports",
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
        event_type: Optional[str] = None,
    ) -> Optional[Notification]:
        """Create a notification with in-app delivery only (no email or web_push). Used when sending one email to many recipients."""
        if source_entity_type and source_entity_id and event_type:
            existing = (
                self.db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.source_entity_type == source_entity_type,
                    Notification.source_entity_id == source_entity_id,
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
            source_entity_id=source_entity_id,
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
