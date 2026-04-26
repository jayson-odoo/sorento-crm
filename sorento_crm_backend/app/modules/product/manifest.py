"""Product module manifest."""
from __future__ import annotations

MODULE_KEY = "product"
DISPLAY_NAME = "Product management"
DESCRIPTION = "Master data: products, categories, brands, UOM."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("master-data",)
GUARD_KEY = "product"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/product.py",
    "app/schemas/product.py",
    "app/api/v1/master_data/",
    "app/services/product_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/master-data-management/",
)
EXPORT_PURGE_FN = None
