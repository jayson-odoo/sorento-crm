"""Inventory API routes."""
from fastapi import APIRouter
from app.api.v1.inventory import warehouses, stock, storage_zones, stock_batches, stock_ledger

router = APIRouter()

router.include_router(warehouses.router, prefix="/warehouses", tags=["warehouses"])
router.include_router(stock.router, prefix="/stock", tags=["stock"])
router.include_router(storage_zones.router, prefix="/storage-zones", tags=["storage-zones"])
router.include_router(stock_batches.router, prefix="/stock-batches", tags=["stock-batches"])
router.include_router(stock_ledger.router, prefix="/stock-ledger", tags=["stock-ledger"])