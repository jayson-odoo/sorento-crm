"""App Store: list / install / enable / disable modules (per-tenant)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
async def get_my_modules(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modules visible to the signed-in user (for menu gating)."""
    return _build_my_modules_response(db)


@router.get("/bundles", response_model=List[BundleAdminResponse])
async def get_module_bundles(
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    """List install presets (same data as in /me, with sort_order for admin UI)."""
    raw = list_bundles_from_db(db)
    return [BundleAdminResponse(**b) for b in raw]


@router.post("/bundles", response_model=BundleAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_module_bundle(
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
    keys = list(row.module_keys) if row.module_keys is not None else []
    return BundleAdminResponse(
        bundle_key=row.bundle_key,
        display_name=row.display_name,
        module_keys=keys,
        sort_order=row.sort_order,
    )


@router.put("/bundles/{bundle_key}", response_model=BundleAdminResponse)
async def update_module_bundle(
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
    keys = list(row.module_keys) if row.module_keys is not None else []
    return BundleAdminResponse(
        bundle_key=row.bundle_key,
        display_name=row.display_name,
        module_keys=keys,
        sort_order=row.sort_order,
    )


@router.delete("/bundles/{bundle_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module_bundle(
    bundle_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    delete_bundle(db, bundle_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events", response_model=ModuleInstallEventsListResponse)
async def get_module_install_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    rows, total = list_install_events(db, _tenant_id(), limit=limit, offset=offset)
    items = [
        ModuleInstallEventResponse(
            id=str(r.id),
            tenant_id=r.tenant_id,
            module_key=r.module_key,
            action=r.action,
            actor_user_id=r.actor_user_id,
            detail=r.detail,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return ModuleInstallEventsListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.post("/install", response_model=InstallModulesResponse)
async def install_modules_or_bundle(
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
async def enable_module_route(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    enable_module(db, _tenant_id(), module_key, current_user.get("id"))
    return ModuleMutationResponse(module_key=module_key, enabled=True, message="Module enabled")


@router.post("/{module_key}/disable", response_model=ModuleMutationResponse)
async def disable_module_route(
    module_key: str,
    current_user: dict = Depends(require_permission("system.modules.manage")),
    db: Session = Depends(get_db),
):
    disable_module(db, _tenant_id(), module_key, current_user.get("id"))
    return ModuleMutationResponse(module_key=module_key, enabled=False, message="Module disabled")


@router.post("/{module_key}/uninstall", response_model=UninstallModuleResponse)
async def uninstall_module_route(
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
