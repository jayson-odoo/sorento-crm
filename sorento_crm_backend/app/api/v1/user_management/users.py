"""Users API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserSelectResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None

router = APIRouter()


@router.get("/", response_model=ListResponse[UserResponse])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    roleId: Optional[str] = Query(None),
    respond_synced: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get users with pagination, filtering, and sorting."""
    try:
        service = UserService(db)
        result = service.list_users(
            page=page,
            limit=limit,
            query=query,
            status=status,
            role_id=roleId,
            respond_synced=respond_synced,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_users: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise handle_internal_error(str(e))


@router.get("/select", response_model=list[UserSelectResponse])
async def get_users_select(
    query: Optional[str] = Query(None),
    respond_synced: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get users for select dropdowns."""
    try:
        service = UserService(db)
        users = service.list_users_select(query=query, respond_synced=respond_synced)
        return [UserSelectResponse.model_validate(user) for user in users]
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_users_select: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise handle_internal_error(str(e))


@router.get("/respond-users", status_code=status.HTTP_200_OK)
async def get_respond_users(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of Respond.io users for dropdown selection."""
    try:
        from app.services.integration_service import RespondClient
        
        client = RespondClient()
        users = client.list_users(limit=500)
        
        # Transform to a simple format for frontend
        formatted_users = []
        for user in users:
            user_id = user.get("id") or user.get("userId") or user.get("_id")
            name = user.get("name") or user.get("displayName") or user.get("email", "")
            email = user.get("email", "")
            
            if user_id:
                formatted_users.append({
                    "id": str(user_id),
                    "name": name or email or f"User {user_id}",
                    "email": email
                })
        
        return formatted_users
    except ValueError as e:
        # API key not configured
        return []
    except Exception as e:
        # Log error but return empty list to not break the form
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching Respond users: {str(e)}", exc_info=True)
        return []


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile."""
    try:
        service = UserService(db)
        user = service.get_user(current_user["id"])
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single user by ID."""
    try:
        service = UserService(db)
        user = service.get_user(user_id)
        # Convert to dict and add superior_name
        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role_id": user.role_id,
            "status": user.status,
            "country": user.country,
            "timezone": user.timezone,
            "respond_user_id": user.respond_user_id,
            "respond_synced": user.respond_synced,
            "superior_id": user.superior_id,
            "avatar": user.avatar,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_sign_in_at": user.last_sign_in_at,
            "role": {
                "id": user.role.id,
                "name": user.role.name
            } if user.role else None,
            "superior_name": user.superior.name if user.superior else None
        }
        return UserResponse(**user_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new user."""
    try:
        service = UserService(db)
        user = service.create_user(user_data)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a user."""
    try:
        service = UserService(db)
        user = service.update_user(user_id, user_data)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a user."""
    try:
        service = UserService(db)
        # Implement delete logic
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


class SyncRespondRequest(BaseModel):
    respond_user_id: Optional[str] = None

@router.post("/{user_id}/sync-respond", status_code=status.HTTP_200_OK)
async def sync_respond_user(
    user_id: str,
    request_data: Optional[SyncRespondRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync a user with Respond.io."""
    try:
        service = UserService(db)
        # Use respond_user_id from request if provided, otherwise use from database
        respond_user_id = request_data.respond_user_id if request_data and request_data.respond_user_id else None
        result = service.sync_respond_user(user_id, respond_user_id=respond_user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{user_id}/agents", status_code=status.HTTP_200_OK)
async def update_user_agent_accesses(
    user_id: str,
    agent_ids: list[str],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user agent accesses."""
    try:
        service = UserService(db)
        result = service.update_user_agent_accesses(user_id, agent_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


class UserAgentAccessCreate(BaseModel):
    agent_id: str
    is_allowed: bool = True
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


@router.post("/{user_id}/agents", status_code=status.HTTP_201_CREATED)
async def create_user_agent_access(
    user_id: str,
    access_data: UserAgentAccessCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a user agent access with allowed, valid_from, valid_to."""
    try:
        service = UserService(db)
        access = service.create_user_agent_access(
            user_id=user_id,
            agent_id=access_data.agent_id,
            is_allowed=access_data.is_allowed,
            valid_from=access_data.valid_from,
            valid_to=access_data.valid_to
        )
        return {
            "id": str(access.id),
            "user_id": access.user_id,
            "agent_id": str(access.agent_id),
            "is_allowed": access.is_allowed,
            "valid_from": access.valid_from.isoformat() if access.valid_from else None,
            "valid_to": access.valid_to.isoformat() if access.valid_to else None,
            "created_at": access.created_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/me/profile", response_model=UserResponse)
async def update_current_user_profile(
    profile_data: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile."""
    try:
        from app.schemas.user import UserUpdate
        
        # Create update data - only include fields that are provided
        update_dict = {}
        if profile_data.name is not None:
            update_dict["name"] = profile_data.name
        if profile_data.avatar is not None:
            update_dict["avatar"] = profile_data.avatar
        
        service = UserService(db)
        update_data = UserUpdate(**update_dict)
        user = service.update_user(current_user["id"], update_data)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
