"""AutoCount payment terms (`Terms`: DisplayTerm, Description, TermDays) as a read-only master.

QUOTE-TERMS-SELECT (PLAN-quote-terms-select-10nov.md): only the ESB ingest creates or updates a
row (`master_ingest_service.ENTITY_SPECS["payment_terms"]`); the CRM has no edit screen and never
writes AutoCount. A quotation and its terms template pick one through ``payment_term_id``; the
printed text stays on their own ``payment_terms`` column, so a later sync never rewrites a
quotation that was already sent.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


class PaymentTerm(Base, CompanyScopedMixin):
    __tablename__ = "payment_terms"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount `Terms.DisplayTerm`, e.g. "C.O.D." or "30 DAYS". Unique per company.
    term_code = Column(String(50), nullable=False)
    # AutoCount `Terms.Description`; what prints on a quotation, else the code.
    description = Column(Text, nullable=True)
    term_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("uq_payment_terms_company_term_code", "company_id", "term_code", unique=True),
    )
