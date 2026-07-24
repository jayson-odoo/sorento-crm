"""Map permission slugs to installable module keys for strict RBAC + module checks."""
from __future__ import annotations

from typing import Optional


def module_for_permission(permission_slug: str) -> Optional[str]:
    """
    Return module key that must be enabled for this permission, or None if not gated.
    """
    if not permission_slug:
        return None
    parts = permission_slug.split(".")
    if len(parts) < 2:
        return None
    prefix = parts[0]
    mapping = {
        "user_management": "base",
        "system": "base",
        "menu": "base",
        "dashboard": "base",
        "integration": "base",
        "master_data": "product",
        "order_management": "order",
        "inventory": "inventory",
        "procurement": "procurement",
        "marketing": "marketing",
        "complaint_management": "complaints",
        "sla_management": "sla",
        "forms": "forms",
        "workflow_forms": "workflow_forms",
        "resource": "resources",
        "audit": "audit",
    }
    return mapping.get(prefix)
