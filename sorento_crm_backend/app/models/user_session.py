"""Staff session model.

Opaque, DB-backed rolling sessions for CRM staff login — the same device-trust
model the contact portal uses (see ``app/models/portal.py``::PortalToken), but
keyed to an internal ``users`` row instead of a Respond.io contact.

A successful ``/api/v1/auth/login`` mints one row. The opaque ``token`` rides
inside the NextAuth httpOnly cookie and is sent to every ``/api/v1/*`` call as
``Authorization: Bearer <token>``. ``get_current_user`` resolves the row on every
request — so revocation (``revoked_at``) and expiry are instant, and role/status
changes take effect on the next request (no stale-JWT window).

Lifetimes:
  - "Remember me" checked  → 30-day rolling (``rolling=True``); each use re-extends
    ``expires_at`` to now+30d, throttled to ~once/day (29-day threshold).
  - "Remember me" unchecked → 8-hour absolute (``rolling=False``); never slides.

No absolute cap on the rolling window (matches the portal). Sessions die only by
expiry or explicit revoke (logout, password change, admin force-logout, block).
"""
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey, Index, Text
from sqlalchemy.sql import func
from app.database import Base
import uuid


class UserSession(Base):
    __tablename__ = "user_sessions"

    # String (not pg UUID) to match the migration column (sa.String) and the
    # sibling String keys (token / user_id). A pg UUID model type emits a
    # `... = %(pk)s::UUID` cast that errors against the VARCHAR column:
    # "operator does not exist: character varying = uuid". Values are uuid4 strings.
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    revoked_at = Column(DateTime(timezone=False), nullable=True)
    # True → 30-day sliding window; False → fixed 8h (remember-me unchecked).
    rolling = Column(Boolean, nullable=False, default=True, server_default="true")
    # Device metadata for the "your devices" UI + admin triage. Never shown raw —
    # the FE parses a friendly label from user_agent.
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    last_seen_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )
