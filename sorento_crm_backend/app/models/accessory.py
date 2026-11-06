"""Accessories included with a product or a combo (PRICETAG-ACCESSORIES).

An accessory is a library item (picture, name, one short spec line) that is NOT a product code:
the chopping board, colander or drainer a sink ships with. A product and each of its combos keep
their OWN ordered list of them, independently (owner ruling Q1, 6 Nov): a combo never inherits its
host product's list. The price tag's "Accessories" box prints the list.

Plan: documentation/plans/dealer-kit/PLAN-pricetag-accessories-06nov.md.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Accessory(Base, CompanyScopedMixin):
    """One library item. The name is unique per company ignoring case (one DRAINER, reused)."""

    __tablename__ = "accessories"
    __audit_track__ = True
    __audit_entity_type__ = "accessory"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(100), nullable=False)
    spec = Column(String(200), nullable=True)
    # SET NULL: deleting the attachment clears the pointer rather than blocking on it, the same
    # rule `product_combos.image_attachment_id` follows.
    image_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_accessories_company_lower_name", "company_id", text("lower(name)"), unique=True),
    )


class ProductAccessory(Base):
    """One accessory on a product's own list. Reached through the product, which carries the
    company partition (like `product_combos`)."""

    __tablename__ = "product_accessories"
    __audit_parent__ = "product_id"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: a listed accessory cannot vanish from under a product; the API refuses the delete
    # with a message naming where it is used.
    accessory_id = Column(
        UUID(as_uuid=False), ForeignKey("accessories.id", ondelete="RESTRICT"), nullable=False
    )
    sort_order = Column(Integer, nullable=False, server_default="0")

    accessory = relationship("Accessory", lazy="joined")

    __table_args__ = (
        UniqueConstraint("product_id", "accessory_id", name="uq_product_accessories_pair"),
        Index("ix_product_accessories_product_id", "product_id"),
        Index("ix_product_accessories_accessory_id", "accessory_id"),
    )


class ProductComboAccessory(Base):
    """One accessory on a combo's own list (its "Free items")."""

    __tablename__ = "product_combo_accessories"
    __audit_parent__ = "combo_id"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    combo_id = Column(
        UUID(as_uuid=False), ForeignKey("product_combos.id", ondelete="CASCADE"), nullable=False
    )
    accessory_id = Column(
        UUID(as_uuid=False), ForeignKey("accessories.id", ondelete="RESTRICT"), nullable=False
    )
    sort_order = Column(Integer, nullable=False, server_default="0")

    accessory = relationship("Accessory", lazy="joined")

    __table_args__ = (
        UniqueConstraint("combo_id", "accessory_id", name="uq_product_combo_accessories_pair"),
        Index("ix_product_combo_accessories_combo_id", "combo_id"),
        Index("ix_product_combo_accessories_accessory_id", "accessory_id"),
    )
