"""Stock balance snapshots — AutoCount report mirror (Slice 4).

Stock balance is a REPORT, not a document: a bare array with no DocKey, one row
per Item x Location x UOM x Batch, balances signed. So it does not fit the
idempotent-upsert masters/documents model. Instead each ingest is a *run*: a
header row plus its snapshot rows, appended so history is preserved and the UI
can compare runs over time.

Product/warehouse resolution is best-effort: an unresolvable ItemCode is NOT a
rejection (a report legitimately lists items that may not be synced) -- the raw
``item_code``/``location_code`` are always kept, and ``product_id``/
``warehouse_id`` are filled when they resolve.

Annotations live on the RUN header (the run is the annotatable unit); rows are
ephemeral and replaced every sync, so they carry no notes.
"""
from sqlalchemy import (
    Boolean,
    Column,
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


class StockBalanceSnapshotRun(Base):
    __tablename__ = "stock_balance_snapshot_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    captured_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    row_count = Column(Integer, nullable=False, default=0)
    source = Column(String(30), nullable=False, default="autocount", server_default="autocount")

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    rows = relationship(
        "StockBalanceSnapshot", back_populates="run", cascade="all, delete-orphan"
    )


class StockBalanceSnapshot(Base):
    __tablename__ = "stock_balance_snapshots"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("stock_balance_snapshot_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Resolution is best-effort: nullable FKs, raw codes always kept.
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
    item_code = Column(String(100), nullable=False)
    location_code = Column(String(100), nullable=True)
    uom = Column(String(100), nullable=True)
    batch_no = Column(String(100), nullable=True)
    # Balance is SIGNED (a report can show negatives). Numeric, never Integer.
    balance = Column(Numeric(15, 4), nullable=True)
    smallest_bal_qty = Column(Numeric(15, 4), nullable=True)
    standard_cost = Column(Numeric(15, 2), nullable=True)
    total_cost = Column(Numeric(15, 2), nullable=True)
    average_cost = Column(Numeric(15, 2), nullable=True)
    rate = Column(Numeric(15, 4), nullable=True)
    description = Column(String(255), nullable=True)

    run = relationship("StockBalanceSnapshotRun", back_populates="rows")
    product = relationship("Product", lazy="joined")

    @property
    def product_name(self):
        return self.product.product_name if self.product else None


Index("ix_stock_balance_snapshots_run", StockBalanceSnapshot.run_id)
Index("ix_stock_balance_snapshots_run_product", StockBalanceSnapshot.run_id, StockBalanceSnapshot.product_id)
