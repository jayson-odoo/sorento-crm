"""Public view links module manifest."""
from __future__ import annotations

MODULE_KEY = "public_view_links"
DISPLAY_NAME = "Public view links"
DESCRIPTION = "Tokenized public pages for shared entities."
DEPENDENCIES = ("base",)
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("public",)
GUARD_KEY = "public_view_links"
USE_API_KEY_GUARD = False

EXPORT_FILES_BACKEND = (
    "app/api/v1/public/",
    "app/services/view_token_service.py",
)
EXPORT_FILES_FRONTEND = ()
EXPORT_PURGE_FN = "app.services.module_purge_service.purge_public_view_links"
