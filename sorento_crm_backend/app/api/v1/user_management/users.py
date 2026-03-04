"""Users API routes."""
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_current_user, require_permission, require_any_permission
from app.models.auth import VerificationToken
from app.models.user import SystemSetting
from app.schemas.common import ListResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserSelectResponse, UserRoleResponse
from app.services.error_handler import handle_internal_error
from app.services.notification_email import send_notification_email, _smtp_config_from_settings
from app.services.user_service import UserService, UserPermissionService

logger = logging.getLogger(__name__)


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None


class UserRolesUpdateRequest(BaseModel):
    role_ids: list[str]

router = APIRouter()


@router.get("/", response_model=ListResponse[UserResponse])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    roleId: Optional[str] = Query(None),
    respond_synced: Optional[str] = Query(None),
    trashed: Optional[str] = Query(None, description="exclude (default), only, or all"),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(require_permission("user_management.users.view")),
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
            trashed=trashed,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        users = result["data"]
        user_ids = [u.id for u in users]
        roles_map = service.get_roles_for_user_ids(user_ids)
        data = []
        for user in users:
            roles = roles_map.get(user.id, [])
            data.append({
                "id": user.id,
                "email": user.email,
                "name": user.name,
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
                "is_trashed": user.is_trashed,
                "roles": [{"id": r.id, "name": r.name} for r in roles],
                "superior_name": user.superior.name if user.superior else None,
            })
        return {
            "data": data,
            "pagination": result["pagination"],
            "empty": result["empty"],
        }
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
    current_user: dict = Depends(require_permission("user_management.users.view")),
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


class BulkUsersRequest(BaseModel):
    user_ids: list[str]
    action: str  # "delete" | "activate" | "deactivate"


@router.post("/bulk", status_code=status.HTTP_200_OK)
async def bulk_users_action(
    body: BulkUsersRequest,
    current_user: dict = Depends(require_any_permission(["user_management.users.edit", "user_management.users.delete"])),
    db: Session = Depends(get_db)
):
    """Bulk delete (soft), activate, or deactivate users."""
    try:
        service = UserService(db)
        perm_service = UserPermissionService(db)
        if body.action == "delete":
            if not perm_service.check_user_has_permission(current_user["id"], "user_management.users.delete"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for bulk delete")
            count = service.bulk_delete_users(body.user_ids)
            return {"message": f"{count} user(s) deleted", "count": count}
        if body.action == "activate":
            count = service.bulk_update_user_status(body.user_ids, "ACTIVE")
            return {"message": f"{count} user(s) activated", "count": count}
        if body.action == "deactivate":
            count = service.bulk_update_user_status(body.user_ids, "INACTIVE")
            return {"message": f"{count} user(s) deactivated", "count": count}
        if body.action == "permanent_delete":
            if not perm_service.check_user_has_permission(current_user["id"], "user_management.users.delete"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for permanent delete")
            count = service.bulk_permanent_delete_users(body.user_ids)
            return {"message": f"{count} trashed user(s) permanently deleted", "count": count}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")
    except HTTPException:
        raise
    except Exception as e:
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
        user_id = current_user["id"]
        user = service.get_user(user_id)
        roles = service.list_user_roles(user_id)
        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
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
            "roles": [{"id": r.id, "name": r.name} for r in roles],
            "superior_name": user.superior.name if user.superior else None,
        }
        return UserResponse(**user_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/me/permissions")
async def get_my_permissions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return current user's effective permission slugs (for frontend RBAC)."""
    try:
        perm_service = UserPermissionService(db)
        slugs = perm_service.get_user_permission_slugs(current_user["id"])
        return {"permissions": list(slugs)}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{user_id}/roles", response_model=list[UserRoleResponse])
async def get_user_roles(
    user_id: str,
    current_user: dict = Depends(require_permission("user_management.users.view")),
    db: Session = Depends(get_db)
):
    """List roles assigned to a user."""
    try:
        service = UserService(db)
        roles = service.list_user_roles(user_id)
        return roles
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{user_id}/roles", status_code=status.HTTP_200_OK)
async def set_user_roles(
    user_id: str,
    body: UserRolesUpdateRequest = Body(...),
    current_user: dict = Depends(require_permission("user_management.users.edit")),
    db: Session = Depends(get_db)
):
    """Replace user's role assignments with the given role_ids."""
    try:
        service = UserService(db)
        return service.set_user_roles(user_id, body.role_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(require_permission("user_management.users.view")),
    db: Session = Depends(get_db)
):
    """Get a single user by ID."""
    try:
        service = UserService(db)
        user = service.get_user(user_id)
        roles = service.list_user_roles(user_id)
        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
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
            "roles": [{"id": r.id, "name": r.name} for r in roles],
            "superior_name": user.superior.name if user.superior else None
        }
        return UserResponse(**user_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_permission("user_management.users.add")),
    db: Session = Depends(get_db)
):
    """Create a user and send an invitation email so they can set their password and sign in."""
    try:
        service = UserService(db)
        user = service.invite_user(user_data, invited_by_user_id=current_user["id"])

        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        verification_token = VerificationToken(
            identifier=user.id,
            token=token,
            expires=expires,
        )
        db.add(verification_token)
        db.commit()

        base_url = (app_settings.frontend_base_url or "").strip().rstrip("/")
        set_password_path = "/change-password"
        invite_link = f"{base_url}{set_password_path}?token={token}" if base_url else f"{set_password_path}?token={token}"
        subject = "You're invited to join the platform"
        body_text = (
            f"Hello{f', {user.name}' if user.name else ''},\n\n"
            f"You have been invited to join the platform. Set your password using the link below (valid for 7 days):\n\n"
            f"{invite_link}\n\n"
            f"After setting your password, you can sign in with your email and the new password."
        )
        body_html = (
            f"<p>Hello{f', {user.name}' if user.name else ''},</p>\n"
            f"<p>You have been invited to join the platform. "
            f"<a href=\"{invite_link}\">Set your password here</a> (link valid for 7 days).</p>\n"
            f"<p>After setting your password, you can sign in with your email and the new password.</p>"
        )
        try:
            sys_settings = db.query(SystemSetting).first()
            smtp_config = _smtp_config_from_settings(sys_settings) if sys_settings else None
            err = send_notification_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                smtp_config=smtp_config,
            )
            if err:
                logger.warning("Invitation email failed for %s: %s", user.email, err)
        except Exception as e:
            logger.warning("Invitation email error: %s", e)

        return user
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_permission("user_management.users.add")),
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
    current_user: dict = Depends(require_permission("user_management.users.edit")),
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
    permanent: bool = Query(False, description="If true, permanently delete (only allowed for trashed users)"),
    current_user: dict = Depends(require_permission("user_management.users.delete")),
    db: Session = Depends(get_db)
):
    """Soft-delete a user (default) or permanently delete if permanent=true and user is trashed."""
    try:
        service = UserService(db)
        if permanent:
            service.permanent_delete_user(user_id)
            return {"message": "User permanently deleted"}
        service.delete_user(user_id)
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{user_id}/restore", status_code=status.HTTP_200_OK)
async def restore_user(
    user_id: str,
    current_user: dict = Depends(require_permission("user_management.users.edit")),
    db: Session = Depends(get_db)
):
    """Restore a trashed user (set is_trashed=False)."""
    try:
        service = UserService(db)
        service.restore_user(user_id)
        return {"message": "User restored successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{user_id}/resend-invite", status_code=status.HTTP_200_OK)
async def resend_invite(
    user_id: str,
    current_user: dict = Depends(require_permission("user_management.users.edit")),
    db: Session = Depends(get_db)
):
    """Resend invitation email so the user can set their password and sign in."""
    try:
        service = UserService(db)
        user = service.get_user(user_id)

        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        verification_token = VerificationToken(
            identifier=user.id,
            token=token,
            expires=expires,
        )
        db.add(verification_token)
        db.commit()

        base_url = (app_settings.frontend_base_url or "").strip().rstrip("/")
        set_password_path = "/change-password"
        invite_link = f"{base_url}{set_password_path}?token={token}" if base_url else f"{set_password_path}?token={token}"
        subject = "You're invited to join the platform"
        body_text = (
            f"Hello{f', {user.name}' if user.name else ''},\n\n"
            f"You have been invited to join the platform. Set your password using the link below (valid for 7 days):\n\n"
            f"{invite_link}\n\n"
            f"After setting your password, you can sign in with your email and the new password."
        )
        body_html = (
            f"<p>Hello{f', {user.name}' if user.name else ''},</p>\n"
            f"<p>You have been invited to join the platform. "
            f"<a href=\"{invite_link}\">Set your password here</a> (link valid for 7 days).</p>\n"
            f"<p>After setting your password, you can sign in with your email and the new password.</p>"
        )
        try:
            sys_settings = db.query(SystemSetting).first()
            smtp_config = _smtp_config_from_settings(sys_settings) if sys_settings else None
            err = send_notification_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                smtp_config=smtp_config,
            )
            if err:
                logger.warning("Resend invitation email failed for %s: %s", user.email, err)
        except Exception as e:
            logger.warning("Resend invitation email error: %s", e)

        return {"message": f"Invitation link sent to {user.email}."}
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
