"""Forms module manifest."""
from __future__ import annotations

MODULE_KEY = "forms"
DISPLAY_NAME = "Forms management"
DESCRIPTION = "Dynamic forms, versions, submissions."
DEPENDENCIES = ("base", "resources")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("forms",)
GUARD_KEY = "forms"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/forms.py",
    "app/schemas/forms.py",
    "app/api/v1/forms/",
    "app/services/forms_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/forms-management/",
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_forms"
