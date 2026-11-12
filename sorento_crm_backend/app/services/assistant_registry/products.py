"""Products (`/master-data-management/products`), with their brand and category.

Cost price needs `products.cost.view` (SUPPLIER-COST-ACCESS, management 9 Nov 2026), the same permission
the product page and API now check: purchasing and management only.
"""
from __future__ import annotations

from app.models.product import Brand, Product, ProductCategory
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

COST_PRICE_VIEW = "products.cost.view"

register(
    EntityDef(
        key="brand",
        label="Brands",
        module="product",
        model=Brand,
        view_permission=None,
        fields={"code": FieldDef("Brand code", column="brand_code"), "name": FieldDef("Brand", column="brand_name")},
    ),
    EntityDef(
        key="category",
        label="Product categories",
        module="product",
        model=ProductCategory,
        view_permission=None,
        fields={
            "code": FieldDef("Category code", column="category_code"),
            "name": FieldDef("Category", column="category_name"),
        },
    ),
    EntityDef(
        key="product",
        label="Products",
        module="product",
        model=Product,
        view_permission="master_data.products.view",
        fields={
            "product_code": FieldDef("Product code"),
            "product_name": FieldDef("Product name"),
            "list_price": FieldDef("List price"),
            "cost_price": FieldDef("Cost price", permission=COST_PRICE_VIEW),
            "currency": FieldDef("Currency"),
            "is_active": FieldDef("Active"),
            "is_discontinued": FieldDef("Discontinued"),
            # LIST-PRICE-CHANGE-UI: the products list's "List price changed at" column.
            "list_price_changed_at": FieldDef("List price changed at", column="list_price_notified_at"),
            "created_at": FieldDef("Created at"),
        },
        relations={"brand": ("brand", "brand_id"), "category": ("category", "category_id")},
        name_by=("product_code", "product_name"),
        screen_path="/master-data-management/products/{id}",
        pages=("/master-data-management/products",),
        routes=("GET /api/v1/master-data/products/",),
        hint="products with brand and category",
    ),
)
