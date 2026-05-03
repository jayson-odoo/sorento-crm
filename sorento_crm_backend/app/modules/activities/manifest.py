"""Activities & Notes module manifest.

Generic per-entity activity feed + private notes + Respond.io message panel.
Other modules opt in by registering an adapter in app.services.activities_registry.
"""
from __future__ import annotations

MODULE_KEY = "activities"
DISPLAY_NAME = "Activities & Notes"
DESCRIPTION = "Per-entity activity feed, internal notes, and Respond.io conversation panel."
DEPENDENCIES = ("base", "resources")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("activities",)
GUARD_KEY = "activities"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/activities.py",
    "app/schemas/activities.py",
    "app/api/v1/activities/",
    "app/services/activities_service.py",
    "app/services/activities_registry.py",
)
EXPORT_FILES_FRONTEND = (
    "components/common/ActivitiesNotesPanel/",
)
