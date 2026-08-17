"""
Bootstrap defaults for the App Store.

`MODULE_MANIFEST` / `ALL_MODULE_KEYS` are used only to:
- seed **new** rows into `app_modules_catalog` when a key is missing, and
- provide **fallback** bundle definitions (`MODULE_BUNDLES`) if `app_module_bundles` is empty.

At runtime, the API and install resolver read **display_name**, **description**,
**dependencies**, and **sort_order** from the database (`app_modules_catalog`).
Edit those columns in the DB to change what the UI shows and how installs resolve.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Set


@dataclass(frozen=True)
class ModuleManifest:
    module_key: str
    display_name: str
    description: str
    dependencies: FrozenSet[str]


# Dependency graph matches the approved plan (install order = topo sort).
_RAW: Dict[str, dict] = {
    "base": {
        "display_name": "Base",
        "description": "System management, user management, integrations foundation.",
        "dependencies": [],
    },
    "product": {
        "display_name": "Product management",
        "description": "Master data: products, categories, brands, UOM.",
        "dependencies": ["base"],
    },
    "resources": {
        "display_name": "Resource management",
        "description": "Attachments, directories, attachment types.",
        "dependencies": ["base"],
    },
    "inventory": {
        "display_name": "Inventory management",
        "description": "Warehouses, stock, batches, ledger.",
        "dependencies": ["base", "product"],
    },
    "order": {
        "display_name": "Order management",
        "description": "Orders, customers, order lines, tracking import.",
        "dependencies": ["base", "product", "inventory"],
    },
    "procurement": {
        "display_name": "Procurement management",
        "description": "Suppliers, GRN, SPO, packing lists, purchase requests, stock inquiries.",
        "dependencies": ["base", "product", "inventory", "resources"],
    },
    "marketing": {
        "display_name": "Marketing management",
        "description": "Promotions, campaigns, promotion attachments.",
        "dependencies": ["base", "product", "resources"],
    },
    "complaints": {
        "display_name": "Complaint management",
        "description": "Complaints and complaint attachments.",
        "dependencies": ["base", "resources"],
    },
    "sla": {
        "display_name": "SLA management",
        "description": "SLA policies, conversation tracking, escalation.",
        "dependencies": ["base"],
    },
    "forms": {
        "display_name": "Forms management",
        "description": "Dynamic forms, versions, submissions.",
        "dependencies": ["base", "resources"],
    },
    "workflow_forms": {
        "display_name": "Workflow forms",
        "description": "Build approval-style forms with customizable fields, states, and notifications.",
        "dependencies": ["base", "notifications"],
    },
    "notifications": {
        "display_name": "Notifications",
        "description": "In-app notifications and delivery.",
        "dependencies": ["base"],
    },
    "audit": {
        "display_name": "Audit",
        "description": "Audit logs and compliance views.",
        "dependencies": ["base"],
    },
    "public_view_links": {
        "display_name": "Public view links",
        "description": "Tokenized public pages for shared entities.",
        "dependencies": ["base"],
    },
    "dealer_kit": {
        "display_name": "Dealer Sales Kit",
        "description": "Catalogue page builder, product collections and brochure export.",
        "dependencies": ["base", "product", "resources"],
    },
    "scm": {
        "display_name": "Supply Chain & Inventory Optimisation",
        "description": "Reorder engine, net-position views, demand classification, supplier performance.",
        "dependencies": ["base", "product", "inventory", "order", "procurement"],
    },
    "projects": {
        "display_name": "Project sales",
        "description": (
            "Project registration and exclusivity, parties and stakeholders, "
            "pipeline, quotations, samples and demand forecast."
        ),
        # `product` for the brands a project pushes; `resources` for tender documents
        # and drawings. Deliberately NOT `order`: a Project PO is a customer's order
        # to us and lives in its own table (ADR-0002).
        "dependencies": ["base", "product", "resources"],
    },
}

MODULE_MANIFEST: Dict[str, ModuleManifest] = {
    k: ModuleManifest(
        module_key=k,
        display_name=v["display_name"],
        description=v.get("description") or "",
        dependencies=frozenset(v.get("dependencies") or []),
    )
    for k, v in _RAW.items()
}

ALL_MODULE_KEYS: List[str] = list(MODULE_MANIFEST.keys())


def manifest_dependency_graph() -> Dict[str, Set[str]]:
    """Bootstrap dependency graph (used for catalog seeding / tests). Runtime uses DB."""
    return {k: set(m.dependencies) for k, m in MODULE_MANIFEST.items()}

# Fallback only when DB table `app_module_bundles` has no rows (or unknown key without a row).
MODULE_BUNDLES: Dict[str, List[str]] = {
    "core_ops": ["base", "product", "inventory", "order", "resources"],
    # NB: unrelated to the removed commercial_core / commercial_activity modules —
    # this is the core-ops bundle plus marketing and procurement.
    "commercial_plus": [
        "base",
        "product",
        "inventory",
        "order",
        "resources",
        "marketing",
        "procurement",
    ],
    "service_desk": [
        "base",
        "resources",
        "complaints",
        "sla",
        "public_view_links",
        "notifications",
        "audit",
    ],
    "full_suite": list(ALL_MODULE_KEYS),
}


def get_manifest(module_key: str) -> ModuleManifest:
    if module_key not in MODULE_MANIFEST:
        raise KeyError(f"Unknown module_key: {module_key}")
    return MODULE_MANIFEST[module_key]


def merge_discovered_manifests() -> Dict[str, ModuleManifest]:
    """
    Merge file-based manifests (app/modules/<key>/manifest.py) into MODULE_MANIFEST.

    Discovered manifests take precedence over _RAW entries with the same key so a module
    that has been migrated to per-module package controls its own metadata.
    """
    try:
        from app.modules.runtime.discovery import discover_manifests
    except Exception:  # noqa: BLE001
        return MODULE_MANIFEST
    found = discover_manifests()
    for key, mf in found.items():
        MODULE_MANIFEST[key] = ModuleManifest(
            module_key=mf.module_key,
            display_name=mf.display_name,
            description=mf.description,
            dependencies=frozenset(mf.dependencies),
        )
    # Refresh ALL_MODULE_KEYS in place
    ALL_MODULE_KEYS.clear()
    ALL_MODULE_KEYS.extend(MODULE_MANIFEST.keys())
    return MODULE_MANIFEST
