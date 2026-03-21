"""Module runtime: manifests, resolver, installer, guards."""

from app.modules.runtime.module_manifest import (
    ALL_MODULE_KEYS,
    MODULE_MANIFEST,
    MODULE_BUNDLES,
    get_manifest,
    manifest_dependency_graph,
)
from app.modules.runtime.resolver import (
    resolve_install_plan,
    get_reverse_dependents,
    transitive_dependencies,
    enabled_modules_blocking_disable,
    installed_modules_blocking_uninstall,
)
from app.modules.runtime.installer import load_dependency_graph
from app.modules.runtime.guards import (
    ensure_public_view_links_allowed,
    require_module_enabled,
    require_module_enabled_with_api_key,
    require_any_module_enabled,
    require_public_view_links_enabled,
)

__all__ = [
    "ALL_MODULE_KEYS",
    "MODULE_MANIFEST",
    "MODULE_BUNDLES",
    "get_manifest",
    "manifest_dependency_graph",
    "load_dependency_graph",
    "resolve_install_plan",
    "get_reverse_dependents",
    "transitive_dependencies",
    "enabled_modules_blocking_disable",
    "installed_modules_blocking_uninstall",
    "ensure_public_view_links_allowed",
    "require_module_enabled",
    "require_module_enabled_with_api_key",
    "require_any_module_enabled",
    "require_public_view_links_enabled",
]
