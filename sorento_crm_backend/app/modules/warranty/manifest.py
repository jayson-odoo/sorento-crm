"""Warranty module manifest (AC-L1, AC-L34).

S2 shipped four warranty TABLES and no module key at all, so until now the
entitlement engine was ungoverned by the App Store: it could be neither installed,
disabled nor purged, and it could not declare the dependency AC-L1 requires. That
was my error in S2 and this manifest is the correction, recorded rather than
quietly fixed.

The dependency runs ONE way. `warranty` needs `consumers` because an assessment is
computed from a purchase line and its date; `consumers` does not need `warranty`,
which is exactly why uninstalling the engine leaves the ledger and the consumer list
standing (AC-L2, the uninstall test that decided fork 7).

`complaints` is declared too, and honestly: `warranty_assessments` foreign-keys
`complaint_product_lines`, because a verdict is always about a specific reported
fault on a specific product. A module whose table points at another module's table
depends on it, whatever the plan says.
"""
from __future__ import annotations

MODULE_KEY = "warranty"
DISPLAY_NAME = "Warranty entitlement"
DESCRIPTION = "Warranty policies, terms, product kinds and stored warranty assessments."
DEPENDENCIES = ("base", "consumers", "complaints")
IS_CORE = False
VERSION = "1.0.0"
ROUTER_PREFIX = None
ROUTER_TAGS = ("warranty",)
GUARD_KEY = "warranty"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/warranty.py",
    "app/services/warranty_service.py",
    "app/services/warranty_assessment_service.py",
    "scripts/seed_warranty_policy_v15.py",
)
EXPORT_FILES_FRONTEND = ()
EXPORT_PURGE_FN = "app.modules.warranty.purge.purge"
