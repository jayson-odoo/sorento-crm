"""Inventory management schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WarehouseBase(BaseModel):
    warehouse_code: str
    warehouse_name: str
    location: Optional[str] = None
    manager_id: Optional[str] = None
    is_active: bool = True


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    location: Optional[str] = None
    manager_id: Optional[str] = None
    is_active: Optional[bool] = None


class WarehouseResponse(WarehouseBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    zones_count: Optional[int] = 0
    stock_count: Optional[int] = 0
    
    class Config:
        from_attributes = True


class StorageZoneBase(BaseModel):
    warehouse_id: str
    zone_code: str
    zone_name: Optional[str] = None
    zone_type: str
    capacity: Optional[int] = 0


class StorageZoneCreate(StorageZoneBase):
    pass


class StorageZoneUpdate(BaseModel):
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None
    capacity: Optional[int] = None


class StorageZoneResponse(StorageZoneBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class WarehouseSimple(BaseModel):
    id: str
    warehouse_name: str
    
    class Config:
        from_attributes = True

class StorageZoneTreeItem(StorageZoneResponse):
    warehouse: Optional[WarehouseSimple] = None
    children: Optional[list["StorageZoneTreeItem"]] = None

    class Config:
        from_attributes = True


class StockBase(BaseModel):
    product_id: str
    warehouse_id: str
    zone_id: Optional[str] = None
    quantity_on_hand: int = 0
    quantity_reserved: int = 0
    quantity_available: int = 0
    quantity_damaged: int = 0
    reorder_point: Optional[int] = None


class StockCreate(StockBase):
    pass


class StockUpdate(BaseModel):
    zone_id: Optional[str] = None
    quantity_on_hand: Optional[int] = None
    quantity_reserved: Optional[int] = None
    quantity_available: Optional[int] = None
    quantity_damaged: Optional[int] = None
    reorder_point: Optional[int] = None


class ProductSimple(BaseModel):
    id: str
    product_code: str
    product_name: str
    reorder_level: Optional[int] = None
    is_discontinued: bool = False

    class Config:
        from_attributes = True


class StockLedgerResponse(BaseModel):
    id: str
    product_id: str
    warehouse_id: str
    transaction_type: str
    quantity_change: int
    previous_quantity: int
    new_quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    product: Optional[ProductSimple] = None
    warehouse: Optional[WarehouseSimple] = None
    created_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class StockResponse(StockBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    warehouse: Optional[WarehouseSimple] = None
    status: Optional[str] = None  # 'low', 'critical', 'normal', 'overstock'
    
    class Config:
        from_attributes = True


class StockBatchBase(BaseModel):
    product_id: str
    warehouse_id: str
    batch_code: str
    quantity: int = 0
    manufactured_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    received_date: datetime
    status: str = "AVAILABLE"


class StockBatchCreate(StockBatchBase):
    pass


class StockBatchUpdate(BaseModel):
    quantity: Optional[int] = None
    manufactured_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    status: Optional[str] = None


class StockBatchResponse(StockBatchBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class StockDashboardResponse(BaseModel):
    total_skus: int
    total_quantity: int
    low_stock_alert_count: int
    overstock_warning_count: int
    stock_by_warehouse: list
    stock_by_category: list
    stock_movement_30_days: list
    low_stock_alerts: list


class BulkImportStockRequest(BaseModel):
    """Request schema for bulk import."""
    stock: list[dict]  # List of stock dictionaries from Excel
    validate_only: Optional[bool] = False  # If True, validate only (no import); return errors/warnings.


class BulkImportStockResponse(BaseModel):
    """Response schema for bulk import."""
    import_session_id: Optional[str] = None
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []
    warnings: list[dict] = []
