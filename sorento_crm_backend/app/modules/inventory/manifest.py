"""Inventory module manifest."""
from __future__ import annotations

MODULE_KEY = "inventory"
DISPLAY_NAME = "Inventory management"
DESCRIPTION = "Warehouses, stock, batches, ledger."
DEPENDENCIES = ("base", "product")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("inventory",)
GUARD_KEY = "inventory"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/inventory.py",
    "app/schemas/inventory.py",
    "app/api/v1/inventory/",
    "app/services/inventory_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/inventory-management/",
)
EXPORT_PURGE_FN = None
