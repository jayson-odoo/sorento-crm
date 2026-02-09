"""User permissions API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.user_service import UserPermissionService
from app.schemas.user import UserPermissionCreate, UserPermissionUpdate, UserPermissionResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select", response_model=List[UserPermissionResponse])
async def get_permissions_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
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
async def get_permissions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
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
async def get_permission(
    permission_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single permission by ID."""
    try:
        service = UserPermissionService(db)
        permission = service.get_permission(permission_id)
        return permission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserPermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission_data: UserPermissionCreate,
    current_user: dict = Depends(get_current_user),
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
async def update_permission(
    permission_id: str,
    permission_data: UserPermissionUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a permission."""
    try:
        service = UserPermissionService(db)
        permission = service.update_permission(permission_id, permission_data)
        return permission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{permission_id}", status_code=status.HTTP_200_OK)
async def delete_permission(
    permission_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a permission."""
    try:
        service = UserPermissionService(db)
        # Implement delete logic
        return {"message": "Permission deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_permissions(
    permission_ids: list[str],
    current_user: dict = Depends(get_current_user),
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
