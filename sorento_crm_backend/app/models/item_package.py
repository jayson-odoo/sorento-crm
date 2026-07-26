"""Item package master (+ lines) — AutoCount mirror (Slice 3).

Read-only mirror with a parent+lines shape, so it does NOT go through
ENTITY_SPECS (that layer is flat-master only). A bespoke adopter ingests the
header + its PackageDTL lines together, resolving each line's product by code.

Annotation columns live on the header only (a package is the annotatable unit).
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database import Base
import uuid


class ItemPackage(Base):
    __tablename__ = "item_packages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount PackageCode. Adoption/idempotency key (no DocKey for packages).
    package_code = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    expiry_date = Column(Date, nullable=True)
    # Qty as Numeric, never Integer (fractional AutoCount quantities).
    limited_qty = Column(Numeric(15, 4), nullable=True)
    opening_qty = Column(Numeric(15, 4), nullable=True)
    user_uom = Column(String(100), nullable=True)
    bar_code = Column(String(100), nullable=True)
    further_description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines = relationship(
        "ItemPackageLine",
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="ItemPackageLine.line_sequence",
    )


class ItemPackageLine(Base):
    __tablename__ = "item_package_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_package_id = Column(
        UUID(as_uuid=False), ForeignKey("item_packages.id", ondelete="CASCADE"), nullable=False
    )
    # Resolved from the canonical line's product_code. RESTRICT: a package line
    # must point at a real product.
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    line_sequence = Column(Integer, nullable=False, default=1)
    uom = Column(String(100), nullable=True)
    qty = Column(Numeric(15, 4), nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    package = relationship("ItemPackage", back_populates="lines")
    product = relationship("Product", lazy="joined")

    # Surfaced in the mirror UI instead of the raw product_id (no UUIDs in UI).
    @property
    def product_code(self):
        return self.product.product_code if self.product else None

    @property
    def product_name(self):
        return self.product.product_name if self.product else None
