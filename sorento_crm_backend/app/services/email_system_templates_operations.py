"""System email documents: operations mails (#1349). Registered by email_system_templates.py.

Each entry follows the same shape as the auth/users/SLA entries there: brand header,
heading, intro, facts, one button, footer. Producers call
`EmailTemplateService(db).render_code(code, context)` and pass context only.
"""
from __future__ import annotations

from app.services.email_system_templates_base import SystemTemplate

TEMPLATES: list[SystemTemplate] = []
