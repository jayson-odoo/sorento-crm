"""High-volume chat history model populated by n8n."""
from sqlalchemy import BigInteger, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel = Column(String(32), nullable=False)
    contact_id = Column(String(128), nullable=False)
    phone_number = Column(String(32), nullable=False)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=False), nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    type = Column(String(32), nullable=False)
    # Respond.io message id + the numbered-options result set the bot sent in
    # that message. Lets conversation-variables resolve a result set by the
    # message the user replied to, not only the latest one.
    message_id = Column(String(64), nullable=True)
    result = Column(JSONB, nullable=True)
    # Set on incoming rows when the user quote-replied to an older message.
    # `reply_to_message_id` matches the `message_id` of that earlier outgoing row,
    # so the chatbot can resolve the pick against its stored `result` set.
    reply_to_message_id = Column(String(64), nullable=True)
    reply_to_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_chat_histories_channel_contact_sent_id", "channel", "contact_id", "sent_at", "id"),
        Index("ix_chat_histories_channel_phone_sent", "channel", "phone_number", "sent_at"),
        Index("ix_chat_histories_channel_type_sent", "channel", "type", "sent_at"),
        Index(
            "ix_chat_histories_contact_message_id",
            "contact_id",
            "message_id",
            postgresql_where=message_id.isnot(None),
        ),
        Index(
            "ix_chat_histories_contact_reply_to",
            "contact_id",
            "reply_to_message_id",
            postgresql_where=reply_to_message_id.isnot(None),
        ),
    )
