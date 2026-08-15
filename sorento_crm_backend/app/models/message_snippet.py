"""Reusable composer snippets - canned replies with ``$`` variables (UAC AC-L4).

Respond.io's own snippets are a client-side feature of their app with no API, so
this is our self-hosted equivalent: rows an admin manages in the CRM, offered in
the ticket-drawer composer behind a "/" picker.

**Workspace-global in v1** (the AC says so): no per-user and no per-company
scope. A snippet is a piece of shared team wording, not personal data, and the
first thing a per-user scope would cost is the reason to have them - everyone
answering the same question the same way.

The body carries ``$name`` tokens that are resolved from the ticket context at
INSERT time (never stored resolved), so an edit to the snippet reaches every
future insert and nothing is frozen into a row. See
``app.services.message_snippet_service.resolve_snippet_variables`` for the token
set and the fallbacks.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class MessageSnippet(Base):
    __tablename__ = "message_snippets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False)
    # The "/" keyword the composer filters on. Optional: a snippet is findable by
    # name alone. Unique case-insensitively (see __table_args__) so "/stock" can
    # never mean two things.
    shortcut = Column(String(60), nullable=True)
    body = Column(Text, nullable=False)
    # Retired wording stays readable in the admin list but leaves the picker.
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_message_snippets_is_active", "is_active"),
        # Declared here as well as in migration 329 so a create_all schema (the
        # test substrate) enforces it too: uniqueness that only exists in a
        # migration is uniqueness the tests cannot see. Name and shape match the
        # migration exactly, so alembic autogenerate sees no drift.
        Index(
            "uq_message_snippets_shortcut",
            func.lower(shortcut),
            unique=True,
            postgresql_where=text("shortcut IS NOT NULL"),
        ),
    )
