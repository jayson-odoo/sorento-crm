"""Procurement API routes."""
from fastapi import APIRouter
from app.api.v1.procurement import suppliers, product_suppliers, packing_lists, grn, spo_allocations, picking_lines, stock_inquiries, purchase_requests

router = APIRouter()

router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
router.include_router(product_suppliers.router, prefix="/product-suppliers", tags=["product-suppliers"])
router.include_router(packing_lists.router, prefix="/packing-lists", tags=["packing-lists"])
router.include_router(grn.router, prefix="/grn", tags=["grn"])
router.include_router(spo_allocations.router, prefix="/spo-allocations", tags=["spo-allocations"])
router.include_router(picking_lines.router, prefix="/picking-lines", tags=["picking-lines"])
router.include_router(stock_inquiries.router, prefix="/stock-inquiries", tags=["stock-inquiries"])
router.include_router(purchase_requests.router, prefix="/purchase-requests", tags=["purchase-requests"])
