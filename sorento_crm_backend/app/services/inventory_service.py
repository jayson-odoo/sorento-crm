"""Inventory service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch
from app.models.product import Product
from app.schemas.inventory import (
    WarehouseCreate, WarehouseUpdate, StorageZoneCreate, StorageZoneUpdate,
    StockCreate, StockUpdate, StockBatchCreate, StockBatchUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


class WarehouseService:
    """Service for warehouse operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_warehouses(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List warehouses."""
        q = self.db.query(Warehouse)
        
        if query:
            q = q.filter(
                or_(
                    Warehouse.warehouse_code.ilike(f"%{query}%"),
                    Warehouse.warehouse_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        warehouses = q.offset(offset).limit(limit).all()
        
        # Add counts
        result = []
        for warehouse in warehouses:
            zones_count = self.db.query(func.count(StorageZone.id)).filter(
                StorageZone.warehouse_id == warehouse.id
            ).scalar() or 0
            
            stock_count = self.db.query(func.count(Stock.id)).filter(
                Stock.warehouse_id == warehouse.id
            ).scalar() or 0
            
            warehouse_dict = {
                **{c.name: getattr(warehouse, c.name) for c in warehouse.__table__.columns},
                "zones_count": zones_count,
                "stock_count": stock_count
            }
            result.append(warehouse_dict)
        
        return {
            "data": warehouses,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_warehouse(self, warehouse_id: str):
        """Get a warehouse by ID."""
        warehouse = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not warehouse:
            raise handle_not_found("Warehouse", warehouse_id)
        return warehouse
    
    def create_warehouse(self, warehouse_data: WarehouseCreate):
        """Create a new warehouse."""
        existing = self.db.query(Warehouse).filter(
            Warehouse.warehouse_code == warehouse_data.warehouse_code
        ).first()
        if existing:
            raise handle_conflict("Warehouse code already exists.")
        
        warehouse = Warehouse(**warehouse_data.model_dump())
        self.db.add(warehouse)
        self.db.commit()
        self.db.refresh(warehouse)
        return warehouse
    
    def update_warehouse(self, warehouse_id: str, warehouse_data: WarehouseUpdate):
        """Update a warehouse."""
        warehouse = self.get_warehouse(warehouse_id)
        
        update_data = warehouse_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(warehouse, key, value)
        
        self.db.commit()
        self.db.refresh(warehouse)
        return warehouse


class StorageZoneService:
    """Service for storage zone operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_zones(self, warehouse_id: Optional[str] = None, page: int = 1, limit: int = 50):
        """List storage zones."""
        q = self.db.query(StorageZone)
        
        if warehouse_id:
            q = q.filter(StorageZone.warehouse_id == warehouse_id)
        
        total = q.count()
        offset = (page - 1) * limit
        zones = q.offset(offset).limit(limit).all()
        
        return {
            "data": zones,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_zone(self, zone_id: str):
        """Get a storage zone by ID."""
        zone = self.db.query(StorageZone).filter(StorageZone.id == zone_id).first()
        if not zone:
            raise handle_not_found("Storage Zone", zone_id)
        return zone
    
    def create_zone(self, zone_data: StorageZoneCreate):
        """Create a new storage zone."""
        # Check unique constraint
        existing = self.db.query(StorageZone).filter(
            StorageZone.warehouse_id == zone_data.warehouse_id,
            StorageZone.zone_code == zone_data.zone_code
        ).first()
        if existing:
            raise handle_conflict("Zone code already exists for this warehouse.")
        
        zone = StorageZone(**zone_data.model_dump())
        self.db.add(zone)
        self.db.commit()
        self.db.refresh(zone)
        return zone
    
    def update_zone(self, zone_id: str, zone_data: StorageZoneUpdate):
        """Update a storage zone."""
        zone = self.get_zone(zone_id)
        
        update_data = zone_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(zone, key, value)
        
        self.db.commit()
        self.db.refresh(zone)
        return zone


class StockService:
    """Service for stock operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_stock(self, page: int = 1, limit: int = 50, warehouse_id: Optional[str] = None):
        """List stock with product and warehouse info."""
        q = self.db.query(Stock)
        
        if warehouse_id:
            q = q.filter(Stock.warehouse_id == warehouse_id)
        
        total = q.count()
        offset = (page - 1) * limit
        stock_items = q.offset(offset).limit(limit).all()
        
        return {
            "data": stock_items,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_stock(self, stock_id: str):
        """Get stock by ID."""
        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
        if not stock:
            raise handle_not_found("Stock", stock_id)
        return stock
    
    def get_stock_dashboard(self):
        """Get stock dashboard statistics."""
        # Count unique products
        total_skus = self.db.query(func.count(func.distinct(Stock.product_id))).scalar() or 0
        
        # Sum quantities from stock batches
        total_quantity_result = self.db.query(func.sum(StockBatch.quantity)).scalar()
        total_quantity = int(total_quantity_result) if total_quantity_result else 0
        
        return {
            "total_skus": total_skus,
            "total_quantity": total_quantity,
            "low_stock_alert_count": 0,
            "overstock_warning_count": 0,
            "stock_by_warehouse": [],
            "stock_by_category": [],
            "stock_movement_30_days": [],
            "low_stock_alerts": []
        }
    
    def get_stock_alerts(self):
        """Get low stock alerts."""
        # TODO: Implement based on reorder levels
        return []


class StockBatchService:
    """Service for stock batch operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_batches(
        self,
        page: int = 1,
        limit: int = 50,
        product_id: Optional[str] = None,
        warehouse_id: Optional[str] = None
    ):
        """List stock batches."""
        q = self.db.query(StockBatch)
        
        if product_id:
            q = q.filter(StockBatch.product_id == product_id)
        if warehouse_id:
            q = q.filter(StockBatch.warehouse_id == warehouse_id)
        
        total = q.count()
        offset = (page - 1) * limit
        batches = q.offset(offset).limit(limit).all()
        
        return {
            "data": batches,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_batch(self, batch_id: str):
        """Get a stock batch by ID."""
        batch = self.db.query(StockBatch).filter(StockBatch.id == batch_id).first()
        if not batch:
            raise handle_not_found("Stock Batch", batch_id)
        return batch
    
    def create_batch(self, batch_data: StockBatchCreate):
        """Create a new stock batch."""
        existing = self.db.query(StockBatch).filter(
            StockBatch.batch_code == batch_data.batch_code
        ).first()
        if existing:
            raise handle_conflict("Batch code already exists.")
        
        batch = StockBatch(**batch_data.model_dump())
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch
    
    def update_batch(self, batch_id: str, batch_data: StockBatchUpdate):
        """Update a stock batch."""
        batch = self.get_batch(batch_id)
        
        update_data = batch_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(batch, key, value)
        
        self.db.commit()
        self.db.refresh(batch)
        return batch
