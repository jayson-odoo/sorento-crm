"""Procurement module manifest."""
from __future__ import annotations

MODULE_KEY = "procurement"
DISPLAY_NAME = "Procurement management"
DESCRIPTION = "Suppliers, GRN, SPO, packing lists, purchase requests, stock inquiries."
DEPENDENCIES = ("base", "product", "inventory", "resources")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("procurement",)
GUARD_KEY = "procurement"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/procurement.py",
    "app/schemas/procurement.py",
    "app/api/v1/procurement/",
    "app/api/v1/incoming_stock.py",
    "app/services/procurement_service.py",
    "app/services/incoming_stock_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/procurement-management/",
)
EXPORT_PURGE_FN = None
