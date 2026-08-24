"""Respond.io workspace admin routes (CRUD + set-default + select).

Mounted under ``/api/v1/system`` so the System Management menu can
manage workspaces (name, space_id, API key, base URL, default).
"""
from __future__ import annotations

import logging

import httpx
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/respond-workspaces", tags=["respond-workspaces"])

_IDEATION_PRODUCTS_PATH = "/ideation/intake/products"
_IDEATION_HTTP_TIMEOUT = 8.0


@router.get("/ideation-products")
def list_ideation_products(
    workspace_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    _user: dict = Depends(require_permission("system.respond_workspaces.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Proxy the shared-service software-product catalog for the Ideation-product
    dropdown. Degrades gracefully - ALWAYS 200 with ``{products, error}``; never 500.

    Resolution (live-preview wins over the saved workspace):
      - ``base_url`` + ``api_key`` query overrides (admin typed them but hasn't
        saved) are used verbatim when BOTH are present; else
      - ``workspace_id`` -> the stored ``ideation_shared_service_url`` +
        decrypted ``ideation_intake_api_key``.

    Returns ``{"products": [{id, name}], "error": <str|null>}``.
    """
    resolved_url = (base_url or "").strip() or None
    resolved_key = (api_key or "").strip() or None

    # Fall back to the saved workspace only when the live-preview pair is incomplete.
    if not (resolved_url and resolved_key) and workspace_id:
        svc = RespondWorkspaceService(db)
        row = svc.get(workspace_id)
        if row is None:
            return {"products": [], "error": "Workspace not found."}
        if not resolved_url:
            resolved_url = (getattr(row, "ideation_shared_service_url", None) or "").strip() or None
        if not resolved_key:
            resolved_key = svc.decrypt_ideation_api_key(row)

    if not resolved_url or not resolved_key:
        return {
            "products": [],
            "error": "Enter the Shared-service URL and Intake API key first.",
        }

    url = resolved_url.rstrip("/") + _IDEATION_PRODUCTS_PATH
    try:
        with httpx.Client(timeout=_IDEATION_HTTP_TIMEOUT) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {resolved_key}"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            return {"products": [], "error": "Shared-service rejected the Intake API key."}
        logger.warning("ideation-products upstream HTTP %s: %s", code, exc)
        return {"products": [], "error": f"Shared-service returned HTTP {code}."}
    except httpx.HTTPError as exc:
        logger.warning("ideation-products request failed: %s", exc)
        return {"products": [], "error": "Could not reach the Shared-service."}
    except ValueError as exc:
        logger.warning("ideation-products malformed body: %s", exc)
        return {"products": [], "error": "Shared-service returned a malformed response."}

    if not isinstance(data, list):
        return {"products": [], "error": "Shared-service returned an unexpected response."}

    products = [
        {"id": str(item["id"]), "name": str(item.get("name") or item["id"])}
        for item in data
        if isinstance(item, dict) and item.get("id")
    ]
    return {"products": products, "error": None}


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
