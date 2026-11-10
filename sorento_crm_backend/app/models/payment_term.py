"""AutoCount payment terms (`Terms`: DisplayTerm, Terms) as a read-only master.

The real AutoCount row carries only two fields (crew GET probe, 10 Nov 2026): `DisplayTerm`, the
label that prints ("CASH BEFORE DELIVERY", "Net 30 days"), and `Terms`, the calculation rule
("C.O.D.", "Net 0th Next 1 Month"). There is no description and no day count.

QUOTE-TERMS-SELECT (PLAN-quote-terms-select-10nov.md): only the ESB ingest creates or updates a
row (`master_ingest_service.ENTITY_SPECS["payment_terms"]`); the CRM has no edit screen and never
writes AutoCount. A quotation and its terms template pick one through ``payment_term_id``; the
printed text stays on their own ``payment_terms`` column, so a later sync never rewrites a
quotation that was already sent.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


class PaymentTerm(Base, CompanyScopedMixin):
    __tablename__ = "payment_terms"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount `Terms.DisplayTerm`, exactly as AutoCount spells it: what prints on a quotation
    # and what a debtor's terms name. Unique per company (case matters: "Cash" is not "CASH").
    term_code = Column(String(100), nullable=False)
    # AutoCount `Terms.Terms`, the calculation rule. Shown beside the label in the picker only.
    term_rule = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("uq_payment_terms_company_term_code", "company_id", "term_code", unique=True),
    )
