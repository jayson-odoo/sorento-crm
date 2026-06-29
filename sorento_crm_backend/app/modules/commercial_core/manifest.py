"""Commercial core module manifest for auto-discovery."""

MODULE_KEY = "commercial_core"
DISPLAY_NAME = "Commercial core"
DESCRIPTION = "Leads, projects, tenders, quotations, and commercial sales orders."
DEPENDENCIES = ["base", "order", "notifications"]
IS_CORE = False
VERSION = "1.0.0"

# Router intentionally NOT mounted: the commercial module code is restored only
# so the consolidated migrations (151/152) can import its model metadata and the
# app boots cleanly. The route/schema/service layer is not present and the UI
# stays gated off. To re-enable, restore the routes package from SRT-10 and set
# ROUTER_PREFIX = "/commercial".
ROUTER_PREFIX = None
ROUTER_TAGS = ["commercial"]
GUARD_KEY = "commercial_core"
USE_API_KEY_GUARD = True
