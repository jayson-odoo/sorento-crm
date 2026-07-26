"""Tax entity master — AutoCount e-Invoice tax party mirror (Slice 2).

Read-only mirror. Adoption/idempotency key is ``tax_entity_id`` (AutoCount's
surrogate TaxEntityID), not TIN -- TIN can be blank or shared, the surrogate is
stable and unique. Fields map 1:1 snake_case from the AutoCount payload.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class TaxEntity(Base):
    __tablename__ = "tax_entities"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount TaxEntityID (surrogate). Adoption/idempotency key.
    tax_entity_id = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    tin = Column(String(100), nullable=True)
    identity_no = Column(String(100), nullable=True)
    tax_branch_id = Column(String(100), nullable=True)
    tax_classification = Column(Integer, nullable=True)
    gst_register_no = Column(String(100), nullable=True)
    sst_register_no = Column(String(100), nullable=True)
    tourism_tax_register_no = Column(String(100), nullable=True)
    trade_name = Column(String(255), nullable=True)
    business_activity_desc = Column(String(255), nullable=True)
    msic_code = Column(String(40), nullable=True)
    # Address block.
    address = Column(String(255), nullable=True)
    post_code = Column(String(40), nullable=True)
    city = Column(String(100), nullable=True)
    state_code = Column(String(40), nullable=True)
    country_code = Column(String(40), nullable=True)
    phone = Column(String(100), nullable=True)
    email_address = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
