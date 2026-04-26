"""Complaints module manifest."""
from __future__ import annotations

MODULE_KEY = "complaints"
DISPLAY_NAME = "Complaint management"
DESCRIPTION = "Complaints and complaint attachments."
DEPENDENCIES = ("base", "resources")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("complaints",)
GUARD_KEY = "complaints"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/complaints.py",
    "app/schemas/complaints.py",
    "app/api/v1/complaints/",
    "app/services/complaints_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/complaint-management/",
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_complaints"
