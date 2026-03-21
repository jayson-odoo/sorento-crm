"""Pydantic schemas for App Store / module runtime APIs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModuleStateResponse(BaseModel):
    module_key: str
    display_name: str
    description: str
    dependencies: List[str]
    installed: bool = Field(description="Tenant has a tenant_modules row (module is registered).")
    enabled: bool = Field(description="Row exists and enabled=true.")


class BundleInfoResponse(BaseModel):
    bundle_key: str
    display_name: str
    module_keys: List[str]


class BundleAdminResponse(BaseModel):
    """Bundle with optional sort hint (DB-backed presets)."""

    bundle_key: str
    display_name: str
    module_keys: List[str]
    sort_order: Optional[str] = None


class BundleCreateRequest(BaseModel):
    bundle_key: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Lowercase identifier, e.g. core_ops",
    )
    display_name: str = Field(..., min_length=1, max_length=255)
    module_keys: List[str] = Field(..., min_length=1)
    sort_order: Optional[str] = Field(None, max_length=16)


class BundleUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    module_keys: Optional[List[str]] = Field(None, min_length=1)
    sort_order: Optional[str] = Field(None, max_length=16)


class InstallModulesRequest(BaseModel):
    module_keys: Optional[List[str]] = None
    bundle_key: Optional[str] = Field(None, description="If set, installs all modules in the bundle")


class InstallModulesResponse(BaseModel):
    installed: List[str]
    plan: List[str]
    bundle: Optional[str] = None


class ModuleMutationResponse(BaseModel):
    module_key: str
    enabled: bool
    message: Optional[str] = None


class MyModulesResponse(BaseModel):
    tenant_id: str
    modules: List[ModuleStateResponse]
    bundles: List[BundleInfoResponse]
    module_guard_strict: bool


class ModuleInstallEventResponse(BaseModel):
    id: str
    tenant_id: str
    module_key: str
    action: str
    actor_user_id: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class ModuleInstallEventsListResponse(BaseModel):
    items: List[ModuleInstallEventResponse]
    total: int
    limit: int
    offset: int


class UninstallModuleRequest(BaseModel):
    """Typed confirmation + optional destructive data purge."""

    confirmation: str = Field(
        ...,
        min_length=1,
        description="Must match module_key exactly (case-sensitive).",
    )
    purge_data: bool = Field(
        False,
        description="If true, delete module business data where supported (irreversible).",
    )


class UninstallModuleResponse(BaseModel):
    module_key: str
    installed: bool = False
    enabled: bool = False
    purge_data: bool = False
    rows_deleted: Optional[Dict[str, int]] = None
    message: Optional[str] = None
