"""Product costing: dated exchange rates, company settings, transport rules, party profiles
(lane PRODUCT-COSTING, `documentation/plans/products/CONTRACT-product-costing.md` section 2).

Six tables, all audited. Everything except `exchange_rates` is company-scoped. Nothing here
holds a unit cost, a landing cost or a selling price: cost comes from the supplier cost lists,
the selling price is `products.list_price` (AutoCount) and is never written by this lane.

Three tables are keyed by the record they extend (`costing_category_rules.category_id`,
`costing_product_overrides.product_id`, `customer_costing_profiles.customer_id`): there is at
most one row per record, and the key is what says so.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ExchangeRate(Base):
    """MYR per 1 unit of `currency`, from `effective_from` on. One row per currency per date.

    Not company-scoped: the books are in ringgit and a rate is the same for every company.
    The rate for a day is the row with the latest `effective_from <= day`; no row means "no
    rate", never 1. MYR has no row (the service refuses one).
    """

    __tablename__ = "exchange_rates"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    currency = Column(String(3), nullable=False)
    rate_to_base = Column(Numeric(18, 6), nullable=False)
    effective_from = Column(Date, nullable=False)
    note = Column(String(255), nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("currency", "effective_from", name="uq_exchange_rates_currency_from"),
        CheckConstraint("rate_to_base > 0", name="ck_exchange_rates_rate_positive"),
    )


class CostingSettings(Base, CompanyScopedMixin):
    """SST factor and the company default cost method. One row per company, made on first write."""

    __tablename__ = "costing_settings"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    sst_factor = Column(Numeric(6, 4), nullable=False, default=1.1, server_default="1.1000")
    default_method = Column(String(16), nullable=False, default="primary", server_default="primary")
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_costing_settings_company"),
        CheckConstraint("sst_factor > 0", name="ck_costing_settings_sst_positive"),
        CheckConstraint(
            "default_method IN ('primary', 'average', 'last_po')",
            name="ck_costing_settings_method",
        ),
    )


class CostingCategoryRule(Base, CompanyScopedMixin):
    """A product category's transport rule: ADD a flat MYR per unit, or MULTIPLY by a factor.
    No row means no rule."""

    __tablename__ = "costing_category_rules"
    __audit_track__ = True

    category_id = Column(
        UUID(as_uuid=False), ForeignKey("product_categories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode = Column(String(8), nullable=False)
    value = Column(Numeric(12, 4), nullable=False)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("mode IN ('add', 'multiply')", name="ck_costing_category_rules_mode"),
        CheckConstraint("value > 0", name="ck_costing_category_rules_value"),
    )


class CostingProductOverride(Base, CompanyScopedMixin):
    """A product's own transport rule and cost method, applying to every party. The row is
    deleted when every field is cleared."""

    __tablename__ = "costing_product_overrides"
    __audit_track__ = True

    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    transport_mode = Column(String(8), nullable=True)
    transport_value = Column(Numeric(12, 4), nullable=True)
    cost_method = Column(String(16), nullable=True)
    cost_method_supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(transport_mode IS NULL AND transport_value IS NULL) OR "
            "(transport_mode IS NOT NULL AND transport_mode IN ('add', 'multiply') "
            "AND transport_value IS NOT NULL "
            "AND transport_value > 0)",
            name="ck_costing_product_overrides_transport",
        ),
        CheckConstraint(
            "cost_method IS NULL OR cost_method IN ('primary', 'selected', 'average', 'last_po')",
            name="ck_costing_product_overrides_method",
        ),
        CheckConstraint(
            # A supplier only on `selected`. `selected` with NO supplier is allowed: deleting the
            # supplier sets it null (ON DELETE SET NULL) and the row then reads
            # "Selected supplier no longer linked" instead of blocking the delete.
            "cost_method = 'selected' OR cost_method_supplier_id IS NULL",
            name="ck_costing_product_overrides_supplier",
        ),
    )


class CustomerCostingProfile(Base, CompanyScopedMixin):
    """A party's costing profile: default mark-up %, optional cost method. One per customer."""

    __tablename__ = "customer_costing_profiles"
    __audit_track__ = True

    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    markup_pct = Column(Numeric(7, 3), nullable=False)
    cost_method = Column(String(16), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("markup_pct >= 0", name="ck_customer_costing_profiles_markup"),
        CheckConstraint(
            "cost_method IS NULL OR cost_method IN ('primary', 'average', 'last_po')",
            name="ck_customer_costing_profiles_method",
        ),
    )


class CustomerCostingProduct(Base, CompanyScopedMixin):
    """One product on a party's costing list, with an optional mark-up of its own."""

    __tablename__ = "customer_costing_products"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    markup_pct = Column(Numeric(7, 3), nullable=True)
    added_by = Column(String(100), nullable=True)
    added_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("customer_id", "product_id", name="uq_customer_costing_products_pair"),
        CheckConstraint(
            "markup_pct IS NULL OR markup_pct >= 0", name="ck_customer_costing_products_markup"
        ),
    )
