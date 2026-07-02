"""Respond.io workspace admin routes (CRUD + set-default + select).

Mounted under ``/api/v1/system`` so the System Management menu can
manage workspaces (name, space_id, API key, base URL, default).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.respond_workspace import (
    RespondWorkspaceCreate,
    RespondWorkspaceResponse,
    RespondWorkspaceSelectItem,
    RespondWorkspaceUpdate,
)
from app.services.respond_workspace_service import RespondWorkspaceService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter(prefix="/respond-workspaces", tags=["respond-workspaces"])


@router.get("", response_model=list[RespondWorkspaceResponse])
def list_workspaces(
    _user: dict = Depends(require_permission("system.respond_workspaces.view")),
    db: Session = Depends(get_db),
):
    svc = RespondWorkspaceService(db)
    rows = svc.list_all()
    return [svc.to_response_dict(r) for r in rows]


@router.get("/select", response_model=list[RespondWorkspaceSelectItem])
def list_workspace_select(
    _user: dict = Depends(require_permission("system.respond_workspaces.view")),
    db: Session = Depends(get_db),
):
    """Active-only minimal list for dropdowns (workspace picker on contacts)."""
    svc = RespondWorkspaceService(db)
    rows = svc.list_active_select()
    return [svc.to_select_dict(r) for r in rows]


@router.get("/{workspace_id}", response_model=RespondWorkspaceResponse)
def get_workspace(
    workspace_id: str,
    _user: dict = Depends(require_permission("system.respond_workspaces.view")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(workspace_id, resource="Respond Workspace")
    svc = RespondWorkspaceService(db)
    row = svc.get(workspace_id)
    if not row:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
    return svc.to_response_dict(row)


@router.post("", response_model=RespondWorkspaceResponse, status_code=201)
def create_workspace(
    data: RespondWorkspaceCreate,
    _user: dict = Depends(require_permission("system.respond_workspaces.add")),
    db: Session = Depends(get_db),
):
    svc = RespondWorkspaceService(db)
    row = svc.create(data)
    return svc.to_response_dict(row)


@router.put("/{workspace_id}", response_model=RespondWorkspaceResponse)
def update_workspace(
    workspace_id: str,
    data: RespondWorkspaceUpdate,
    _user: dict = Depends(require_permission("system.respond_workspaces.edit")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(workspace_id, resource="Respond Workspace")
    svc = RespondWorkspaceService(db)
    row = svc.update(workspace_id, data)
    return svc.to_response_dict(row)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(
    workspace_id: str,
    _user: dict = Depends(require_permission("system.respond_workspaces.delete")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(workspace_id, resource="Respond Workspace")
    svc = RespondWorkspaceService(db)
    svc.delete(workspace_id)
    return None


@router.post("/{workspace_id}/set-default", response_model=RespondWorkspaceResponse)
def set_default_workspace(
    workspace_id: str,
    _user: dict = Depends(require_permission("system.respond_workspaces.set_default")),
    db: Session = Depends(get_db),
):
    svc = RespondWorkspaceService(db)
    row = svc.set_default(workspace_id)
    return svc.to_response_dict(row)
