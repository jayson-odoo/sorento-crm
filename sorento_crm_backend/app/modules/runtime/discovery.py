"""
Auto-discovery for self-contained modules under app/modules/<key>/.

Each module may define:
  - manifest.py     (required for participation; exposes MODULE_KEY etc.)
  - models.py       (SQLAlchemy models - imported so Alembic sees tables)
  - schemas.py      (Pydantic schemas)
  - routes.py       (must expose `router: APIRouter`)
  - services.py     (business logic)
  - purge.py        (must expose `purge(db) -> Dict[str, int]`)
  - migrations/     (per-module Alembic version dir, branch-labeled)
  - frontend/       (JSON metadata for the FE; ignored by backend)
  - mcp/tools.json  (optional per-module MCP slice)

Discovery is additive - it does not replace any existing hardcoded registration.
Modules listed in `LEGACY_REGISTERED_PREFIXES` (those still wired manually in
app/api/v1/__init__.py) are skipped by router discovery to avoid duplicates.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


MODULES_PACKAGE = "app.modules"
RUNTIME_SUBPACKAGE = "runtime"


@dataclass(frozen=True)
class DiscoveredManifest:
    module_key: str
    display_name: str
    description: str
    dependencies: tuple[str, ...]
    is_core: bool = False
    router_prefix: Optional[str] = None
    router_tags: tuple[str, ...] = field(default_factory=tuple)
    guard_key: Optional[str] = None
    use_api_key_guard: bool = False
    version: str = "0.1.0"
    package: str = ""  # e.g. "app.modules.notifications"
    path: str = ""     # filesystem path of module dir


def _modules_root() -> Path:
    return Path(__file__).resolve().parent.parent  # app/modules/


def _iter_module_dirs() -> List[Path]:
    root = _modules_root()
    out: List[Path] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        if p.name.startswith("_") or p.name == RUNTIME_SUBPACKAGE or p.name == "__pycache__":
            continue
        out.append(p)
    return out


def _safe_import(dotted: str) -> Optional[ModuleType]:
    try:
        return importlib.import_module(dotted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Module discovery failed to import %s: %s", dotted, exc)
        return None


def _load_manifest(module_dir: Path) -> Optional[DiscoveredManifest]:
    manifest_file = module_dir / "manifest.py"
    if not manifest_file.exists():
        return None
    dotted = f"{MODULES_PACKAGE}.{module_dir.name}.manifest"
    mod = _safe_import(dotted)
    if mod is None:
        return None
    try:
        return DiscoveredManifest(
            module_key=getattr(mod, "MODULE_KEY"),
            display_name=getattr(mod, "DISPLAY_NAME", module_dir.name),
            description=getattr(mod, "DESCRIPTION", ""),
            dependencies=tuple(getattr(mod, "DEPENDENCIES", []) or []),
            is_core=bool(getattr(mod, "IS_CORE", False)),
            router_prefix=getattr(mod, "ROUTER_PREFIX", None),
            router_tags=tuple(getattr(mod, "ROUTER_TAGS", []) or []),
            guard_key=getattr(mod, "GUARD_KEY", None) or getattr(mod, "MODULE_KEY", None),
            use_api_key_guard=bool(getattr(mod, "USE_API_KEY_GUARD", False)),
            version=str(getattr(mod, "VERSION", "0.1.0")),
            package=f"{MODULES_PACKAGE}.{module_dir.name}",
            path=str(module_dir),
        )
    except AttributeError as exc:
        logger.warning("Manifest %s missing required attr: %s", dotted, exc)
        return None


def discover_manifests() -> Dict[str, DiscoveredManifest]:
    out: Dict[str, DiscoveredManifest] = {}
    for d in _iter_module_dirs():
        m = _load_manifest(d)
        if m is not None:
            out[m.module_key] = m
    return out


# Modules whose router is still mounted manually in app/api/v1/__init__.py.
# Auto-discovery skips these prefixes until cleanup phase removes the manual lines.
LEGACY_REGISTERED_PREFIXES = {
    "/audit", "/master-data", "/order-management", "/inventory", "/procurement",
    "/incoming-stock", "/marketing", "/forms-management", "/workflow-forms",
    "/complaints-management", "/sla-management", "/resource-management",
    "/user-management", "/integrations/logs",
    "/integration-management/integration-logs", "/notifications", "/list-query",
    "/auth", "/system", "/system/modules", "/external", "/public",
}


def discover_module_routers(api_router) -> List[str]:
    """
    Scan modules with a routes.py exposing `router` and mount on api_router.

    Returns list of module_keys that were registered.
    """
    from fastapi import Depends  # local to avoid import cycle at app boot

    from app.modules.runtime.guards import (
        require_module_enabled,
        require_module_enabled_with_api_key,
    )

    registered: List[str] = []
    manifests = discover_manifests()
    for key, mf in manifests.items():
        if mf.router_prefix is None:
            continue
        if mf.router_prefix in LEGACY_REGISTERED_PREFIXES:
            logger.debug("Skip legacy-registered router prefix: %s", mf.router_prefix)
            continue
        routes_mod = _safe_import(f"{mf.package}.routes")
        if routes_mod is None:
            continue
        router = getattr(routes_mod, "router", None)
        if router is None:
            logger.warning("Module %s routes.py has no `router` symbol", key)
            continue
        guard_factory = (
            require_module_enabled_with_api_key if mf.use_api_key_guard else require_module_enabled
        )
        api_router.include_router(
            router,
            prefix=mf.router_prefix,
            tags=list(mf.router_tags) or [key],
            dependencies=[Depends(guard_factory(mf.guard_key or key))],
        )
        registered.append(key)
        logger.info("Auto-mounted module router: %s -> %s", key, mf.router_prefix)
    return registered


def discover_module_models() -> List[str]:
    """Import models.py (or models/ package) from each module so Alembic sees tables.

    After every module is imported, the deferred relationship registry
    (``app.modules.runtime.relationship_registry``) is applied so any inverse
    relationships registered by modules attach to their target classes before
    the first ``configure_mappers()`` call.
    """
    imported: List[str] = []
    for d in _iter_module_dirs():
        if (d / "models.py").exists() or (d / "models" / "__init__.py").exists():
            dotted = f"{MODULES_PACKAGE}.{d.name}.models"
            if _safe_import(dotted) is not None:
                imported.append(d.name)

    # Apply any inverse relationships modules registered with the deferred
    # registry. Lazy imports avoid circular import via app.database.
    try:
        from app.database import Base
        from app.modules.runtime.relationship_registry import apply_pending
        apply_pending(Base.registry)
    except Exception:
        logger.exception("Failed to apply deferred relationship registry")
        raise

    return imported


def discover_module_purge_handlers() -> Dict[str, Callable]:
    """Return module_key -> purge fn from any module exposing purge.py with `purge`."""
    out: Dict[str, Callable] = {}
    for d in _iter_module_dirs():
        if not (d / "purge.py").exists():
            continue
        dotted = f"{MODULES_PACKAGE}.{d.name}.purge"
        mod = _safe_import(dotted)
        if mod is None:
            continue
        fn = getattr(mod, "purge", None)
        if callable(fn):
            mf = _load_manifest(d)
            key = mf.module_key if mf else d.name
            out[key] = fn
    return out


def discover_migration_dirs() -> List[str]:
    """Filesystem paths of per-module migrations directories."""
    out: List[str] = []
    for d in _iter_module_dirs():
        mig = d / "migrations"
        if mig.is_dir():
            out.append(str(mig))
    return out


def discover_mcp_tool_files() -> Dict[str, str]:
    """module_key -> path of mcp/tools.json if present."""
    out: Dict[str, str] = {}
    for d in _iter_module_dirs():
        candidate = d / "mcp" / "tools.json"
        if candidate.is_file():
            mf = _load_manifest(d)
            key = mf.module_key if mf else d.name
            out[key] = str(candidate)
    return out
