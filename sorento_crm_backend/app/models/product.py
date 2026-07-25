"""Product management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Numeric, Integer, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import CompanyScopedMixin
import uuid

# Forward references for relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.inventory import Stock, StockBatch
    from app.models.procurement import ProductSupplier, InboundShipmentLine, SPOAllocation, PickingLine
    from app.models.marketing import PromotionProduct
    from app.models.resources import Attachment


class ProductCategory(Base, CompanyScopedMixin):
    __tablename__ = "product_categories"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_code = Column(String(50), unique=True, nullable=False)
    category_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    parent_category_id = Column(UUID(as_uuid=False), ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    parent = relationship("ProductCategory", remote_side=[id], back_populates="children")
    children = relationship("ProductCategory", back_populates="parent")
    products = relationship("Product", back_populates="category")
    
    __table_args__ = (
        Index("ix_product_categories_parent_category_id", "parent_category_id"),
        Index("ix_product_categories_is_active", "is_active"),
    )


class Brand(Base, CompanyScopedMixin):
    __tablename__ = "brands"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_code = Column(String(50), unique=True, nullable=False)
    brand_name = Column(String(150), nullable=False)
    manufacturer = Column(String(150), nullable=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # Visibility codes overlapping `contact_access_types.code`. Used by the
    # resolver's promotion-domain product fallback to scope product search to
    # brands the active contact can see. Default mirrors the Attachment +
    # Promotion default so existing brands stay broadly visible.
    access_levels = Column(JSONB, nullable=False, server_default='["dealer","end_user"]')
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    products = relationship("Product", back_populates="brand")

    __table_args__ = (
        Index("ix_brands_is_active", "is_active"),
        Index("ix_brands_access_levels", "access_levels", postgresql_using="gin"),
    )


class UnitOfMeasure(Base, CompanyScopedMixin):
    __tablename__ = "units_of_measure"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    uom_code = Column(String(50), unique=True, nullable=False)
    uom_name = Column(String(150), nullable=False)
    base_uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id", ondelete="SET NULL"), nullable=True)
    conversion_factor = Column(Numeric(10, 4), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    base_uom = relationship("UnitOfMeasure", remote_side=[id], back_populates="alternate_uoms")
    alternate_uoms = relationship("UnitOfMeasure", back_populates="base_uom")
    products = relationship("Product", back_populates="base_uom", foreign_keys="[Product.base_uom_id]")
    
    __table_args__ = (
        Index("ix_units_of_measure_base_uom_id", "base_uom_id"),
        Index("ix_units_of_measure_is_active", "is_active"),
    )


class Product(Base, CompanyScopedMixin):
    """Product model. Set __audit_track__ = True for automatic audit logging of changes."""
    __tablename__ = "products"
    __audit_track__ = True
    __audit_entity_type__ = "product"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_code = Column(String(100), unique=True, nullable=False)
    product_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey("product_categories.id"), nullable=False)
    brand_id = Column(UUID(as_uuid=False), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)
    # Self-referential variant graph. A variant points at its (longest existing
    # boundary-prefix) parent product; a base has variant_of_id IS NULL. Deleting
    # a parent SET-NULLs its children (never blocks) — derivation re-anchors them
    # to the next existing ancestor. See app/services/variant_link_service.py and
    # docs/plans/PLAN-suggest-on-miss-variant-graph.md §1.
    variant_of_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    # Manual-curation flag. When true, the auto-derivation (reconcile_variant_links /
    # _adopt_orphans / backfill) must NOT re-derive or re-point this row's variant
    # link — a hand-set parent (or hand-cleared link) is sticky until "reset to auto"
    # clears the flag. See docs/plans/PLAN-variant-manual-curation.md.
    variant_link_manual = Column(Boolean, nullable=False, server_default="false", default=False)
    base_uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id"), nullable=False)
    item_type = Column(String(50), nullable=True)
    list_price = Column(Numeric(12, 2), nullable=False)
    cost_price = Column(Numeric(12, 2), nullable=True)
    invoice_price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=False, server_default="MYR", default="MYR")
    weight = Column(Numeric(10, 3), nullable=True)
    dimensions_length = Column(Numeric(10, 2), nullable=True)
    dimensions_width = Column(Numeric(10, 2), nullable=True)
    dimensions_height = Column(Numeric(10, 2), nullable=True)
    warranty_months = Column(Integer, nullable=True)
    has_serial_tracking = Column(Boolean, default=False, nullable=False)
    has_batch_tracking = Column(Boolean, default=False, nullable=False)
    reorder_level = Column(Integer, nullable=True)
    reorder_quantity = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_discontinued = Column(Boolean, default=False, nullable=False, server_default="false")
    # Discontinued-notification watermark. NULL = not yet reported by the batch cron
    # (cron-eligible while is_discontinued is True). Stamped with the run time when a
    # batch goes out; cleared back to NULL whenever is_discontinued flips True->False
    # so a later re-discontinuation is reported again.
    discontinued_notified_at = Column(DateTime(timezone=False), nullable=True)
    # Stable id of the batch this product was reported in. Deep-linked from the
    # notification to the product list filtered to exactly that batch.
    discontinued_notify_batch_id = Column(UUID(as_uuid=False), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    updated_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    category = relationship("ProductCategory", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    variant_of = relationship("Product", remote_side=[id], backref="variants")
    base_uom = relationship("UnitOfMeasure", back_populates="products", foreign_keys=[base_uom_id])
    product_suppliers = relationship(
        "ProductSupplier",
        back_populates="product",
        foreign_keys="ProductSupplier.product_id",
        passive_deletes=True,
    )
    stock = relationship("Stock", back_populates="product", passive_deletes=True)
    stock_batches = relationship("StockBatch", back_populates="product", passive_deletes=True)
    promotion_products = relationship(
        "PromotionProduct",
        back_populates="product",
        passive_deletes=True,
    )
    inbound_shipment_lines = relationship("InboundShipmentLine", back_populates="product")
    spo_allocations = relationship(
        "SPOAllocation",
        back_populates="product",
        passive_deletes=True,
    )
    picking_lines = relationship("PickingLine", back_populates="product")
    product_attachments = relationship(
        "ProductAttachment",
        back_populates="product",
        passive_deletes=True,
    )
    
    __table_args__ = (
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_base_uom_id", "base_uom_id"),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_product_code", "product_code"),
        Index("ix_products_variant_of_id", "variant_of_id"),
        Index(
            "ix_products_variant_link_manual",
            "variant_link_manual",
            postgresql_where=text("variant_link_manual = true"),
        ),
        Index("ix_products_discontinued_pending", "is_discontinued", "discontinued_notified_at"),
        Index("ix_products_discontinued_notify_batch_id", "discontinued_notify_batch_id"),
    )


class ProductAttachment(Base, CompanyScopedMixin):
    __tablename__ = "product_attachments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=True)
    sort_order = Column(Integer, nullable=True)
    access_levels = Column(JSONB, nullable=False, server_default='["dealer","end_user"]')
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=True)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    product = relationship("Product", back_populates="product_attachments")
    attachment = relationship("Attachment", foreign_keys=[attachment_id])
    
    __table_args__ = (
        Index("ix_product_attachments_product_id", "product_id"),
        Index("ix_product_attachments_attachment_id", "attachment_id"),
        Index("uq_product_attachment", "product_id", "attachment_id", unique=True),
        Index("ix_product_attachments_access_levels", "access_levels", postgresql_using="gin"),
    )
