"""Payment method master — AutoCount mirror (Slice 2). Read-only mirror."""
from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount PaymentMethod. Adoption/idempotency key.
    payment_method = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    bank_account = Column(String(100), nullable=True)
    journal_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
