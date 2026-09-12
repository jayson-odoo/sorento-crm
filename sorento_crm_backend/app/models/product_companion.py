""""Supplied with" companion rules (PLAN-scm-supplied-with-companions.md section 3.1).

A rule says a COMPANION product rides inside its HOST(s) own line when the supplier
ships them together - CKSW015 (seat cover) inside CKS1050's own line, never its own PO
line. A rule with two hosts (SC-RL with the X + Y pair) requires BOTH present on the
same order before it bites; one host is the common case.

Configured on the companion product's own Suppliers tab ("Supplied with"); the host's
own page shows the read-only mirror ("Ships with"). `bundled_qty` /
`bundled_with_row_id` on `projects.order_inquiry_rows` (S3's other half) are what the
rule actually BITES on `ProjectOrderInquiryService.derive_bundles`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CompanyScopedMixin


class ProductCompanionRule(Base, CompanyScopedMixin):
    """One companion, one supplier scope (or "any"), one ratio.

    `UNIQUE (company_id, companion_product_id, supplier_id)` is the natural key - a
    companion may have several rules only if they name DIFFERENT suppliers. Postgres
    treats every NULL as distinct, so that constraint alone would let two "any
    supplier" rules coexist for the same companion; the two partial indexes below
    (`__table_args__`) are what actually forbids it (UAC A4).
    """

    __tablename__ = "product_companion_rules"
    __audit_track__ = True
    __audit_entity_type__ = "product_companion_rule"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # RESTRICT: a product named as a companion of an active rule cannot be deleted out
    # from under it (UAC A6) - the rule would otherwise point at nothing.
    companion_product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL = "any supplier" (owner ruling, 9 Sep: "just in case"). SET NULL rather than
    # RESTRICT: a supplier going away should widen the rule's scope, not block the
    # supplier's own deletion over an unrelated companion configuration.
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    # Companion units per ONE host unit (ruling 1). NUMERIC, never Integer - a fractional
    # ratio (0.5) is a real case (B15), and an Integer column truncates it silently.
    ratio = Column(Numeric(15, 4), nullable=False, default=1, server_default=text("1"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)

    hosts = relationship(
        "ProductCompanionRuleHost",
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="ProductCompanionRuleHost.seq",
    )
    companion_product = relationship("Product", lazy="joined")
    supplier = relationship("Supplier", lazy="joined")

    __table_args__ = (
        Index(
            "uq_product_companion_rules_supplier",
            "company_id",
            "companion_product_id",
            "supplier_id",
            unique=True,
            postgresql_where=text("supplier_id IS NOT NULL"),
        ),
        Index(
            "uq_product_companion_rules_any_supplier",
            "company_id",
            "companion_product_id",
            unique=True,
            postgresql_where=text("supplier_id IS NULL"),
        ),
        Index("ix_product_companion_rules_companion", "companion_product_id"),
    )


class ProductCompanionRuleHost(Base):
    """One host on a rule. Two rows for the same rule means BOTH must be present on
    an order (the X + Y pair) before the rule applies.

    Not company-scoped on its own - it hangs off `ProductCompanionRule`, which is.
    """

    __tablename__ = "product_companion_rule_hosts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_companion_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT: a product named as a host of an active rule cannot be deleted out from
    # under it either (UAC A6).
    host_product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Insertion order, assigned by the DATABASE via a real sequence rather than by any
    # caller: "the FIRST host named on the rule is the anchor" (plan 3.2, B5) has to
    # survive a plain `ProductCompanionRuleHost(rule_id=..., host_product_id=...)`
    # insert - neither this model's own service nor the test fixtures ever set an
    # explicit position, and a UUID primary key carries no order at all.
    seq = Column(BIGINT, Sequence("product_companion_rule_host_seq"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    rule = relationship("ProductCompanionRule", back_populates="hosts")
    host_product = relationship("Product", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "rule_id", "host_product_id", name="uq_product_companion_rule_host"
        ),
        Index("ix_product_companion_rule_hosts_rule_id", "rule_id"),
        Index("ix_product_companion_rule_hosts_host_product_id", "host_product_id"),
    )
