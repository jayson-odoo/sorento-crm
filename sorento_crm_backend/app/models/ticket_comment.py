"""Internal comments on a conversation intervention ticket (UAC AC-L1/L2/L3).

The CRM database is the source of truth: Respond.io can CREATE a comment but
offers no read-back endpoint, so nothing here can be re-derived from Respond.

Two shapes live in this one table, discriminated by ``source``:

- ``crm``   - written from the ticket drawer. Carries BOTH ``tracking_id``
                (the ticket it was written on) and ``respond_contact_id``.
- ``respond`` - ingested from a ``comment.created`` webhook via n8n. Respond
                comments are CONTACT-scoped, not ticket-scoped, so these carry
                the contact only (``tracking_id`` NULL) and render in EVERY
                open ticket drawer for that contact.

Comments are deliberately NOT written into ``chat_histories``: that table is
the message mirror (and the in-thread search substrate), and an internal note
is not a message. The drawer merges the two streams at render time.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

COMMENT_SOURCE_CRM = "crm"
COMMENT_SOURCE_RESPOND = "respond"


class ConversationTicketComment(Base):
    __tablename__ = "conversation_ticket_comments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # NULL for a Respond-ingested comment: it belongs to the contact, not to one
    # ticket. CASCADE because a deleted ticket's own notes have nowhere to live.
    tracking_id = Column(
        UUID(as_uuid=False),
        ForeignKey("conversation_sla_tracking.id", ondelete="CASCADE"),
        nullable=True,
    )
    respond_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=True
    )
    # The CRM author. NULL for a Respond-ingested comment (the author is a
    # Respond space user, who may have no CRM account at all).
    author_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Display name captured at write time: a Respond-side author has no CRM row
    # to resolve, and a CRM author's name must survive the account being deleted.
    author_name = Column(Text, nullable=True)
    author_respond_user_id = Column(Text, nullable=True)
    body = Column(Text, nullable=False)
    # CRM users.id is a varchar, so this is text[] rather than uuid[]. The body
    # keeps the readable "@Display Name" inline; these ids are what the mention
    # notification and the Respond mirror's {{@user.<id>}} tokens resolve from.
    mentioned_user_ids = Column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"), default=list
    )
    source = Column(String(16), nullable=False, server_default=COMMENT_SOURCE_CRM)
    # Respond's own comment id. Present on ingested rows and the dedupe key for
    # a replayed webhook; NULL for CRM-authored rows (Respond returns no id we
    # can trust on create).
    respond_comment_id = Column(Text, nullable=True)
    respond_mirrored = Column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # Python-side default, not just the server one: `now()` is TRANSACTION time,
    # so several comments written inside one transaction would share a timestamp
    # and the "oldest first" thread order would fall back to a random uuid tie
    # break. `utcnow()` stamps the actual write instant, and naive UTC matches
    # every other datetime column here.
    created_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        default=datetime.utcnow,
        nullable=False,
    )

    tracking = relationship("ConversationSLATracking")
    author = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        CheckConstraint(
            "tracking_id IS NOT NULL OR respond_contact_id IS NOT NULL",
            name="ck_conversation_ticket_comments_scope",
        ),
        Index("ix_conversation_ticket_comments_tracking_id", "tracking_id"),
        Index("ix_conversation_ticket_comments_contact_id", "respond_contact_id"),
        Index("ix_conversation_ticket_comments_created_at", "created_at"),
        Index(
            "uq_conversation_ticket_comments_respond_comment_id",
            "respond_comment_id",
            unique=True,
            postgresql_where=text("respond_comment_id IS NOT NULL"),
        ),
    )
