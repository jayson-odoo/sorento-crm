"""Respond.io workspace configuration (multi-workspace per deployment).

The `commercial_leads` reciprocal relationship is added at runtime by
`app/modules/commercial_core/_base_patches.py` when the commercial_core
module is enabled — keeps this base class commercial-free.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class RespondWorkspace(Base):
    __tablename__ = "respond_workspaces"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    space_id = Column(String(64), nullable=False)
    name = Column(String(255), nullable=True)
    api_key_ciphertext = Column(Text, nullable=False)
    base_url = Column(String(512), nullable=True)
    # Business WhatsApp number for this workspace's channel (E.164 digits).
    # Drives the portal verify page's wa.me click-to-chat escape hatch.
    whatsapp_number = Column(String(32), nullable=True)
    # Ideation pipeline: the shared-service Product this workspace maps to
    # (one sorento deployment -> one shared-service Product of kind=software).
    # Stored as a UUID string; server-side only, NEVER rendered in the FE.
    # NULL keeps ideation dormant/fail-closed for this workspace (no create_idea).
    ideation_product_id = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_default = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    respond_contacts = relationship("RespondContact", back_populates="workspace")

    __table_args__ = (
        Index("ix_respond_workspaces_space_id", "space_id"),
        Index("ix_respond_workspaces_is_active", "is_active"),
        Index(
            "uq_respond_workspaces_one_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
        ),
    )
