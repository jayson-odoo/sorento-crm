"""User submission portal models.

Contact-scoped tokens grant a contact (identified by Respond.io contact id) access
to view and edit their own submissions across complaints, stock inquiries,
purchase requests and sponsorship forms — without a CRM login. After token
expiry the contact re-verifies via OTP sent to their phone via Respond.io.
"""
from sqlalchemy import Column, String, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class PortalToken(Base):
    __tablename__ = "portal_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(255), unique=True, nullable=False, index=True)
    contact_id = Column(Text, nullable=False)
    space_id = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    revoked_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_portal_tokens_contact_id", "contact_id"),
        Index("ix_portal_tokens_expires_at", "expires_at"),
    )


class PortalOtpCode(Base):
    __tablename__ = "portal_otp_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    contact_id = Column(Text, nullable=False)
    space_id = Column(Text, nullable=False)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    consumed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_portal_otp_codes_contact_id", "contact_id"),
        Index("ix_portal_otp_codes_created_at", "created_at"),
    )
