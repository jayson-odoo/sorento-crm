"""Order module manifest."""
from __future__ import annotations

MODULE_KEY = "order"
DISPLAY_NAME = "Order management"
DESCRIPTION = "Orders, customers, order lines, tracking import."
DEPENDENCIES = ("base", "product", "inventory")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("order-management",)
GUARD_KEY = "order"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/order.py",
    "app/schemas/order.py",
    "app/api/v1/order_management/",
    "app/services/order_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/order-management/",
)
EXPORT_PURGE_FN = None
