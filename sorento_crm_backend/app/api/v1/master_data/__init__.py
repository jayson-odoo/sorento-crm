"""Master data API routes."""
from fastapi import APIRouter
from app.api.v1.master_data import (
    products,
    brands,
    categories,
    units_of_measure,
    products_select,
    product_attachments,
    lookup_sets,
    lookup_eligibility,
    field_linkage,
    ai_extract_field,
    credit_terms,
    tax_codes,
    sales_agents,
    payment_methods,
    tax_entities,
    item_packages,
)

router = APIRouter()

router.include_router(products_select.router, prefix="/products", tags=["products"])
router.include_router(products.router, prefix="/products", tags=["products"])
router.include_router(brands.router, prefix="/brands", tags=["brands"])
router.include_router(categories.router, prefix="/product-categories", tags=["product-categories"])
router.include_router(units_of_measure.router, prefix="/units-of-measure", tags=["units-of-measure"])
router.include_router(credit_terms.router, prefix="/credit-terms", tags=["credit-terms"])
router.include_router(tax_codes.router, prefix="/tax-codes", tags=["tax-codes"])
router.include_router(sales_agents.router, prefix="/sales-agents", tags=["sales-agents"])
router.include_router(payment_methods.router, prefix="/payment-methods", tags=["payment-methods"])
router.include_router(tax_entities.router, prefix="/tax-entities", tags=["tax-entities"])
router.include_router(item_packages.router, prefix="/item-packages", tags=["item-packages"])
router.include_router(product_attachments.router, prefix="/product-attachments", tags=["product-attachments"])
router.include_router(lookup_sets.router, prefix="/lookup-sets", tags=["lookup-sets"])
router.include_router(lookup_eligibility.router, prefix="/lookup-eligibility", tags=["lookup-eligibility"])
router.include_router(
    field_linkage.router,
    prefix="/field-linkage-schema",
    tags=["field-linkage-schema"],
)
router.include_router(
    ai_extract_field.router,
    prefix="/ai-extract-field",
    tags=["ai-extract-field"],
)
