"""Quotation document (+ lines) — AutoCount mirror (Slice 6).

Read-only mirror with a parent+lines shape (a sales quotation header plus its
QTDTL lines), so it does NOT go through ENTITY_SPECS (flat-master only). A
bespoke adopter ingests the header + lines together, resolving each line's
product by code. Idempotency key = DocKey (``quote_number = AC-{DocKey}``).

Annotation columns live on the header only (the quotation is the annotatable
unit). ``is_cancelled`` mirrors AutoCount's Cancelled flag — there is no
Sorento-side lifecycle on a mirror.
"""
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount DocKey-derived. Adoption/idempotency anchor: AC-{DocKey}.
    quote_number = Column(String(100), nullable=False, unique=True)
    # Human-facing DocNo (display; expected to change).
    source_doc_no = Column(String(100), nullable=True)
    debtor_code = Column(String(100), nullable=True)
    debtor_name = Column(String(255), nullable=True)
    doc_date = Column(Date, nullable=True)
    is_cancelled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    attention = Column(String(255), nullable=True)
    branch_code = Column(String(100), nullable=True)
    deliver_addr1 = Column(String(255), nullable=True)
    deliver_addr2 = Column(String(255), nullable=True)
    deliver_addr3 = Column(String(255), nullable=True)
    deliver_addr4 = Column(String(255), nullable=True)
    terms = Column(String(255), nullable=True)
    sales_agent = Column(String(100), nullable=True)

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines = relationship(
        "QuotationLine",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationLine.line_sequence",
    )

    __table_args__ = (
        Index("ix_quotations_quote_number", "quote_number"),
        Index("ix_quotations_debtor_code", "debtor_code"),
    )


class QuotationLine(Base):
    __tablename__ = "quotation_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    quotation_id = Column(
        UUID(as_uuid=False), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    # Resolved from the canonical line's product_code. RESTRICT: a quotation line
    # must point at a real product (a miss makes the whole quotation retryable).
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    line_sequence = Column(Integer, nullable=False, default=1)
    uom = Column(String(100), nullable=True)
    location = Column(String(100), nullable=True)
    qty = Column(Numeric(15, 4), nullable=True)
    unit_price = Column(Numeric(15, 4), nullable=True)
    sub_total = Column(Numeric(15, 2), nullable=True)
    discount_amt = Column(Numeric(15, 2), nullable=True)
    tax_code = Column(String(100), nullable=True)
    tax_rate = Column(Numeric(9, 4), nullable=True)
    tax = Column(Numeric(15, 2), nullable=True)
    description = Column(Text, nullable=True)
    further_description = Column(Text, nullable=True)
    package_code = Column(String(100), nullable=True)
    proj_no = Column(String(100), nullable=True)
    dept_no = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    quotation = relationship("Quotation", back_populates="lines")
    product = relationship("Product", lazy="joined")

    # Surfaced in the mirror UI instead of the raw product_id (no UUIDs in UI).
    @property
    def product_code(self):
        return self.product.product_code if self.product else None

    @property
    def product_name(self):
        return self.product.product_name if self.product else None

    __table_args__ = (
        Index("ix_quotation_lines_quotation_id", "quotation_id"),
        Index("ix_quotation_lines_product_id", "product_id"),
    )
