"""Product combos - the catalogue package a product is sold as (PLAN-price-tag-combos D1).

A combo lives on the REAL host product (a cabinet), is named the way the catalogue
names it ("3 in 1", "4 in 1"), and lists the parts that come with it. A part with no
choice group is fixed - it is always in the package. Parts sharing a choice group are
the options the customer picks ONE of (the four basin colours). A combo carries no code
and no price: the price is summed per tag from the products on it.

Deliberately NOT a product set. A set is a synthetic code the system never sold, and the
chatbot searches sets (`chatbot/lanes/business/gate.py`); combos are invisible to it,
which is the owner's ruling 1 and what AC-S1-8 guards.

Not company-scoped on their own: a combo is reachable only through its host product,
which carries the partition. Every read and write resolves the host under the caller's
scope first, so a caller scoped elsewhere gets 404 on the host (AC-S1-7).
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ProductCombo(Base):
    """One catalogue package on one host product.

    `UNIQUE (host_product_id, name)` is the natural key: the catalogue names a package
    once, and two combos called "3 in 1" on one cabinet is the marketing user having
    lost their place - answered as a 409 the modal shows inline (AC-S1-2).
    """

    __tablename__ = "product_combos"
    __audit_track__ = True
    __audit_entity_type__ = "product_combo"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    # RESTRICT: a product that is somebody's package host cannot be deleted out from
    # under it - the combo would otherwise point at nothing.
    host_product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    parts = relationship(
        "ProductComboPart",
        back_populates="combo",
        cascade="all, delete-orphan",
        order_by="ProductComboPart.sort_order",
    )
    host_product = relationship("Product", lazy="joined")

    __table_args__ = (
        UniqueConstraint("host_product_id", "name", name="uq_product_combos_host_name"),
        Index("ix_product_combos_host_product_id", "host_product_id"),
    )


class ProductComboPart(Base):
    """One part on a combo.

    `choice_group` NULL means fixed - it is always in the package. A label means this is
    one of the options for that label, and two or more rows sharing it are what the
    customer picks one of.

    The host-as-part rule is enforced in the SERVICE, not by a CHECK: a row-level CHECK
    cannot see the combo's own `host_product_id`, and a trigger for one rule the service
    already owns is machinery nobody asked for (plan D1).
    """

    __tablename__ = "product_combo_parts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    combo_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_combos.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT for the same reason the host is: a product named by a package cannot
    # vanish from under it. A SUBMITTED request line naming the same product does NOT
    # pin the part in place - that is a fact about the request, not a live pointer into
    # the catalogue's current packaging (AC-S1-5).
    part_product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    choice_group = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    combo = relationship("ProductCombo", back_populates="parts")
    part_product = relationship("Product", lazy="joined")

    __table_args__ = (
        UniqueConstraint("combo_id", "part_product_id", name="uq_product_combo_parts_product"),
        Index("ix_product_combo_parts_combo_id", "combo_id"),
        Index("ix_product_combo_parts_part_product_id", "part_product_id"),
    )
