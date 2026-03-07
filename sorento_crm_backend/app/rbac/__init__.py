"""RBAC: permission registry and seeding."""
from app.rbac.permission_registry import PERMISSION_REGISTRY, sync_permissions

__all__ = ["PERMISSION_REGISTRY", "sync_permissions"]
