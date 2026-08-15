"""Internal ticket comments: create, list, mirror out, ingest in (UAC AC-L1/L2/L3).

The CRM database is the source of truth. Respond.io can create a comment but
has no read-back endpoint, so the mirror in AC-L2 is a courtesy to staff still
working in the Respond inbox, never a second store we read from.

Scope rules (they are the reason `tracking_id` is nullable):

- a CRM comment belongs to ONE ticket and to the contact behind it;
- a Respond-ingested comment belongs to the CONTACT only, because Respond's own
  comments are contact-scoped - so it renders in every open ticket for that
  contact.
"""
from __future__ import annotations

import logging
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.sla import ConversationSLATracking
from app.models.ticket_comment import (
    COMMENT_SOURCE_CRM,
    COMMENT_SOURCE_RESPOND,
    ConversationTicketComment,
)
from app.models.user import User
from app.schemas.ticket_comment import TicketCommentResponse
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- names


def _display_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    return (getattr(user, "name", None) or getattr(user, "email", None) or "").strip() or None


def _users_by_id(db: Session, user_ids: Iterable[str]) -> dict[str, User]:
    ids = [str(u) for u in user_ids if u]
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {str(u.id): u for u in rows}


def _is_crm_user_uuid(value: str) -> bool:
    """True when the stored `respond_user_id` is actually a CRM users.id.

    Some rows were filled with the CRM uuid, which is NOT a Respond user id -
    same trap `crm_chat_outbound_webhook.resolve_sender_respond_user_id` guards.
    A mention resolved from one of those would render a broken token in Respond.
    """
    s = str(value).strip()
    if len(s) != 36:
        return False
    try:
        uuid_module.UUID(s)
        return True
    except ValueError:
        return False


def build_mirror_text(db: Session, body: str, mentioned_user_ids: list[str]) -> str:
    """The comment text as Respond should receive it (AC-L2).

    Mentioned users that HAVE a usable Respond mapping become
    ``{{@user.<respond_user_id>}}`` so the Respond inbox notifies the real
    person; everyone else keeps the plain "@Name" the author typed. Longest
    name first so "@Team Lead" is not half-consumed by a "@Team" that also
    exists.
    """
    users = _users_by_id(db, mentioned_user_ids)
    replacements: list[tuple[str, str]] = []
    for uid in mentioned_user_ids or []:
        user = users.get(str(uid))
        name = _display_name(user)
        if not name:
            continue
        respond_id = str(getattr(user, "respond_user_id", None) or "").strip()
        if not respond_id or _is_crm_user_uuid(respond_id):
            continue
        replacements.append((f"@{name}", "{{@user." + respond_id + "}}"))
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    text = body or ""
    for needle, token in replacements:
        text = text.replace(needle, token)
    return text


# -------------------------------------------------------------------- mirror


def mirror_comment_to_respond(
    db: Session,
    comment: ConversationTicketComment,
    *,
    identifier: Optional[str],
    client=None,
) -> bool:
    """Best-effort mirror of a committed CRM comment to Respond.io (AC-L2).

    Post-commit and never raising: the comment is already saved, so a mirror
    failure is a logged outbox row, not a 500 for work that succeeded. Every
    Respond call leaves an ``integration_log`` on success AND failure (repo
    rule) - local dev runs with deliberately-wrong credentials, so a 401'd
    mirror still has to be readable from the Respond outbox.
    """
    from app.services.integration_service import RespondClient, log_respond_send

    ident = (identifier or "").strip()
    if not ident:
        # Nothing to mirror to. Not a failure, and not outbox-worthy: no call
        # was attempted.
        return False

    text = build_mirror_text(db, comment.body or "", list(comment.mentioned_user_ids or []))
    endpoint = f"https://api.respond.io/v2/contact/id:{ident}/comment"
    payload = {"text": text}
    api = client if client is not None else RespondClient.for_identifier(db, ident)
    try:
        response = api.create_comment(ident, text)
    except Exception as exc:  # noqa: BLE001 - the comment itself already committed
        logger.warning("Respond comment mirror failed for %s: %s", comment.id, exc)
        log_respond_send(
            db,
            business_table="conversation_ticket_comments",
            business_id=str(comment.id),
            identifier=ident,
            request_payload=payload,
            exc=exc,
            endpoint=endpoint,
        )
        return False

    log_respond_send(
        db,
        business_table="conversation_ticket_comments",
        business_id=str(comment.id),
        identifier=ident,
        request_payload=payload,
        response=response,
        endpoint=endpoint,
    )
    try:
        comment.respond_mirrored = True
        db.commit()
    except Exception:  # noqa: BLE001 - a flag, not the comment
        db.rollback()
        logger.warning("Could not stamp respond_mirrored on comment %s", comment.id)
    return True


# ------------------------------------------------------------------- service


class TicketCommentService:
    def __init__(self, db: Session):
        self.db = db

    # -- reads ------------------------------------------------------------

    def _tracking_in_scope(self, tracking_id: str, viewer_user_id: str):
        """The ticket, or a 404 - for a missing row AND for a viewer outside its
        scope. Never a 403: that would confirm the ticket exists (same rule as
        `get_ticket_detail`)."""
        from app.services.form_sla_service import FORM_SLA_TYPES
        from app.services.sla_service import ConversationSLATrackingService

        service = ConversationSLATrackingService(self.db)
        tracking = service.get_tracking(tracking_id, load_event_logs=False)
        if not tracking or getattr(tracking, "source_entity_type", None) in FORM_SLA_TYPES:
            raise handle_not_found("Conversation SLA tracking", tracking_id)
        if not service.can_user_act_on_tracking(viewer_user_id, tracking):
            raise handle_not_found("Conversation SLA tracking", tracking_id)
        return tracking

    def _list(self, *scope) -> list[TicketCommentResponse]:
        """Serialize whatever the given scope selects, oldest first.

        The one render order (AC-L1) and the one serializer, shared by the
        ticket-keyed and contact-keyed lists so the two cannot drift.
        """
        rows = (
            self.db.query(ConversationTicketComment)
            .filter(*scope)
            .order_by(
                ConversationTicketComment.created_at.asc(),
                ConversationTicketComment.id.asc(),
            )
            .all()
        )
        return [self.serialize(row) for row in rows]

    def list_for_tracking(
        self, tracking_id: str, *, viewer_user_id: str
    ) -> list[TicketCommentResponse]:
        """This ticket's own comments PLUS the contact-level ones ingested from
        Respond, oldest first (AC-L1 render order, AC-L3 scope)."""
        tracking = self._tracking_in_scope(tracking_id, viewer_user_id)
        contact_id = getattr(tracking, "respond_contact_id", None)
        scope = [ConversationTicketComment.tracking_id == str(tracking.id)]
        if contact_id:
            scope.append(
                ConversationTicketComment.respond_contact_id == str(contact_id)
            )
        return self._list(
            or_(*scope),
            # A sibling ticket's CRM note belongs to that ticket, not here.
            or_(
                ConversationTicketComment.tracking_id == str(tracking.id),
                ConversationTicketComment.tracking_id.is_(None),
            ),
        )

    def list_for_contact(self, contact_ref: str) -> list[TicketCommentResponse]:
        """Every internal note about a CONTACT, oldest first (AC-N3).

        Wider than ``list_for_tracking`` on purpose: the inbox thread is not
        looking at one ticket, and a note is internal staff context rather than
        ticket-private, so a sibling ticket's note renders here too. Read
        access is the caller's ``sla_management.conversations.view`` permission,
        checked at the route - there is no assignment to check against.

        The gate is a permission, so this method authorises nothing: never call
        it from a surface that has not already required that permission.
        """
        from app.services.sla_service import (
            ConversationSLATrackingService,
            conversation_tracking_scope,
        )

        contact = ConversationSLATrackingService(self.db).require_contact(contact_ref)
        contact_pk = str(contact.id)
        tickets_for_contact = (
            self.db.query(ConversationSLATracking.id)
            .filter(
                ConversationSLATracking.respond_contact_id == contact_pk,
                conversation_tracking_scope(),
            )
            .scalar_subquery()
        )
        return self._list(
            or_(
                ConversationTicketComment.respond_contact_id == contact_pk,
                ConversationTicketComment.tracking_id.in_(tickets_for_contact),
            )
        )

    def serialize(self, comment: ConversationTicketComment) -> TicketCommentResponse:
        names = [
            name
            for name in (
                _display_name(user)
                for user in _users_by_id(
                    self.db, list(comment.mentioned_user_ids or [])
                ).values()
            )
            if name
        ]
        names.sort()
        return TicketCommentResponse(
            id=str(comment.id),
            tracking_id=str(comment.tracking_id) if comment.tracking_id else None,
            body=comment.body,
            author_name=comment.author_name,
            mentioned_names=names,
            source=comment.source or COMMENT_SOURCE_CRM,
            created_at=comment.created_at,
        )

    # -- writes -----------------------------------------------------------

    def create_comment(
        self,
        tracking_id: str,
        *,
        author_user_id: str,
        body: str,
        mentioned_user_ids: list[str],
    ) -> TicketCommentResponse:
        """Write an internal note on a ticket (AC-L1).

        Nothing here touches a Respond SEND path: a comment is never delivered
        to the contact. The only outbound call is the AC-L2 comment mirror,
        which runs post-commit and best-effort.
        """
        tracking = self._tracking_in_scope(tracking_id, author_user_id)

        mentions = [str(uid).strip() for uid in (mentioned_user_ids or []) if str(uid).strip()]
        known = _users_by_id(self.db, mentions)
        unknown = [uid for uid in mentions if uid not in known]
        if unknown:
            raise handle_validation_error(
                "One or more mentioned users no longer exist. Remove them and try again."
            )

        author = self.db.query(User).filter(User.id == str(author_user_id)).first()
        comment = ConversationTicketComment(
            id=str(uuid_module.uuid4()),
            tracking_id=str(tracking.id),
            respond_contact_id=(
                str(tracking.respond_contact_id)
                if getattr(tracking, "respond_contact_id", None)
                else None
            ),
            author_id=str(author_user_id) if author else None,
            author_name=_display_name(author),
            body=body.strip(),
            mentioned_user_ids=mentions,
            source=COMMENT_SOURCE_CRM,
        )
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)

        # Everything below is post-commit: warn and carry on, never raise.
        self._notify_mentions(comment, tracking, author_user_id=str(author_user_id))
        self._mirror(comment, tracking)
        self._publish(tracking)
        return self.serialize(comment)

    def _existing_ingested_comment(
        self, respond_comment_id: str
    ) -> Optional[ConversationTicketComment]:
        return (
            self.db.query(ConversationTicketComment)
            .filter(ConversationTicketComment.respond_comment_id == respond_comment_id)
            .first()
        )

    def ingest_respond_comment(
        self,
        *,
        contact: RespondContact,
        body: str,
        respond_comment_id: str,
        author_respond_user_id: Optional[str],
        author_name: Optional[str],
        created_at_ms: Optional[int],
    ) -> tuple[ConversationTicketComment, bool]:
        """Store a comment made in Respond's own inbox (AC-L3).

        Contact-scoped by construction: no ``tracking_id``, so it renders in
        every open ticket drawer for this contact. Returns
        ``(comment, already_existed)`` - a replayed ``comment.created`` webhook
        resolves to the row it already created rather than duplicating it.

        ``respond_comment_id`` is required (the route refuses a payload without
        one): it is the only thing that makes a replay recognisable, and a note
        cannot be un-duplicated once it is in front of everyone.

        The read-then-insert below RACES - two lanes forwarding the same event
        can both find nothing - so the insert is also guarded by the unique
        index. The loser re-reads the winner's row and reports a duplicate,
        which is what it truthfully is, instead of a 500 the forwarder retries
        forever.
        """
        existing = self._existing_ingested_comment(respond_comment_id)
        if existing:
            return existing, True

        created_at = None
        if created_at_ms and int(created_at_ms) > 0:
            created_at = datetime.fromtimestamp(
                int(created_at_ms) / 1000, tz=timezone.utc
            ).replace(tzinfo=None)

        comment = ConversationTicketComment(
            id=str(uuid_module.uuid4()),
            tracking_id=None,
            respond_contact_id=str(contact.id),
            author_id=None,
            author_name=(author_name or "").strip() or None,
            author_respond_user_id=(author_respond_user_id or "").strip() or None,
            body=body.strip(),
            mentioned_user_ids=[],
            source=COMMENT_SOURCE_RESPOND,
            respond_comment_id=respond_comment_id,
            respond_mirrored=True,
        )
        if created_at is not None:
            comment.created_at = created_at
        self.db.add(comment)
        try:
            self.db.commit()
        except IntegrityError:
            # Lost the race with the other lane: the unique index on
            # respond_comment_id is the real dedupe, the SELECT above is only
            # the cheap path. Rolling back and re-reading turns a 500 the
            # forwarder retries forever into the honest "duplicate".
            self.db.rollback()
            winner = self._existing_ingested_comment(respond_comment_id)
            if winner is None:
                raise
            return winner, True
        self.db.refresh(comment)
        return comment, False

    # -- post-commit side effects ------------------------------------------

    def _notify_mentions(
        self,
        comment: ConversationTicketComment,
        tracking: ConversationSLATracking,
        *,
        author_user_id: str,
    ) -> None:
        """In-app notification with a deep link, one per mentioned user (AC-L1).

        In-app lane only per the AC (no email, no WhatsApp); the notification
        service still mirrors in-app to web push for users who subscribed their
        browser, which IS the in-app lane's delivery. Best-effort: the comment
        is committed, so a notification failure must not fail the save.
        """
        try:
            recipients = [
                uid
                for uid in (comment.mentioned_user_ids or [])
                if str(uid) != str(author_user_id)
            ]
            if not recipients:
                return
            from app.config import settings
            from app.services.notification_service import NotificationService

            base_url = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
            # Same deep link as the assignment notify: the dashboard with this
            # ticket targeted, which is where the drawer opens.
            link = f"{base_url}/?ticket={tracking.id}" if base_url else f"/?ticket={tracking.id}"
            author = comment.author_name or "A teammate"
            contact_name = (
                getattr(getattr(tracking, "contact", None), "name", None) or "a contact"
            )
            title = f"{author} mentioned you in a note"
            body = f"{comment.body}\n\nOn the enquiry from {contact_name}.\n\nOpen: {link}"
            service = NotificationService(self.db)
            for user_id in recipients:
                service.create_with_channel_preferences(
                    user_id=str(user_id),
                    type="conversation_ticket_comment",
                    title=title,
                    body=body,
                    data={
                        "tracking_id": str(tracking.id),
                        "comment_id": str(comment.id),
                        "url": link,
                    },
                    source_entity_type="conversation_sla_tracking",
                    source_entity_id=str(tracking.id),
                    # Per comment, so a second mention of the same person on the
                    # same ticket is a second notification, not a stale dedupe.
                    event_type=f"comment_mention:{comment.id}",
                    send_in_app=True,
                    send_email=False,
                    send_whatsapp=False,
                )
        except Exception as exc:  # noqa: BLE001 - the comment already committed
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.warning(
                "mention notify failed for comment %s: %s", getattr(comment, "id", "?"), exc
            )

    def _mirror(
        self, comment: ConversationTicketComment, tracking: ConversationSLATracking
    ) -> None:
        contact = getattr(tracking, "contact", None)
        identifier = str(getattr(contact, "respond_io_id", "") or "").strip() or None
        try:
            mirror_comment_to_respond(self.db, comment, identifier=identifier)
        except Exception as exc:  # noqa: BLE001 - belt and braces; it never raises
            logger.warning("Respond comment mirror raised for %s: %s", comment.id, exc)

    def _publish(self, tracking: ConversationSLATracking) -> None:
        """Poke the live-thread stream so other open drawers on this contact pick
        the note up without waiting for their slow poll (AC-K1 channel)."""
        try:
            from app.services import conversation_event_bus

            contact = getattr(tracking, "contact", None)
            identifier = str(getattr(contact, "respond_io_id", "") or "").strip()
            if identifier:
                conversation_event_bus.publish(
                    conversation_event_bus.EVENT_MESSAGE, contact_id=identifier
                )
        except Exception:  # noqa: BLE001 - liveness only
            logger.debug("comment event publish failed", exc_info=True)
