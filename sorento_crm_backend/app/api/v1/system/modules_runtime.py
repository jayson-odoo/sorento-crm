"""App Store: list / install / enable / disable modules (per-tenant)."""
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.modules.runtime.installer import (
    DEFAULT_TENANT_ID,
    disable_module,
    enable_module,
    install_bundle,
    install_modules,
    list_bundles,
    list_catalog_with_state,
    list_install_events,
    uninstall_module,
)
from app.schemas.app_modules import (
    BundleAdminResponse,
    BundleCreateRequest,
    BundleUpdateRequest,
    InstallModulesRequest,
    InstallModulesResponse,
    ModuleInstallEventResponse,
    ModuleInstallEventsListResponse,
    ModuleMutationResponse,
    ModuleStateResponse,
    MyModulesResponse,
    BundleInfoResponse,
    UninstallModuleRequest,
    UninstallModuleResponse,
)
from app.services.app_module_bundle_service import (
    create_bundle,
    delete_bundle,
    list_bundles_from_db,
    update_bundle,
)

router = APIRouter()


def _tenant_id() -> str:
    return DEFAULT_TENANT_ID


def _build_my_modules_response(db: Session) -> MyModulesResponse:
    from app.config import settings

    rows = list_catalog_with_state(db, _tenant_id())
    bundles_raw = list_bundles(db)
    return MyModulesResponse(
        tenant_id=_tenant_id(),
        modules=[ModuleStateResponse(**r) for r in rows],
        bundles=[
            BundleInfoResponse(
                bundle_key=b["bundle_key"],
                display_name=b["display_name"],
                module_keys=b["module_keys"],
            )
            for b in bundles_raw
        ],
        module_guard_strict=getattr(settings, "module_guard_strict", False),
    )


@router.get("/", response_model=MyModulesResponse)
@router.get("/me", response_model=MyModulesResponse)
def get_my_modules(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modules visible to the signed-in user (for menu gating)."""
    return _build_my_modules_response(db)


@router.get("/bundles", response_model=List[BundleAdminResponse])
def get_module_bundles(
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """List install presets (same data as in /me, with sort_order for admin UI)."""
    raw = list_bundles_from_db(db)
    return [BundleAdminResponse(**b) for b in raw]


@router.post("/bundles", response_model=BundleAdminResponse, status_code=status.HTTP_201_CREATED)
def create_module_bundle(
    body: BundleCreateRequest,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    row = create_bundle(
        db,
        bundle_key=body.bundle_key,
        display_name=body.display_name,
        module_keys=body.module_keys,
        sort_order=body.sort_order,
    )
    module_keys_raw = getattr(row, "module_keys", None)
    keys = list(module_keys_raw) if isinstance(module_keys_raw, list) else []
    return BundleAdminResponse(
        bundle_key=str(getattr(row, "bundle_key")),
        display_name=str(getattr(row, "display_name")),
        module_keys=keys,
        sort_order=(
            str(getattr(row, "sort_order"))
            if getattr(row, "sort_order", None) is not None
            else None
        ),
    )


@router.put("/bundles/{bundle_key}", response_model=BundleAdminResponse)
def update_module_bundle(
    bundle_key: str,
    body: BundleUpdateRequest,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    row = update_bundle(
        db,
        bundle_key,
        display_name=body.display_name,
        module_keys=body.module_keys,
        sort_order=body.sort_order,
    )
    module_keys_raw = getattr(row, "module_keys", None)
    keys = list(module_keys_raw) if isinstance(module_keys_raw, list) else []
    return BundleAdminResponse(
        bundle_key=str(getattr(row, "bundle_key")),
        display_name=str(getattr(row, "display_name")),
        module_keys=keys,
        sort_order=(
            str(getattr(row, "sort_order"))
            if getattr(row, "sort_order", None) is not None
            else None
        ),
    )


@router.delete("/bundles/{bundle_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module_bundle(
    bundle_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    delete_bundle(db, bundle_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events", response_model=ModuleInstallEventsListResponse)
def get_module_install_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    rows, total = list_install_events(db, _tenant_id(), limit=limit, offset=offset)
    items = [
        ModuleInstallEventResponse(
            id=str(r.id),
            tenant_id=str(getattr(r, "tenant_id")),
            module_key=str(getattr(r, "module_key")),
            action=str(getattr(r, "action")),
            actor_user_id=(
                str(getattr(r, "actor_user_id"))
                if getattr(r, "actor_user_id", None) is not None
                else None
            ),
            detail=(
                getattr(r, "detail")
                if isinstance(getattr(r, "detail", None), dict)
                else None
            ),
            created_at=(
                created_at.isoformat()
                if isinstance((created_at := getattr(r, "created_at", None)), datetime)
                else None
            ),
        )
        for r in rows
    ]
    return ModuleInstallEventsListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.post("/install", response_model=InstallModulesResponse)
def install_modules_or_bundle(
    body: InstallModulesRequest,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    tid = _tenant_id()
    uid = current_user.get("id")
    if body.bundle_key:
        result = install_bundle(db, tid, body.bundle_key, uid)
        return InstallModulesResponse(
            installed=result["installed"],
            plan=result["plan"],
            bundle=result.get("bundle"),
        )
    if not body.module_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide module_keys or bundle_key",
        )
    result = install_modules(db, tid, body.module_keys, uid, action="install")
    return InstallModulesResponse(installed=result["installed"], plan=result["plan"])


@router.post("/{module_key}/enable", response_model=ModuleMutationResponse)
def enable_module_route(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    enable_module(db, _tenant_id(), module_key, current_user.get("id"))
    return ModuleMutationResponse(module_key=module_key, enabled=True, message="Module enabled")


@router.post("/{module_key}/disable", response_model=ModuleMutationResponse)
def disable_module_route(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    disable_module(db, _tenant_id(), module_key, current_user.get("id"))
    return ModuleMutationResponse(module_key=module_key, enabled=False, message="Module disabled")


@router.post("/{module_key}/uninstall", response_model=UninstallModuleResponse)
def uninstall_module_route(
    module_key: str,
    body: UninstallModuleRequest,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """
    Remove tenant install row. Optionally purge domain data (typed confirmation required).
    """
    result = uninstall_module(
        db,
        _tenant_id(),
        module_key,
        current_user.get("id"),
        body.confirmation,
        body.purge_data,
    )
    return UninstallModuleResponse(
        module_key=result["module_key"],
        installed=result["installed"],
        enabled=result["enabled"],
        purge_data=result["purge_data"],
        rows_deleted=result.get("rows_deleted"),
        message=result.get("message"),
    )


# ---------------------------------------------------------------------------
# Phase 8 — module upload + activate + remove (zip drop-in)
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_module_zip(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """
    Accept a zip exported by another deployment, extract, run migrations.
    Caller must POST /{key}/activate afterward to install + enable for tenant.
    """
    from app.services.module_upload_service import (
        ModuleUploadError,
        install_uploaded_zip,
    )

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip file")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        tmp.write(await file.read())
        tmp.flush()
        tmp.close()
        result = install_uploaded_zip(Path(tmp.name))
    except ModuleUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # Re-merge manifests so the new catalog row appears via _ensure_catalog_rows on next call.
    from app.modules.runtime.module_manifest import merge_discovered_manifests
    merge_discovered_manifests()

    return {
        "module_key": result.module_key,
        "version": result.version,
        "status": result.status,
        "needs_frontend_rebuild": result.needs_frontend_rebuild,
        "restart_required": result.restart_required,
        "extracted_backend_files": result.extracted_backend_files,
        "extracted_frontend_files": result.extracted_frontend_files,
    }


@router.post("/{module_key}/activate", response_model=InstallModulesResponse)
def activate_uploaded_module(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """Install + enable a freshly uploaded module for the current tenant."""
    plan = install_modules(db, _tenant_id(), [module_key], current_user.get("id"))
    return InstallModulesResponse(installed=plan["installed"], plan=plan["plan"])


@router.get("/available")
def list_available_modules(
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """Modules in catalog with no tenant install row (uploaded but not activated)."""
    from app.models.app_modules import AppModuleCatalog, TenantModule

    installed_keys = {
        r[0]
        for r in db.query(TenantModule.module_key)
        .filter(TenantModule.tenant_id == _tenant_id())
        .all()
    }
    rows = (
        db.query(
            AppModuleCatalog.module_key,
            AppModuleCatalog.display_name,
            AppModuleCatalog.description,
            AppModuleCatalog.dependencies,
        )
        .filter(~AppModuleCatalog.module_key.in_(installed_keys or [""]))
        .all()
    )
    return [
        {
            "module_key": r[0],
            "display_name": r[1],
            "description": r[2],
            "dependencies": list(r[3] or []),
        }
        for r in rows
    ]


@router.delete("/{module_key}/remove")
def remove_module(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """Delete the on-disk module package. Refused while installed for any tenant."""
    from app.models.app_modules import TenantModule
    from app.services.module_upload_service import ModuleUploadError, remove_module_files

    has_install = (
        db.query(TenantModule).filter(TenantModule.module_key == module_key).first() is not None
    )
    if has_install:
        raise HTTPException(
            status_code=409,
            detail="Module still installed for at least one tenant — uninstall first.",
        )
    try:
        return remove_module_files(module_key)
    except ModuleUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Phase 9 — module export (download as zip)
# ---------------------------------------------------------------------------

@router.get("/{module_key}/export")
def export_module(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
):
    """Stream a zip containing the module's backend + frontend assets + metadata."""
    from app.services.module_export_service import (
        ModuleExportError,
        build_export_zip,
    )

    try:
        data, filename = build_export_zip(module_key)
    except ModuleExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
