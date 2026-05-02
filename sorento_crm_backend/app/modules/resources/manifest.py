"""Resources module manifest."""
from __future__ import annotations

MODULE_KEY = "resources"
DISPLAY_NAME = "Resource management"
DESCRIPTION = "Attachments, directories, attachment types."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("resources",)
GUARD_KEY = "resources"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/resources.py",
    "app/models/entity_attachment.py",
    "app/schemas/resources.py",
    "app/api/v1/resources/",
    "app/services/resources_service.py",
    "app/services/s3_service.py",
    "app/services/r2_service.py",
    "app/services/storage_router.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/resource-management/",
)
EXPORT_PURGE_FN = None  # No automated purge handler today.
