"""Chinese -> English translation memory (R15, purchasing consolidation batch, lane C).

One row per phrase. Not company-scoped, like ``import_field_alias``: a translation of
"座厕" does not belong to one company's data, it is a fact about the phrase itself, and
every company that reads a supplier document in the same language benefits from the
same memory (D "simplest thing that works" - the alternative is duplicating the same
row per company for no behavioural difference).

``source`` says whether a human typed the English (``manual``, always wins) or the AI
Assistant's configured model filled the gap (``ai``, never overwrites a manual row) -
see ``app.services.translation_service``. ``hit_count`` is bumped on every read, so the
Translations admin page can show which phrases are actually seen again.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

SOURCE_MANUAL = "manual"
SOURCE_AI = "ai"
TRANSLATION_SOURCES = (SOURCE_MANUAL, SOURCE_AI)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class TranslationMemory(Base):
    __tablename__ = "translation_memory"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    # Normalised (trimmed, internal whitespace collapsed) by
    # `translation_service.normalize_source_text` before every read and write, so two
    # cells differing only in padding hit the same row.
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False, server_default="zh")
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False, server_default="en")
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        UniqueConstraint(
            "source_text", "source_lang", "target_lang", name="uq_translation_memory_phrase"
        ),
        CheckConstraint(
            "source IN ('manual', 'ai')", name="ck_translation_memory_source"
        ),
        Index("ix_translation_memory_updated_at", "updated_at"),
    )
