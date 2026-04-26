"""Commercial core module manifest for auto-discovery."""

MODULE_KEY = "commercial_core"
DISPLAY_NAME = "Commercial core"
DESCRIPTION = "Leads, projects, tenders, quotations, and commercial sales orders."
DEPENDENCIES = ["base", "order", "notifications"]
IS_CORE = False
VERSION = "1.0.0"

ROUTER_PREFIX = "/commercial"
ROUTER_TAGS = ["commercial"]
GUARD_KEY = "commercial_core"
USE_API_KEY_GUARD = True
