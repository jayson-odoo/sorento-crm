"""Respond.io WhatsApp channels, message templates and per-use-case defaults.

Synced from the Respond.io API (see `app/services/respond_template_service.py`):

- ``respond_channels`` — channels of a workspace (``GET /v2/space/channel``).
- ``respond_message_templates`` — WhatsApp templates of a channel
  (``GET /v2/space/channel/{channelId}/template``). Hard-deleted on sync when
  gone from the API; only ``status='approved'`` rows are sendable.
- ``respond_template_defaults`` — one row per auto-send use case mapping a
  template + param mapping used when the contact's 24h window is closed.
  ``template_id`` is ``ON DELETE SET NULL`` so a sync hard-delete leaves the
  row with ``template_name_snapshot`` for the "template was removed" warning.

Plan: docs/plans/PLAN-whatsapp-template-fallback.md
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

TEMPLATE_DEFAULT_USE_CASES = (
    "complaint",
    "stock_inquiry",
    "purchase_request",
    "sponsorship_form",
    # Portal OTP — sent when a contact verifies on a new device and the 24h
    # window is closed. Map the approved auth/utility template's code param to
    # the ``otp_code`` variable.
    "portal_otp",
)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class RespondChannel(Base):
    __tablename__ = "respond_channels"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    workspace_id = Column(
        UUID(as_uuid=False),
        ForeignKey("respond_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Respond.io numeric channel id (e.g. 453209) — required in template sends.
    respond_channel_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=True)
    # Respond.io channel source, e.g. "whatsapp_business".
    source = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    synced_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspace = relationship("RespondWorkspace")
    templates = relationship(
        "RespondMessageTemplate",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "respond_channel_id", name="uq_respond_channels_ws_channel"),
        Index("ix_respond_channels_workspace_id", "workspace_id"),
    )


class RespondMessageTemplate(Base):
    __tablename__ = "respond_message_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    channel_id = Column(
        UUID(as_uuid=False),
        ForeignKey("respond_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Respond.io internal template row id (items[].id, e.g. 47212542).
    respond_template_id = Column(Integer, nullable=False)
    # Meta/WhatsApp template id + namespace (items[].templateId / .namespace).
    meta_template_id = Column(String(64), nullable=True)
    namespace = Column(String(64), nullable=True)
    name = Column(String(255), nullable=False)
    language_code = Column(String(16), nullable=False, server_default="en")
    category = Column(String(32), nullable=True)  # UTILITY | MARKETING | AUTHENTICATION
    status = Column(String(32), nullable=False, server_default="pending")  # approved | rejected | ...
    status_detail = Column(String(255), nullable=True)
    # Raw components array from the API (body/header/footer/buttons).
    components = Column(JSONB, nullable=False, server_default="[]")
    # Body component text (contains {{1}}..{{n}}) + derived positional param count.
    body_text = Column(Text, nullable=False, server_default="")
    param_count = Column(Integer, nullable=False, server_default="0")
    synced_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    channel = relationship("RespondChannel", back_populates="templates")

    __table_args__ = (
        UniqueConstraint("channel_id", "respond_template_id", name="uq_respond_templates_channel_tpl"),
        Index("ix_respond_message_templates_channel_id", "channel_id"),
        Index("ix_respond_message_templates_status", "status"),
    )


class RespondTemplateDefault(Base):
    __tablename__ = "respond_template_defaults"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    # One row per auto-send use case (see TEMPLATE_DEFAULT_USE_CASES).
    use_case = Column(String(32), nullable=False, unique=True)
    template_id = Column(
        UUID(as_uuid=False),
        ForeignKey("respond_message_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Survives template hard-delete so the UI can say "template was removed"
    # instead of silently showing "not set".
    template_name_snapshot = Column(String(255), nullable=True)
    # {"1": "contact_name", "2": "message", ...} — positional param -> variable.
    param_mapping = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    template = relationship("RespondMessageTemplate")
