"""AI assistant configuration, conversations, messages, and governance events."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class AIAssistantConfig(Base):
    __tablename__ = "ai_assistant_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, server_default="openai")
    model: Mapped[str] = mapped_column(String(128), nullable=False, server_default="gpt-4o-mini")
    temperature: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_tools: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    rag_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AIAssistantConversation(Base):
    __tablename__ = "ai_assistant_conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list["AIAssistantMessage"]] = relationship(
        "AIAssistantMessage", back_populates="conversation", cascade="all,delete-orphan"
    )

    __table_args__ = (
        Index("ix_ai_assistant_conversations_user_id", "user_id"),
        Index("ix_ai_assistant_conversations_updated_at", "updated_at"),
    )


class AIAssistantMessage(Base):
    __tablename__ = "ai_assistant_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ai_assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    conversation: Mapped[AIAssistantConversation] = relationship("AIAssistantConversation", back_populates="messages")

    __table_args__ = (
        Index("ix_ai_assistant_messages_conversation_id", "conversation_id"),
        Index("ix_ai_assistant_messages_role", "role"),
    )


class AIAssistantGovernanceEvent(Base):
    __tablename__ = "ai_assistant_governance_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ai_assistant_conversations.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    module_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    permission_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_ai_assistant_governance_events_user_id", "user_id"),
        Index("ix_ai_assistant_governance_events_event_type", "event_type"),
    )
