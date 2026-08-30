"""Inventory management models."""
import enum
from sqlalchemy import Boolean, Column, Computed, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import CompanyScopedMixin
import uuid

# Forward references for relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.procurement import SPOAllocation, PickingLine


class BatchStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DAMAGED = "DAMAGED"
    EXPIRED = "EXPIRED"
    RETURNED = "RETURNED"


class Warehouse(Base, CompanyScopedMixin):
    __tablename__ = "warehouses"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_code = Column(String(50), unique=True, nullable=False)
    warehouse_name = Column(String(150), nullable=True)
    location = Column(String(255), nullable=True)
    manager_id = Column(UUID(as_uuid=False), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # Does this location's stock count as available to plan against. CONFIG, defaulting to
    # true for every location: deriving it from the code naming convention would bake one
    # client's convention into the engine and would silently exclude stock. An admin turns
    # one off.
    counts_as_available = Column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    # Which shared pool this location may draw on. The STRUCTURAL half, and what lets a
    # shortage in BRW-BB be covered from BRW instead of triggering a purchase. Seeded from
    # the SITE-SUFFIX convention but STORED, never parsed at runtime, so a client whose
    # codes look nothing like Sorento's repoints rows instead of needing code.
    # Distinct from counts_as_available on purpose: BRW-BB stock IS sellable yet can only
    # serve customer BB, so one flag cannot express both (ADR-0011 amendment).
    pool_warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    # Who this location sells to: `dealer` or `project`. The bare site code (BRW) is the
    # dealer bin and its suffixed bins (BRW-BB, BRW-IB) are project stock, which is why
    # "last purchase cost" is two different numbers depending on who is asking. SEEDED from
    # that convention and then never parsed again, same reasoning as pool_warehouse_id: a
    # client whose codes look nothing like Sorento's repoints rows instead of needing code.
    segment = Column(String(20), nullable=True)
    # Whether this bin takes part in fulfilment planning at all (borrow ladder v7.1, R17).
    # A bin that is OFF is outside fulfilment planning entirely: its on hand, its incoming
    # and its sales-order lines are invisible to the ladder, the board and the Stock Debt
    # view - which is a stronger statement than `counts_as_available`, where the stock is
    # merely not sellable but the location's demand still counts. Seeded by migration 443
    # for the ACTIVE `-BB/-IB/-IR/-NTC/-AM` bins and then CONFIG, like every other flag on
    # this row: an admin turns one on or off on the Warehouses screen. The site pools are
    # off - a pool is reached through `pool_warehouse_id`, never as an ownership group.
    # One predicate spells the test: `app.services.scm.planning_predicate`.
    fulfilment_planning = Column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    storage_zones = relationship("StorageZone", back_populates="warehouse")
    stock = relationship("Stock", back_populates="warehouse")
    stock_batches = relationship("StockBatch", back_populates="warehouse")
    spo_allocations = relationship("SPOAllocation", back_populates="warehouse")
    source_picking_lines = relationship("PickingLine", back_populates="source_warehouse", foreign_keys="[PickingLine.source_warehouse_id]")
    destination_picking_lines = relationship("PickingLine", back_populates="destination_warehouse", foreign_keys="[PickingLine.destination_warehouse_id]")
    
    __table_args__ = (
        Index("ix_warehouses_is_active", "is_active"),
        Index("ix_warehouses_manager_id", "manager_id"),
    )


class StorageZone(Base, CompanyScopedMixin):
    __tablename__ = "storage_zones"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    zone_code = Column(String(50), nullable=False)
    zone_name = Column(String(150), nullable=True)
    zone_type = Column(String(100), nullable=False)
    capacity = Column(Integer, default=0, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    warehouse = relationship("Warehouse", back_populates="storage_zones")
    spo_allocations = relationship("SPOAllocation", back_populates="storage_zone")
    
    __table_args__ = (
        Index("ix_storage_zones_warehouse_id", "warehouse_id"),
        Index("ix_storage_zones_zone_type", "zone_type"),
        Index("uq_storage_zones_warehouse_id_zone_code", "warehouse_id", "zone_code", unique=True),
    )


class Stock(Base, CompanyScopedMixin):
    __tablename__ = "stock"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(UUID(as_uuid=False), nullable=True)
    # `default=0` is applied by SQLAlchemy and so covers ORM inserts only. The migrated
    # database also carries a DB-level DEFAULT 0, which is what lets a raw
    # `INSERT INTO stock (...)` omit these columns. Without `server_default` here,
    # `create_all` built a schema with no default, so those raw inserts succeeded against
    # a migrated database and failed against a freshly created one. Declaring it keeps the
    # two paths behaving identically.
    quantity_on_hand = Column(Integer, default=0, server_default=text("0"), nullable=False)
    quantity_reserved = Column(Integer, default=0, server_default=text("0"), nullable=False)
    # DB-generated column: GENERATED ALWAYS AS (quantity_on_hand - quantity_reserved) STORED
    quantity_available = Column(Integer, Computed("(quantity_on_hand - quantity_reserved)"), nullable=False)
    quantity_damaged = Column(Integer, default=0, server_default=text("0"), nullable=False)
    reorder_point = Column(Integer, nullable=True)
    last_count_date = Column(Date, nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    product = relationship("Product", back_populates="stock")
    warehouse = relationship("Warehouse", back_populates="stock")

    @property
    def status(self) -> str:
        """Computed status: critical, low, normal, overstock (for API/frontend)."""
        avail = self.quantity_available or 0
        reorder = getattr(self.product, "reorder_level", None) if self.product else None
        reorder = (reorder if reorder is not None else 0) or 0
        if avail <= 0:
            return "critical"
        if reorder and avail < reorder:
            return "low"
        if reorder and avail > reorder * 2:
            return "overstock"
        return "normal"

    __table_args__ = (
        Index("ix_stock_product_id", "product_id"),
        Index("ix_stock_warehouse_id", "warehouse_id"),
        Index("uq_stock_product_id_warehouse_id", "product_id", "warehouse_id", unique=True),
    )


class StockLedger(Base, CompanyScopedMixin):
    __tablename__ = "stock_ledger"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    transaction_type = Column(String(50), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    previous_quantity = Column(Integer, nullable=False)
    new_quantity = Column(Integer, nullable=False)
    reference_type = Column(String(100), nullable=True)
    reference_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    product = relationship("Product")
    warehouse = relationship("Warehouse")

    __table_args__ = (
        Index("ix_stock_ledger_product_id", "product_id"),
        Index("ix_stock_ledger_warehouse_id", "warehouse_id"),
        Index("ix_stock_ledger_transaction_type", "transaction_type"),
        Index("ix_stock_ledger_created_at", "created_at"),
    )


class StockBatch(Base, CompanyScopedMixin):
    __tablename__ = "stock_batches"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    batch_code = Column(String(100), unique=True, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    manufactured_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=False)
    status = Column(String, default=BatchStatus.AVAILABLE.value, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    product = relationship("Product", back_populates="stock_batches")
    warehouse = relationship("Warehouse", back_populates="stock_batches")
    
    __table_args__ = (
        Index("ix_stock_batches_product_id", "product_id"),
        Index("ix_stock_batches_warehouse_id", "warehouse_id"),
        Index("ix_stock_batches_status", "status"),
        Index("ix_stock_batches_expiry_date", "expiry_date"),
    )
