"""Workflow forms module manifest."""
from __future__ import annotations

MODULE_KEY = "workflow_forms"
DISPLAY_NAME = "Workflow forms"
DESCRIPTION = "Build approval-style forms with customizable fields, states, and notifications."
DEPENDENCIES = ("base", "notifications")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("workflow-forms",)
GUARD_KEY = "workflow_forms"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/workflow_forms.py",
    "app/schemas/workflow_forms.py",
    "app/api/v1/workflow_forms/",
    "app/services/workflow_forms_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/workflow-forms-management/",
)
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_workflow_forms"
