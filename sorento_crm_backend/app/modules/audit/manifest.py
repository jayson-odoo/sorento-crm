"""Audit module manifest."""
from __future__ import annotations

MODULE_KEY = "audit"
DISPLAY_NAME = "Audit"
DESCRIPTION = "Audit logs and compliance views."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"

# Legacy: app/api/v1/__init__.py mounts /audit. Keep None until cleanup.
ROUTER_PREFIX = None
ROUTER_TAGS = ("audit",)
GUARD_KEY = "audit"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/audit.py",
    "app/api/v1/audit/",
    "app/services/audit_service.py",
)
EXPORT_FILES_FRONTEND = ()
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_audit"
