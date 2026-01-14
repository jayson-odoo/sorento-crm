"""Product management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Numeric, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

# Forward references for relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.inventory import Stock, StockBatch
    from app.models.procurement import ProductSupplier, InboundShipmentLine, SPOAllocation, PickingLine
    from app.models.marketing import PromotionProduct


class ProductCategory(Base):
    __tablename__ = "product_categories"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_code = Column(String(50), unique=True, nullable=False)
    category_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    parent_category_id = Column(UUID(as_uuid=False), ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    parent = relationship("ProductCategory", remote_side=[id], back_populates="children")
    children = relationship("ProductCategory", back_populates="parent")
    products = relationship("Product", back_populates="category")
    
    __table_args__ = (
        Index("ix_product_categories_parent_category_id", "parent_category_id"),
        Index("ix_product_categories_is_active", "is_active"),
    )


class Brand(Base):
    __tablename__ = "brands"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_code = Column(String(50), unique=True, nullable=False)
    brand_name = Column(String(150), nullable=False)
    manufacturer = Column(String(150), nullable=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    products = relationship("Product", back_populates="brand")
    
    __table_args__ = (
        Index("ix_brands_is_active", "is_active"),
    )


class UnitOfMeasure(Base):
    __tablename__ = "units_of_measure"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    uom_code = Column(String(50), unique=True, nullable=False)
    uom_name = Column(String(150), nullable=False)
    base_uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id", ondelete="SET NULL"), nullable=True)
    conversion_factor = Column(Numeric(10, 4), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    base_uom = relationship("UnitOfMeasure", remote_side=[id], back_populates="alternate_uoms")
    alternate_uoms = relationship("UnitOfMeasure", back_populates="base_uom")
    products = relationship("Product", back_populates="base_uom", foreign_keys="[Product.base_uom_id]")
    
    __table_args__ = (
        Index("ix_units_of_measure_base_uom_id", "base_uom_id"),
    )


class Product(Base):
    __tablename__ = "products"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_code = Column(String(100), unique=True, nullable=False)
    product_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey("product_categories.id"), nullable=False)
    brand_id = Column(UUID(as_uuid=False), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)
    base_uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id"), nullable=False)
    item_type = Column(String(50), nullable=True)
    list_price = Column(Numeric(12, 2), nullable=False)
    cost_price = Column(Numeric(12, 2), nullable=True)
    invoice_price = Column(Numeric(12, 2), nullable=True)
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
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    category = relationship("ProductCategory", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    base_uom = relationship("UnitOfMeasure", back_populates="products", foreign_keys=[base_uom_id])
    product_suppliers = relationship("ProductSupplier", back_populates="product", foreign_keys="ProductSupplier.product_id")
    stock = relationship("Stock", back_populates="product")
    stock_batches = relationship("StockBatch", back_populates="product")
    promotion_products = relationship("PromotionProduct", back_populates="product")
    inbound_shipment_lines = relationship("InboundShipmentLine", back_populates="product")
    spo_allocations = relationship("SPOAllocation", back_populates="product")
    picking_lines = relationship("PickingLine", back_populates="product")
    
    __table_args__ = (
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_base_uom_id", "base_uom_id"),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_product_code", "product_code"),
    )
