"""Request-quotation document (+ lines) — AutoCount mirror (Slice 7).

Read-only mirror of an AutoCount RFQ (request for quotation to a supplier).
Parent+lines, so it does NOT go through ENTITY_SPECS. Bespoke adopter ingests
header + RQDTL together, resolving each line's product by code and the header's
supplier by CreditorCode (best-effort; the FK is nullable). Idempotency key =
DocKey (``rq_number = AC-{DocKey}``).

NOT ``purchase_requests`` -- that is a separate Sorento workflow entity. This is
a pure supplier-facing RFQ document mirror.
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


class RequestQuotation(Base):
    __tablename__ = "request_quotations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount DocKey-derived. Adoption/idempotency anchor: AC-{DocKey}.
    rq_number = Column(String(100), nullable=False, unique=True)
    source_doc_no = Column(String(100), nullable=True)
    # Best-effort CreditorCode -> suppliers.id (nullable: a miss keeps the raw code).
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    creditor_code = Column(String(100), nullable=True)
    creditor_name = Column(String(255), nullable=True)
    doc_date = Column(Date, nullable=True)
    purchase_agent = Column(String(100), nullable=True)

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    supplier = relationship("Supplier", lazy="joined")
    lines = relationship(
        "RequestQuotationLine",
        back_populates="request_quotation",
        cascade="all, delete-orphan",
        order_by="RequestQuotationLine.line_sequence",
    )

    # Surfaced in the mirror UI instead of the raw supplier_id (no UUIDs in UI).
    @property
    def supplier_code(self):
        return self.supplier.supplier_code if self.supplier else self.creditor_code

    @property
    def supplier_name(self):
        return self.supplier.supplier_name if self.supplier else self.creditor_name

    __table_args__ = (
        Index("ix_request_quotations_rq_number", "rq_number"),
        Index("ix_request_quotations_creditor_code", "creditor_code"),
    )


class RequestQuotationLine(Base):
    __tablename__ = "request_quotation_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_quotation_id = Column(
        UUID(as_uuid=False), ForeignKey("request_quotations.id", ondelete="CASCADE"), nullable=False
    )
    # Resolved from product_code. RESTRICT: a line must point at a real product
    # (a miss makes the whole RFQ retryable).
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    line_sequence = Column(Integer, nullable=False, default=1)
    uom = Column(String(100), nullable=True)
    location = Column(String(100), nullable=True)
    qty = Column(Numeric(15, 4), nullable=True)
    unit_price = Column(Numeric(15, 4), nullable=True)
    sub_total = Column(Numeric(15, 2), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    request_quotation = relationship("RequestQuotation", back_populates="lines")
    product = relationship("Product", lazy="joined")

    @property
    def product_code(self):
        return self.product.product_code if self.product else None

    @property
    def product_name(self):
        return self.product.product_name if self.product else None

    __table_args__ = (
        Index("ix_request_quotation_lines_rq_id", "request_quotation_id"),
        Index("ix_request_quotation_lines_product_id", "product_id"),
    )
