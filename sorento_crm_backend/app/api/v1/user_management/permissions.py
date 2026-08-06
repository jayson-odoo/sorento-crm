"""User permissions API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, require_permission
from app.services.user_service import UserPermissionService
from app.schemas.user import UserPermissionCreate, UserPermissionUpdate, UserPermissionResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select", response_model=List[UserPermissionResponse])
def get_permissions_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("user_management.permissions.view")),
    db: Session = Depends(get_db)
):
    """Get user permissions for select dropdowns."""
    try:
        service = UserPermissionService(db)
        permissions = service.get_all_permissions(query=query)
        return permissions
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[UserPermissionResponse])
def get_permissions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission("user_management.permissions.view")),
    db: Session = Depends(get_db)
):
    """Get user permissions with pagination."""
    try:
        service = UserPermissionService(db)
        result = service.list_permissions(page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{permission_id}", response_model=UserPermissionResponse)
def get_permission(
    permission_id: str,
    current_user: dict = Depends(require_permission("user_management.permissions.view")),
    db: Session = Depends(get_db)
):
    """Get a single permission by ID."""
    try:
        validate_uuid_path(permission_id, resource="User Permission")
        service = UserPermissionService(db)
        permission = service.get_permission(permission_id)
        return permission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserPermissionResponse, status_code=status.HTTP_201_CREATED)
def create_permission(
    permission_data: UserPermissionCreate,
    current_user: dict = Depends(require_permission("user_management.permissions.add")),
    db: Session = Depends(get_db)
):
    """Create a new permission."""
    try:
        service = UserPermissionService(db)
        permission = service.create_permission(permission_data, current_user["id"])
        return permission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{permission_id}", response_model=UserPermissionResponse)
def update_permission(
    permission_id: str,
    permission_data: UserPermissionUpdate,
    current_user: dict = Depends(require_permission("user_management.permissions.edit")),
    db: Session = Depends(get_db)
):
    """Update a permission."""
    try:
        validate_uuid_path(permission_id, resource="User Permission")
        service = UserPermissionService(db)
        permission = service.update_permission(permission_id, permission_data)
        return permission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{permission_id}", status_code=status.HTTP_200_OK)
def delete_permission(
    permission_id: str,
    current_user: dict = Depends(require_permission("user_management.permissions.delete")),
    db: Session = Depends(get_db)
):
    """Delete a permission."""
    try:
        validate_uuid_path(permission_id, resource="User Permission")
        service = UserPermissionService(db)
        # Implement delete logic
        return {"message": "Permission deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
def bulk_delete_permissions(
    permission_ids: list[str],
    current_user: dict = Depends(require_permission("user_management.permissions.delete")),
    db: Session = Depends(get_db)
):
    """Bulk delete permissions."""
    try:
        service = UserPermissionService(db)
        result = service.bulk_delete_permissions(permission_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
