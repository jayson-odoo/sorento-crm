"""Credit term master — mirrored from AutoCount via the ESB ingest (Slice 1).

Read-only mirror. AutoCount owns the data; the ESB pushes canonical records in
and the ingest upserts them by ``display_term``. Nothing in Sorento creates or
edits a credit term except ingest, with ONE exception: the two annotation
columns (``internal_note``/``follow_up``) are Sorento-only, written solely by
the annotation PATCH and never touched by the ingest column-map, so they survive
every re-sync.

Existence of this table is what unblocks supplier/customer ingest: until it
landed, ``_supplier_columns``/``_customer_columns`` reported any
``payment_terms_code`` as retryable (the master did not exist). Now the code
resolves against ``display_term`` here.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class CreditTerm(Base):
    __tablename__ = "credit_terms"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # AutoCount DisplayTerm. Adoption/idempotency key: a re-push matches on this,
    # never on a mutable id, so a second sync updates in place.
    display_term = Column(String(100), nullable=False, unique=True)
    terms = Column(String(255), nullable=True)
    term_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    # Sorento-only annotations. Ingest never writes these (not in the column-map),
    # so they persist across re-sync. Editable only via the annotation PATCH.
    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
