"""Email templates module manifest."""
from __future__ import annotations

MODULE_KEY = "email_templates"
DISPLAY_NAME = "Email Templates"
DESCRIPTION = "Designable email templates with Jinja2 variable placeholders, used by automation and ad-hoc sends."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("email-templates",)
GUARD_KEY = "email_templates"
USE_API_KEY_GUARD = False

EXPORT_FILES_BACKEND = (
    "app/models/email_template.py",
    "app/schemas/email_template.py",
    "app/api/v1/system/email_templates.py",
    "app/services/email_template_service.py",
    "app/services/templating.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/system-management/email-templates/",
)
