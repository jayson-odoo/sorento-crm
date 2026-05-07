"""Automation module manifest."""
from __future__ import annotations

MODULE_KEY = "automation"
DISPLAY_NAME = "Automation"
DESCRIPTION = "Configurable rules that trigger emails (e.g. X days before promotion ends), runnable manually or on a daily schedule."
DEPENDENCIES = ("base", "email_templates", "marketing", "notifications")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("automation",)
GUARD_KEY = "automation"
USE_API_KEY_GUARD = False

EXPORT_FILES_BACKEND = (
    "app/models/automation.py",
    "app/schemas/automation.py",
    "app/api/v1/system/automation.py",
    "app/services/automation_service.py",
    "app/services/automation_triggers.py",
    "app/services/automation_recipients.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/system-management/automation/",
)
