"""Tax code master — mirrored from AutoCount via the ESB ingest (Slice 1).

Read-only mirror (see credit_term.py for the annotation-survives-resync rule).
This table is the resolve-target for document-line ``TaxCode`` in later slices
(quotation/SO/DO/PO lines carry a tax code that must resolve to a real row here),
so it lands early even though nothing references it yet at Slice 1.
"""
from sqlalchemy import Boolean, Column, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class TaxCode(Base):
    __tablename__ = "tax_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # AutoCount TaxCode. Adoption/idempotency key.
    tax_code = Column(String(100), nullable=False, unique=True)
    # "S" (supply/sales) or "P" (purchase). One char in AutoCount.
    supply_purchase = Column(String(1), nullable=True)
    # Percentage, e.g. 6.0000. Numeric, never Integer (fractional rates).
    tax_rate = Column(Numeric(9, 4), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    # Sorento-only annotations, ingest-safe (see credit_term.py).
    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
