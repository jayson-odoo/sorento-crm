"""Install / enable / disable orchestration for tenant modules."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.app_modules import AppModuleCatalog, TenantModule, ModuleInstallEvent
from app.modules.runtime.module_manifest import MODULE_MANIFEST, ALL_MODULE_KEYS
from app.modules.runtime.resolver import (
    resolve_install_plan,
    enabled_modules_blocking_disable,
    installed_modules_blocking_uninstall,
)
from app.services.error_handler import handle_validation_error, handle_conflict
from app.services.app_module_bundle_service import list_bundles_from_db, resolve_bundle_module_keys

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "__default__"


def _ensure_catalog_rows(db: Session) -> None:
    """Idempotent: insert missing catalog rows from manifest defaults (bootstrap only)."""
    existing = {row[0] for row in db.query(AppModuleCatalog.module_key).all()}
    for idx, key in enumerate(ALL_MODULE_KEYS):
        if key in existing:
            continue
        m = MODULE_MANIFEST[key]
        db.add(
            AppModuleCatalog(
                module_key=key,
                display_name=m.display_name,
                description=m.description,
                sort_order=str(idx).zfill(3),
                is_core=(key == "base"),
                dependencies=sorted(m.dependencies),
            )
        )
    db.commit()


def load_dependency_graph(db: Session) -> Dict[str, Set[str]]:
    """Dependency edges from app_modules_catalog (authoritative for install/disable logic)."""
    _ensure_catalog_rows(db)
    rows = db.query(AppModuleCatalog.module_key, AppModuleCatalog.dependencies).all()
    graph: Dict[str, Set[str]] = {}
    for mk, deps in rows:
        if deps is None:
            graph[mk] = set()
        elif isinstance(deps, list):
            graph[mk] = set(deps)
        else:
            graph[mk] = set(deps)
    return graph


def get_installed_module_keys(db: Session, tenant_id: str) -> Set[str]:
    rows = db.query(TenantModule.module_key).filter(TenantModule.tenant_id == tenant_id).all()
    return {r[0] for r in rows}


def get_enabled_module_keys(db: Session, tenant_id: str) -> Set[str]:
    rows = (
        db.query(TenantModule.module_key)
        .filter(TenantModule.tenant_id == tenant_id, TenantModule.enabled.is_(True))
        .all()
    )
    return {r[0] for r in rows}


def is_module_enabled(db: Session, tenant_id: str, module_key: str) -> bool:
    row = (
        db.query(TenantModule)
        .filter(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == module_key,
            TenantModule.enabled.is_(True),
        )
        .first()
    )
    return row is not None


def tenant_has_any_module_row(db: Session, tenant_id: str) -> bool:
    return (
        db.query(TenantModule.id).filter(TenantModule.tenant_id == tenant_id).first()
        is not None
    )


def log_event(
    db: Session,
    tenant_id: str,
    module_key: str,
    action: str,
    actor_user_id: Optional[str],
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    db.add(
        ModuleInstallEvent(
            tenant_id=tenant_id,
            module_key=module_key,
            action=action,
            actor_user_id=actor_user_id,
            detail=detail,
        )
    )


def install_modules(
    db: Session,
    tenant_id: str,
    module_keys: List[str],
    actor_user_id: Optional[str],
    action: str = "install",
) -> Dict[str, Any]:
    graph = load_dependency_graph(db)
    try:
        plan = resolve_install_plan(graph, module_keys)
    except ValueError as e:
        raise handle_validation_error(str(e))
    installed: List[str] = []
    for key in plan:
        row = (
            db.query(TenantModule)
            .filter(TenantModule.tenant_id == tenant_id, TenantModule.module_key == key)
            .first()
        )
        if row:
            if not bool(getattr(row, "enabled", False)):
                setattr(row, "enabled", True)
                log_event(db, tenant_id, key, "enable", actor_user_id, {"via": action})
            installed.append(key)
        else:
            db.add(
                TenantModule(
                    tenant_id=tenant_id,
                    module_key=key,
                    enabled=True,
                )
            )
            log_event(db, tenant_id, key, action, actor_user_id)
            installed.append(key)
    db.commit()
    return {"installed": installed, "plan": plan}


def install_bundle(
    db: Session,
    tenant_id: str,
    bundle_key: str,
    actor_user_id: Optional[str],
) -> Dict[str, Any]:
    keys = resolve_bundle_module_keys(db, bundle_key)
    result = install_modules(db, tenant_id, keys, actor_user_id, action="install")
    result["bundle"] = bundle_key
    log_event(
        db,
        tenant_id,
        bundle_key,
        "bundle_install",
        actor_user_id,
        {"modules": result.get("plan")},
    )
    db.commit()
    return result


def disable_module(
    db: Session,
    tenant_id: str,
    module_key: str,
    actor_user_id: Optional[str],
) -> Dict[str, Any]:
    graph = load_dependency_graph(db)
    if module_key not in graph:
        raise handle_validation_error(f"Unknown module: {module_key}")
    enabled = get_enabled_module_keys(db, tenant_id)
    conflicts = enabled_modules_blocking_disable(graph, module_key, enabled)
    if conflicts:
        raise handle_conflict(
            f"Cannot disable '{module_key}' while these modules are enabled: {', '.join(conflicts)}"
        )
    row = (
        db.query(TenantModule)
        .filter(TenantModule.tenant_id == tenant_id, TenantModule.module_key == module_key)
        .first()
    )
    if row:
        setattr(row, "enabled", False)
        log_event(db, tenant_id, module_key, "disable", actor_user_id)
        db.commit()
    return {"module_key": module_key, "enabled": False}


def enable_module(
    db: Session,
    tenant_id: str,
    module_key: str,
    actor_user_id: Optional[str],
) -> Dict[str, Any]:
    """Enable one module; auto-installs dependencies."""
    return install_modules(db, tenant_id, [module_key], actor_user_id, action="enable")


def uninstall_module(
    db: Session,
    tenant_id: str,
    module_key: str,
    actor_user_id: Optional[str],
    confirmation: str,
    purge_data: bool,
) -> Dict[str, Any]:
    """
    Remove tenant install row (module no longer installed). Optionally purge domain data.
    Cannot remove while any other module that still depends on this one is installed
    (even if that dependent is currently disabled).
    """
    if module_key == "base":
        raise handle_validation_error("Cannot uninstall the base module.")
    if confirmation.strip() != module_key:
        raise handle_validation_error(
            f"Confirmation must match the module key exactly (type «{module_key}»)."
        )

    graph = load_dependency_graph(db)
    if module_key not in graph:
        raise handle_validation_error(f"Unknown module: {module_key}")

    row = (
        db.query(TenantModule)
        .filter(TenantModule.tenant_id == tenant_id, TenantModule.module_key == module_key)
        .first()
    )
    if not row:
        raise handle_validation_error(
            f"Module '{module_key}' is not installed for this tenant (nothing to uninstall)."
        )

    installed = get_installed_module_keys(db, tenant_id)
    conflicts = installed_modules_blocking_uninstall(graph, module_key, installed)
    if conflicts:
        raise handle_conflict(
            f"Cannot uninstall '{module_key}' while these modules are still installed: {', '.join(conflicts)}"
        )

    rows_deleted: Optional[Dict[str, int]] = None
    if purge_data:
        from app.services.module_purge_service import purge_module_data

        try:
            rows_deleted = purge_module_data(db, module_key)
        except ValueError as e:
            raise handle_validation_error(str(e))

    db.delete(row)
    log_event(
        db,
        tenant_id,
        module_key,
        "uninstall",
        actor_user_id,
        detail={"purge_data": purge_data, "rows_deleted": rows_deleted or {}},
    )
    db.commit()
    return {
        "module_key": module_key,
        "installed": False,
        "enabled": False,
        "purge_data": purge_data,
        "rows_deleted": rows_deleted,
        "message": "Module uninstalled for this tenant.",
    }


def list_catalog_with_state(db: Session, tenant_id: str) -> List[Dict[str, Any]]:
    """List modules from DB catalog + tenant install/enabled flags."""
    _ensure_catalog_rows(db)
    enabled = get_enabled_module_keys(db, tenant_id)
    tenant_rows = {
        r.module_key: r
        for r in db.query(TenantModule).filter(TenantModule.tenant_id == tenant_id).all()
    }
    rows = (
        db.query(AppModuleCatalog)
        .order_by(AppModuleCatalog.sort_order, AppModuleCatalog.module_key)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        raw_deps = row.dependencies
        if raw_deps is None:
            deps_list: List[str] = []
        elif isinstance(raw_deps, list):
            deps_list = [str(d) for d in raw_deps]
        else:
            deps_list = [str(d) for d in raw_deps] if isinstance(raw_deps, (tuple, set)) else []
        tm = tenant_rows.get(row.module_key)
        installed = tm is not None
        is_on = tm is not None and bool(getattr(tm, "enabled", False))
        out.append(
            {
                "module_key": row.module_key,
                "display_name": row.display_name,
                "description": row.description or "",
                "dependencies": sorted(deps_list),
                "installed": installed,
                "enabled": is_on,
            }
        )
    return out


def list_bundles(db: Session) -> List[Dict[str, Any]]:
    """Preset bundles from DB (seeded defaults); see app_module_bundle_service."""
    return list_bundles_from_db(db)


def list_install_events(
    db: Session,
    tenant_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[List[ModuleInstallEvent], int]:
    """Recent install/enable/disable audit events for the tenant."""
    q = (
        db.query(ModuleInstallEvent)
        .filter(ModuleInstallEvent.tenant_id == tenant_id)
        .order_by(ModuleInstallEvent.created_at.desc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return rows, total
