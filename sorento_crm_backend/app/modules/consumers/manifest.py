"""Consumers module manifest (AC-L1, fork 7).

Its own installable module, and neither of the two things it could lazily have
been. Not CORE: core is exactly one module today (`base`), consumer data would be
the first domain data in it, and a direct-selling tenant would never install it.
Not part of `warranty`: uninstalling the entitlement engine must leave the consumer
list and the receipts standing, which is the uninstall test that decided fork 7.

Not named `purchase` either (AC-L3). `procurement` already owns that word for
Sorento buying FROM suppliers, and a consumer purchase is a dealer selling TO a
homeowner. One word for both directions is a bug waiting for a join.

Dependencies are `base`, `product` and `order` exactly. `warranty` is deliberately
NOT among them: the dependency runs the other way, and declaring it both ways is a
cycle the install resolver refuses outright.
"""
from __future__ import annotations

MODULE_KEY = "consumers"
DISPLAY_NAME = "Consumer ledger"
DESCRIPTION = "Consumer profiles and the consumer purchase ledger."
DEPENDENCIES = ("base", "product", "order")
IS_CORE = False
VERSION = "1.0.0"
# No routers yet: S2b is the data layer. GUARD_KEY is declared anyway so the first
# router added is guarded by construction rather than by somebody remembering.
ROUTER_PREFIX = None
ROUTER_TAGS = ("consumers",)
GUARD_KEY = "consumers"
# n8n and the MCP server reach the ledger with X-API-Key, so the API-key-aware
# guard rather than the JWT-only one.
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/consumers.py",
    "app/services/consumer_service.py",
)
EXPORT_FILES_FRONTEND = ()
EXPORT_PURGE_FN = "app.modules.consumers.purge.purge"
