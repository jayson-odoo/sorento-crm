"""Master data API routes."""
from fastapi import APIRouter
from app.api.v1.master_data import products, brands, categories, units_of_measure, products_select, product_attachments

router = APIRouter()

router.include_router(products_select.router, prefix="/products", tags=["products"])
router.include_router(products.router, prefix="/products", tags=["products"])
router.include_router(brands.router, prefix="/brands", tags=["brands"])
router.include_router(categories.router, prefix="/product-categories", tags=["product-categories"])
router.include_router(units_of_measure.router, prefix="/units-of-measure", tags=["units-of-measure"])
router.include_router(product_attachments.router, prefix="/product-attachments", tags=["product-attachments"])
