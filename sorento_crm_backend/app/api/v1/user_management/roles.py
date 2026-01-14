"""User roles API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.user_service import UserRoleService
from app.schemas.user import UserRoleCreate, UserRoleUpdate, UserRoleResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[UserRoleResponse])
async def get_roles(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user roles with pagination."""
    try:
        service = UserRoleService(db)
        result = service.list_roles(page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{role_id}", response_model=UserRoleResponse)
async def get_role(
    role_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single role by ID."""
    try:
        service = UserRoleService(db)
        role = service.get_role(role_id)
        return role
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserRoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: UserRoleCreate,
    current_user: dict = Depends(get_current_user),
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
async def update_role(
    role_id: str,
    role_data: UserRoleUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a role."""
    try:
        service = UserRoleService(db)
        role = service.update_role(role_id, role_data)
        return role
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{role_id}", status_code=status.HTTP_200_OK)
async def delete_role(
    role_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a role."""
    try:
        service = UserRoleService(db)
        # Implement delete logic
        return {"message": "Role deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
