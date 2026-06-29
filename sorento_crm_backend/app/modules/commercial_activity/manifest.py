"""Commercial activity module manifest for auto-discovery."""

MODULE_KEY = "commercial_activity"
DISPLAY_NAME = "Commercial activity plan"
DESCRIPTION = "Activity templates and hierarchical tasks on master quotations with reminders."
DEPENDENCIES = ["base", "commercial_core", "notifications"]
IS_CORE = False
VERSION = "1.0.0"

# Router intentionally NOT mounted: see commercial_core/manifest.py. The module
# code is restored only so migrations import and the app boots; the UI is gated
# off. To re-enable, restore routes.py from SRT-10 and set
# ROUTER_PREFIX = "/commercial-activity".
ROUTER_PREFIX = None
ROUTER_TAGS = ["commercial-activity"]
GUARD_KEY = "commercial_activity"
USE_API_KEY_GUARD = True
