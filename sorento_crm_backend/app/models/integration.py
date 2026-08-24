"""Integration models: the counterparty record, its API keys, and the call log."""
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Text,
    Integer,
    Index,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Integration(Base):
    """A counterparty Sorento exchanges data with (the AutoCount ESB, n8n, the MCP server).

    Bidirectional by design (plan decision A4): the same row carries the inbound
    identity - who may call us, via ``integration_api_keys`` - and the outbound
    destination, the config and credentials Sorento uses to call *them*. One
    relationship, one row, one screen for an operator to debug.

    Authorization is plain RBAC (A1/A8). ``act_as_user_id`` points at a real
    ``users`` row, so every write this integration makes is attributable in the
    audit trail and every endpoint can enforce ordinary permission slugs. There
    is deliberately no ``scopes_json``: a second authorization vocabulary beside
    a working one produces disagreements that are invisible at review.
    """

    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(50), nullable=False)

    # UNVERIFIED until a call actually succeeds -- a fresh row has proven nothing,
    # and defaulting to ACTIVE would misreport health on the integrations screen.
    status = Column(String(20), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")

    # The principal writes are attributed to (AC-AC-05a). Replaces the hardcoded
    # fake {"id": "system"} that matches no row in the database.
    act_as_user_id = Column(String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    # Non-secret and displayable: ESB base URL, AutoCount company code.
    config_json = Column(JSONB, nullable=True)
    # Fernet ciphertext, write-only over the API, never echoed by a read endpoint.
    # Empty for inbound-only integrations such as n8n.
    credentials_json = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    last_used_at = Column(DateTime(timezone=False), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_integrations_type", "type"),
        Index("ix_integrations_is_active", "is_active"),
    )


class IntegrationApiKey(Base):
    """One issued API key. The plaintext exists only in the creation response.

    Rotation issues a *new* row pointing back at the old via ``rotated_from_id``
    and stamps ``expires_at`` on the old one. The window closes passively, checked
    at request time (A5) -- the scheduler is opt-in and defaults off, so a
    cron-driven expiry would leave superseded keys valid indefinitely wherever
    ``ENABLE_SCHEDULER`` was never set. A security control must not fail open
    because an unrelated env var is missing.
    """

    __tablename__ = "integration_api_keys"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(
        UUID(as_uuid=False),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Hex SHA-256. Unique because verification is a single indexed lookup here --
    # a collision would make the caller's identity ambiguous.
    key_hash = Column(String(64), nullable=False)
    # Short non-secret fragment, shown in the UI to tell two keys apart.
    key_prefix = Column(String(16), nullable=False)

    # Both null on a freshly issued key: it lives until rotated or revoked.
    # A default expiry would silently kill integrations nobody touched.
    expires_at = Column(DateTime(timezone=False), nullable=True)
    revoked_at = Column(DateTime(timezone=False), nullable=True)

    rotated_from_id = Column(
        UUID(as_uuid=False), ForeignKey("integration_api_keys.id", ondelete="SET NULL"), nullable=True
    )
    # Lets an admin confirm the caller actually migrated *before* the grace
    # window closes. Without it, rotation is a coin flip (AC-AC-06a).
    last_used_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_integration_api_keys_key_hash"),
        Index("ix_integration_api_keys_integration_id", "integration_id"),
    )


class IntegrationLog(Base):
    __tablename__ = "integration_log"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_channel = Column(String(100), nullable=False)
    business_table = Column(String(100), nullable=False)
    business_id = Column(UUID(as_uuid=False), nullable=False)
    external_reference = Column(String(255), nullable=True)
    direction = Column(String(10), nullable=False)  # "inbound" or "outbound"
    endpoint = Column(String(512), nullable=False)
    http_method = Column(String(10), nullable=False)
    request_headers = Column(Text, nullable=True)
    request_payload = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, success, failed
    response_headers = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    correlation_id = Column(UUID(as_uuid=False), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retry_allowed = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    processed_at = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_integration_log_business_table_business_id", "business_table", "business_id"),
        Index("ix_integration_log_status", "status"),
        Index("ix_integration_log_integration_channel", "integration_channel"),
        Index("ix_integration_log_created_at", "created_at"),
        Index("ix_integration_log_next_retry_at", "next_retry_at"),
    )
