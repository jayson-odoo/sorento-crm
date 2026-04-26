"""Notifications module manifest (file-based, supersedes _RAW entry)."""
from __future__ import annotations

MODULE_KEY = "notifications"
DISPLAY_NAME = "Notifications"
DESCRIPTION = "In-app notifications and delivery."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"

# Legacy path: app/api/v1/__init__.py still mounts the router manually under /notifications.
# Keep ROUTER_PREFIX = None so discover_module_routers() does NOT double-mount.
# Cleanup phase will flip this to "/notifications" and remove the manual line.
ROUTER_PREFIX = None
ROUTER_TAGS = ("notifications",)
GUARD_KEY = "notifications"
USE_API_KEY_GUARD = False

# File refs for module export (Phase 9). Walked relative to sorento_crm_backend/.
# Frontend assets are referenced relative to sorento_crm_frontend/.
EXPORT_FILES_BACKEND = (
    "app/models/notification.py",
    "app/schemas/notification.py",
    "app/api/v1/notifications/",
    "app/services/notification_service.py",
    "app/services/notification_email.py",
)
EXPORT_FILES_FRONTEND = (
    # Notifications surface in the header bell; no dedicated pages.
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_notifications"
