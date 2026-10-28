"""Procurement API routes."""
from fastapi import APIRouter, Depends
from app.api.v1._request_own_scope import purchase_request_own_scope, stock_inquiry_own_scope
from app.api.v1.procurement import suppliers, product_suppliers, packing_lists, grn, spo_allocations, picking_lines, stock_inquiries, purchase_requests, purchase_orders, cost_price_changes, new_product_applications

router = APIRouter()

router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
router.include_router(cost_price_changes.router, prefix="/cost-price-changes", tags=["cost-price-changes"])
router.include_router(product_suppliers.router, prefix="/product-suppliers", tags=["product-suppliers"])
router.include_router(packing_lists.router, prefix="/packing-lists", tags=["packing-lists"])
router.include_router(grn.router, prefix="/grn", tags=["grn"])
router.include_router(spo_allocations.router, prefix="/spo-allocations", tags=["spo-allocations"])
router.include_router(picking_lines.router, prefix="/picking-lines", tags=["picking-lines"])
# "Only theirs" for a user holding a form's view_own alone (PORTAL-P4-REQUESTS).
router.include_router(
    stock_inquiries.router,
    prefix="/stock-inquiries",
    tags=["stock-inquiries"],
    dependencies=[Depends(stock_inquiry_own_scope)],
)
router.include_router(new_product_applications.router, prefix="/new-product-applications", tags=["new-product-applications"])
router.include_router(
    purchase_requests.router,
    prefix="/purchase-requests",
    tags=["purchase-requests"],
    dependencies=[Depends(purchase_request_own_scope)],
)
router.include_router(purchase_orders.router, prefix="/purchase-orders", tags=["purchase-orders"])
