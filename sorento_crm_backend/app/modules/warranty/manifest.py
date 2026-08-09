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
# S7b gave the module an HTTP surface: the configuration editor at
# /api/v1/warranty-management/*. It is mounted by hand in app/api/v1/__init__.py
# (hence its presence in discovery.LEGACY_REGISTERED_PREFIXES); this constant is what
# the App Store's install / export path reads, and leaving it None would claim the
# module carries no routes while it serves four.
ROUTER_PREFIX = "/warranty-management"
ROUTER_TAGS = ("warranty",)
GUARD_KEY = "warranty"
USE_API_KEY_GUARD = True

EXPORT_FILES_BACKEND = (
    "app/models/warranty.py",
    "app/services/warranty_service.py",
    "app/services/warranty_assessment_service.py",
    "app/services/warranty_config_service.py",
    "app/schemas/warranty_config.py",
    "app/api/v1/warranty/__init__.py",
    "app/api/v1/warranty/policies.py",
    "app/api/v1/warranty/terms.py",
    "app/api/v1/warranty/kinds.py",
    "app/api/v1/warranty/kind_rules.py",
    "scripts/seed_warranty_policy_v15.py",
)
# The configuration screens (AC-P0a). A module that exports routes it has no screens
# for installs a surface nobody can reach.
EXPORT_FILES_FRONTEND = (
    "app/(protected)/warranty-management/page.tsx",
    "app/(protected)/warranty-management/policies/[id]/page.tsx",
    "app/(protected)/warranty-management/components/",
    "app/(protected)/warranty-management/hooks/",
    "app/(protected)/warranty-management/lib/",
    "app/(protected)/warranty-management/services/",
    "app/(protected)/warranty-management/types/",
)
EXPORT_PURGE_FN = "app.modules.warranty.purge.purge"
