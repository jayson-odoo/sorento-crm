"""Tickets module manifest."""
from __future__ import annotations

MODULE_KEY = "tickets"
DISPLAY_NAME = "Ticketing System"
DESCRIPTION = "Internal Jira-style ticketing: list/kanban views, assignment, SLA, response/resolution."
DEPENDENCIES = ("base", "resources", "activities")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("tickets",)
GUARD_KEY = "tickets"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/tickets.py",
    "app/schemas/tickets.py",
    "app/api/v1/tickets/",
    "app/services/tickets_service.py",
)
EXPORT_FILES_FRONTEND = (
    "app/(protected)/ticket-management/",
)
