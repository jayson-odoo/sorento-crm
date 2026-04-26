"""SLA module manifest."""
from __future__ import annotations

MODULE_KEY = "sla"
DISPLAY_NAME = "SLA management"
DESCRIPTION = "SLA policies, conversation tracking, escalation."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("sla",)
GUARD_KEY = "sla"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/sla.py",
    "app/schemas/sla.py",
    "app/api/v1/sla/",
    "app/services/sla_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/sla-management/",
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_sla"
