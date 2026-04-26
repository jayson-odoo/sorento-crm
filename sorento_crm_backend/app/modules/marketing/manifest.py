"""Marketing module manifest."""
from __future__ import annotations

MODULE_KEY = "marketing"
DISPLAY_NAME = "Marketing management"
DESCRIPTION = "Promotions, campaigns, promotion attachments."
DEPENDENCIES = ("base", "product", "resources")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("marketing",)
GUARD_KEY = "marketing"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/marketing.py",
    "app/schemas/marketing.py",
    "app/api/v1/marketing/",
    "app/services/marketing_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/marketing-management/",
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_marketing"
