"""Product sets: a code that names an assembly sold as one thing, stocked as several.

`SRTWC8608-RL` is printed on a flyer and asked for on WhatsApp, but the catalogue
holds only its parts - `SRTWCX8608-RL` the pedestal, `SRTWCY8608` the cistern and
`SRTWC8608-SC` the seat cover. No product carries the flyer's code, so the
resolver's exact match finds nothing and the customer is told the product does not
exist. A ProductSet is that missing code.

A set is NOT a product. It is never stocked, never costed, never sent to
accounting and never ordered - what would be ordered is always its members. It is
also NOT the dealer-kit `Bundle`, which has no code and *is* an authored price; a
set is a code first and its price is derived from the members it names.

No role column, deliberately. "Which one is the cistern" was proposed and dropped
because nothing depended on it: the price basis is a per-member tick, the
complete-sets figure needs quantity, and the labels already exist in the product
description ("CLOSE-COUPLED CISTERN ONLY"). A column that only restates data we
already hold is a second place for it to be wrong.

UAC: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
Plan: `documentation/plans/master-data/PLAN-product-sets.md`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CompanyScopedMixin


class ProductSet(Base, CompanyScopedMixin):
    __tablename__ = "product_sets"
    __audit_track__ = True
    __audit_entity_type__ = "product_set"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    set_code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)

    # NULL means "computed from the ticked members". A number here wins and is
    # rendered as an override against the computed figure, never silently in its
    # place: the support question is always "why does the flyer say 1,180 and the
    # system say 1,200", and hiding the computed value makes it unanswerable.
    list_price_override = Column(Numeric(15, 2), nullable=True)
    override_set_by = Column(UUID(as_uuid=False), nullable=True)
    override_set_at = Column(DateTime(timezone=False), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)

    members = relationship(
        "ProductSetMember",
        back_populates="product_set",
        cascade="all, delete-orphan",
        order_by="ProductSetMember.sort_order",
    )

    __table_args__ = (
        # Per company, not global. Sorento and Mocha both legitimately carry the
        # same codes - every product code in the catalogue exists twice - so a
        # global unique index would make the two companies fight over one row.
        UniqueConstraint("company_id", "set_code", name="uq_product_sets_company_code"),
        Index("ix_product_sets_set_code", "set_code"),
    )


class ProductSetMember(Base):
    """One real SKU inside a set. These are what a stock answer counts."""

    __tablename__ = "product_set_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_set_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT, not CASCADE: a set must never hold a dangling member, and a
    # product disappearing out from under a set would make the complete-sets
    # figure quietly wrong rather than loudly refused.
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # NUMERIC, never Integer. An Integer quantity column truncates fractional and
    # negative values with no error, which this repo has paid for before.
    quantity = Column(Numeric(15, 4), nullable=False, default=1, server_default=text("1"))
    # The price basis. Ticking members IS the formula - no expression language,
    # no config DSL. "Pedestal only", "cistern plus seat cover", any combination.
    contributes_to_price = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    product_set = relationship("ProductSet", back_populates="members")
    product = relationship("Product", lazy="joined")

    __table_args__ = (
        UniqueConstraint("product_set_id", "product_id", name="uq_product_set_member"),
        Index("ix_product_set_members_set_id", "product_set_id"),
        Index("ix_product_set_members_product_id", "product_id"),
    )
