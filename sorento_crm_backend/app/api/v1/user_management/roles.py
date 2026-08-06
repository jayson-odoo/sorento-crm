"""User roles API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, require_permission
from app.services.user_service import UserRoleService
from app.schemas.user import UserRoleCreate, UserRoleUpdate, UserRoleResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select", response_model=List[UserRoleResponse])
def get_roles_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("user_management.roles.view")),
    db: Session = Depends(get_db)
):
    """Get user roles for select dropdowns."""
    try:
        service = UserRoleService(db)
        roles = service.get_all_roles(query=query)
        return roles
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[UserRoleResponse])
def get_roles(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("user_management.roles.view")),
    db: Session = Depends(get_db)
):
    """Get user roles with pagination."""
    try:
        service = UserRoleService(db)
        result = service.list_roles(page=page, limit=limit, query=query)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{role_id}", response_model=UserRoleResponse)
def get_role(
    role_id: str,
    current_user: dict = Depends(require_permission("user_management.roles.view")),
    db: Session = Depends(get_db)
):
    """Get a single role by ID."""
    try:
        validate_uuid_path(role_id, resource="User Role")
        service = UserRoleService(db)
        role = service.get_role(role_id)
        return role
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserRoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: UserRoleCreate,
    current_user: dict = Depends(require_permission("user_management.roles.add")),
    db: Session = Depends(get_db)
):
    """Create a new role with permissions."""
    try:
        service = UserRoleService(db)
        role = service.create_role(role_data, current_user["id"])
        return role
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{role_id}", response_model=UserRoleResponse)
def update_role(
    role_id: str,
    role_data: UserRoleUpdate,
    current_user: dict = Depends(require_permission("user_management.roles.edit")),
    db: Session = Depends(get_db)
):
    """Update a role."""
    try:
        validate_uuid_path(role_id, resource="User Role")
        service = UserRoleService(db)
        role = service.update_role(role_id, role_data)
        return role
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{role_id}", status_code=status.HTTP_200_OK)
def delete_role(
    role_id: str,
    current_user: dict = Depends(require_permission("user_management.roles.delete")),
    db: Session = Depends(get_db)
):
    """Delete a role."""
    try:
        validate_uuid_path(role_id, resource="User Role")
        service = UserRoleService(db)
        return service.delete_role(role_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{role_id}/default", status_code=status.HTTP_200_OK)
def set_default_role(
    role_id: str,
    current_user: dict = Depends(require_permission("user_management.roles.edit")),
    db: Session = Depends(get_db)
):
    """Set a role as the default role."""
    try:
        validate_uuid_path(role_id, resource="User Role")
        service = UserRoleService(db)
        result = service.set_default_role(role_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
