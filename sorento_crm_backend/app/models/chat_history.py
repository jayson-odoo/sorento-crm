"""High-volume chat history model populated by n8n."""
from sqlalchemy import BigInteger, Column, DateTime, Index, String, Text
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
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_chat_histories_channel_contact_sent_id", "channel", "contact_id", "sent_at", "id"),
        Index("ix_chat_histories_channel_phone_sent", "channel", "phone_number", "sent_at"),
        Index("ix_chat_histories_channel_type_sent", "channel", "type", "sent_at"),
    )
