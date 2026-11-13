"""A staff user's passkey (PASSKEY-LOGIN, AC-04).

One row per WebAuthn credential. ``public_key`` holds the COSE_Key bytes py_webauthn returns
as ``credential_public_key`` and verifies an assertion against; ``credential_id`` is the
credential's raw id, base64url. Neither is a secret, but the key bytes are kept out of the
audit trail anyway (they mean nothing to a reader). The user handle a browser sends back is
the user's id as UTF-8, so no handle column is stored.
"""
import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.database import Base


class UserPasskey(Base):
    __tablename__ = "user_passkeys"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credential_id = Column(Text, nullable=False, unique=True)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(BigInteger, nullable=False, default=0, server_default="0")
    transports = Column(JSON, nullable=True)
    aaguid = Column(String, nullable=True)
    backed_up = Column(Boolean, nullable=False, default=False, server_default="false")
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (Index("ix_user_passkeys_user_id", "user_id"),)


# Add, rename and remove are audited by default (AC-25); the key bytes stay out of the trail.
UserPasskey.__audit_columns__ = [c.key for c in UserPasskey.__table__.columns if c.key != "public_key"]
