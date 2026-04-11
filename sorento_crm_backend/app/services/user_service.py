"""User management service for business logic."""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import datetime
from app.models.user import (
    User,
    UserRole,
    UserRoleAssignment,
    UserPermission,
    UserRolePermission,
    SystemLog,
    UserQuickAccess,
)
from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    Team,
    TeamMember,
    AgentTeam,
    AgentTeamRoundRobinCursor,
)
from app.schemas.user import (
    UserCreate, UserUpdate, UserRoleCreate, UserRoleUpdate,
    UserPermissionCreate, UserPermissionUpdate, AccessAgentCreate, AccessAgentUpdate,
    ContactAgentAccessCreate, ContactAgentAccessUpdate,
    TeamCreate, TeamUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error
from app.services.integration_service import RespondClient


def _normalize_respond_user_id(value: Optional[str]) -> Optional[str]:
    """Return stripped string or None if empty."""
    if value is None:
        return None
    s = (str(value)).strip()
    return s if s else None


def _rr_user_id_key(value: Optional[object]) -> str:
    """
    Canonical string key for round-robin user id comparisons.
    Cursor.last_assigned_user_id is a string FK; TeamMember.user_id may come back as UUID or str
    from the driver — mixing them breaks list.index() and stuck rotation on index 0.
    """
    if value is None:
        return ""
    return str(value).strip()


class UserService:
    """Service for user operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def _has_table(self, table_name: str) -> bool:
        """Return True if table exists in current DB schema."""
        try:
            bind = self.db.get_bind()
            return sa_inspect(bind).has_table(table_name)
        except Exception:
            # If we can't inspect for any reason, assume it exists and let SQL errors surface elsewhere.
            return True

    def _prepare_user_for_hard_delete(self, user_id: str) -> None:
        """
        Best-effort cleanup before hard delete.

        Some tables reference users without ON DELETE CASCADE (e.g. system_logs, self-referential superior_id),
        so we clean those up explicitly to avoid 500 IntegrityError.
        """
        # Break self-referential FK (users.superior_id -> users.id)
        self.db.query(User).filter(User.superior_id == user_id).update(
            {"superior_id": None}, synchronize_session=False
        )

        # Remove non-cascading refs
        if self._has_table(SystemLog.__tablename__):
            self.db.query(SystemLog).filter(SystemLog.user_id == user_id).delete(
                synchronize_session=False
            )

        # Defensive deletes even if FK cascades exist (keeps behavior consistent if DB constraints differ)
        if self._has_table(UserRoleAssignment.__tablename__):
            self.db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete(
                synchronize_session=False
            )
        if self._has_table(TeamMember.__tablename__):
            self.db.query(TeamMember).filter(TeamMember.user_id == user_id).delete(
                synchronize_session=False
            )
        if self._has_table(UserQuickAccess.__tablename__):
            self.db.query(UserQuickAccess).filter(UserQuickAccess.user_id == user_id).delete(
                synchronize_session=False
            )

        # SET NULL modeled, but update defensively (cursor table might be missing FK constraint in some envs)
        if self._has_table(AgentTeamRoundRobinCursor.__tablename__):
            self.db.query(AgentTeamRoundRobinCursor).filter(
                AgentTeamRoundRobinCursor.last_assigned_user_id == user_id
            ).update({"last_assigned_user_id": None}, synchronize_session=False)
    
    def list_users(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        status: Optional[str] = None,
        role_id: Optional[str] = None,
        respond_synced: Optional[str] = None,
        trashed: Optional[str] = None,
        tier: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List users. trashed: 'exclude' (default), 'only', or 'all'. tier: comma-separated tier levels, e.g. '1,2,3'."""
        q = self.db.query(User)
        if trashed == "only":
            q = q.filter(User.is_trashed == True)
        elif trashed != "all":
            q = q.filter(User.is_trashed == False)
        filters = []
        if status and status != "all":
            filters.append(User.status == status)
        if role_id and role_id != "all":
            q = q.join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            q = q.filter(UserRoleAssignment.role_id == role_id)
            q = q.distinct()

        if respond_synced:
            filters.append(User.respond_synced == respond_synced)

        if tier and tier.strip():
            tier_values = []
            for s in tier.strip().split(","):
                s = s.strip()
                if s:
                    try:
                        tier_values.append(int(s))
                    except ValueError:
                        pass
            if tier_values:
                filters.append(User.tier.in_(tier_values))

        if query:
            filters.append(
                or_(
                    User.name.ilike(f"%{query}%"),
                    User.email.ilike(f"%{query}%")
                )
            )
        
        if filters:
            from sqlalchemy import and_
            q = q.filter(and_(*filters))
        
        sort_map = {
            "name": User.name,
            "status": User.status,
            "created_at": User.created_at,
            "createdAt": User.created_at,  # Support camelCase from frontend
            "last_sign_in_at": User.last_sign_in_at,
            "lastSignInAt": User.last_sign_in_at,  # Support camelCase from frontend
        }
        sort_column = sort_map.get(sort_field, User.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        # Count total (joinedload doesn't affect count)
        total = q.count()
        
        # Apply pagination and fetch with eager loading
        offset = (page - 1) * limit
        users = q.offset(offset).limit(limit).all()
        
        return {
            "data": users,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }

    def list_users_select(
        self,
        query: Optional[str] = None,
        respond_synced: Optional[str] = None,
        status: Optional[str] = None,
        trashed: str = "exclude",
    ):
        """List users for select dropdowns. Defaults to non-trashed only."""
        q = self.db.query(User)

        if trashed == "only":
            q = q.filter(User.is_trashed == True)
        elif trashed != "all":
            q = q.filter(User.is_trashed == False)

        filters = []
        if status and status != "all":
            filters.append(User.status == status)
        if respond_synced:
            filters.append(User.respond_synced == respond_synced)
        if query:
            filters.append(
                or_(
                    User.name.ilike(f"%{query}%"),
                    User.email.ilike(f"%{query}%")
                )
            )

        if filters:
            from sqlalchemy import and_
            q = q.filter(and_(*filters))

        return q.order_by(User.name.asc()).all()
    
    def get_user(self, user_id: str):
        """Get a user by ID."""
        user = self.db.query(User).options(
            joinedload(User.superior)
        ).filter(User.id == user_id).first()
        if not user:
            raise handle_not_found("User", user_id)
        return user

    def _users_with_respond_user_id(
        self, respond_user_id: str, exclude_user_id: Optional[str] = None
    ) -> list:
        """
        Return list of users (other than exclude_user_id) that have this respond_user_id.
        Compares using trimmed value so "971724" matches " 971724 " in DB.
        Each item is a dict with keys: id, name, email.
        """
        q = self.db.query(User).filter(
            User.respond_user_id.isnot(None),
            func.trim(User.respond_user_id) == respond_user_id,
        )
        if exclude_user_id:
            q = q.filter(User.id != exclude_user_id)
        users = q.all()
        return [
            {"id": u.id, "name": getattr(u, "name", None) or "", "email": getattr(u, "email", None) or ""}
            for u in users
        ]

    def _check_respond_user_id_unique(
        self, respond_user_id: str, exclude_user_id: Optional[str] = None
    ) -> None:
        """
        Raise handle_conflict if respond_user_id is already used by another user.
        Message includes which users have it (name and email).
        """
        existing = self._users_with_respond_user_id(respond_user_id, exclude_user_id=exclude_user_id)
        if not existing:
            return
        parts = [f"{u['name']} ({u['email']})".strip() or u["email"] or u["id"] for u in existing]
        msg = "Respond User ID is already used by: " + "; ".join(parts)
        raise handle_conflict(msg)

    def _user_create_data(self, user_data: UserCreate) -> dict:
        """Build User model dict from UserCreate, excluding role_ids."""
        d = user_data.model_dump(exclude={"role_ids"})
        return d

    def create_user(self, user_data: UserCreate):
        """Create a new user and assign roles via user_role_assignments."""
        existing = self.db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise handle_conflict("Email is already registered.")
        data = self._user_create_data(user_data)
        rid = _normalize_respond_user_id(data.get("respond_user_id"))
        if rid:
            self._check_respond_user_id_unique(rid, exclude_user_id=None)
            data["respond_user_id"] = rid
        user = User(**data)
        self.db.add(user)
        self.db.flush()
        role_ids = user_data.role_ids
        if not role_ids:
            default_role = self.db.query(UserRole).filter(UserRole.is_default == True).first()
            if default_role:
                role_ids = [default_role.id]
        for role_id in role_ids or []:
            role = self.db.query(UserRole).filter(UserRole.id == role_id).first()
            if role:
                self.db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
        self.db.commit()
        self.db.refresh(user)
        return user

    def invite_user(self, user_data: UserCreate, invited_by_user_id: str):
        """Create a user without a password and mark them as invited. Used for invitation flow."""
        existing = self.db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise handle_conflict("Email is already registered.")
        data = self._user_create_data(user_data)
        data["password"] = None
        data["invited_by_user_id"] = invited_by_user_id
        data["status"] = "INACTIVE"
        user = User(**data)
        self.db.add(user)
        self.db.flush()
        role_ids = user_data.role_ids
        if not role_ids:
            default_role = self.db.query(UserRole).filter(UserRole.is_default == True).first()
            if default_role:
                role_ids = [default_role.id]
        for role_id in role_ids or []:
            role = self.db.query(UserRole).filter(UserRole.id == role_id).first()
            if role:
                self.db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: str, user_data: UserUpdate):
        """Update a user."""
        import logging
        logger = logging.getLogger(__name__)
        
        user = self.get_user(user_id)
        
        # Get all fields that were explicitly set in the request
        update_data = user_data.model_dump(exclude_unset=True)
        logger.info(f"Updating user {user_id} with data: {update_data}")
        
        # Enforce Respond User ID uniqueness before applying any updates
        if "respond_user_id" in update_data:
            rid = _normalize_respond_user_id(update_data["respond_user_id"])
            if rid:
                self._check_respond_user_id_unique(rid, exclude_user_id=user_id)
        
        # Convert empty strings to None for optional fields to avoid foreign key violations
        optional_fields = ['superior_id', 'respond_user_id', 'country', 'timezone', 'avatar', 'tier', 'contact_number']
        
        # Log what we received
        logger.info(f"Received update_data keys: {list(update_data.keys())}")
        logger.info(f"Received update_data: {update_data}")
        
        for key, value in update_data.items():
            logger.info(f"Processing field '{key}' with value: {repr(value)} (type: {type(value).__name__})")
            if key in optional_fields and value == '':
                setattr(user, key, None)
                logger.info(f"✓ Set {key} = None (converted from empty string)")
            elif value is None and key in optional_fields:
                setattr(user, key, None)
                logger.info(f"✓ Set {key} = None (explicit None)")
            elif value is None:
                logger.warning(f"⚠ Skipping {key} (None value for non-optional field)")
            elif key == "respond_user_id":
                setattr(user, key, _normalize_respond_user_id(value))
                logger.info(f"✓ Set {key} = {repr(_normalize_respond_user_id(value))} (normalized)")
            else:
                setattr(user, key, value)
                logger.info(f"✓ Set {key} = {repr(value)}")
        
        logger.info(f"Before commit - respond_user_id: {user.respond_user_id}, superior_id: {user.superior_id}")
        self.db.commit()
        self.db.refresh(user)
        logger.info(f"After commit - respond_user_id: {user.respond_user_id}, superior_id: {user.superior_id}")
        return user

    def delete_user(self, user_id: str) -> None:
        """Soft-delete a user (set is_trashed=True)."""
        user = self.get_user(user_id)
        setattr(user, "is_trashed", True)
        self.db.commit()

    def restore_user(self, user_id: str) -> None:
        """Restore a trashed user (set is_trashed=False)."""
        user = self.get_user(user_id)
        setattr(user, "is_trashed", False)
        self.db.commit()

    def permanent_delete_user(self, user_id: str) -> None:
        """Permanently delete a user. Only allowed when user is trashed."""
        user = self.get_user(user_id)
        if not bool(getattr(user, "is_trashed", False)):
            raise handle_conflict("Only trashed users can be permanently deleted. Trash the user first.")
        if getattr(user, "is_protected", False):
            raise handle_conflict("Protected users cannot be permanently deleted.")
        self._prepare_user_for_hard_delete(str(getattr(user, "id")))
        self.db.delete(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise handle_conflict("Cannot permanently delete user because it is referenced by other records.")

    def bulk_delete_users(self, user_ids: list[str]) -> int:
        """Soft-delete multiple users. Returns count of deleted."""
        if not user_ids:
            return 0
        count = self.db.query(User).filter(
            User.id.in_(user_ids),
            User.is_trashed == False,
        ).update({"is_trashed": True}, synchronize_session=False)
        self.db.commit()
        return count

    def bulk_update_user_status(self, user_ids: list[str], status: str) -> int:
        """Set status for multiple users. Returns count updated."""
        if not user_ids:
            return 0
        count = self.db.query(User).filter(
            User.id.in_(user_ids),
            User.is_trashed == False,
        ).update({"status": status}, synchronize_session=False)
        self.db.commit()
        return count

    def bulk_permanent_delete_users(self, user_ids: list[str]) -> int:
        """Permanently delete users that are trashed. Returns count deleted."""
        if not user_ids:
            return 0
        users = self.db.query(User).filter(
            User.id.in_(user_ids),
            User.is_trashed == True,
        ).all()
        count = 0
        for user in users:
            if getattr(user, "is_protected", False):
                continue
            self._prepare_user_for_hard_delete(str(getattr(user, "id")))
            self.db.delete(user)
            count += 1
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise handle_conflict("Cannot permanently delete one or more users because they are referenced by other records.")
        return count

    def sync_respond_user(self, user_id: str, respond_user_id: Optional[str] = None) -> dict:
        """Sync user with Respond.io and update respond_synced status."""
        user = self.get_user(user_id)
        # Use provided respond_user_id or fall back to database value
        respond_id = _normalize_respond_user_id(respond_user_id) or _normalize_respond_user_id(
            getattr(user, "respond_user_id", None)
        )
        # Check for None, empty string, or falsy values
        if respond_id is None or respond_id.strip() == "":
            raise handle_conflict("Respond user ID is required for sync.")
        
        # If respond_user_id was provided and different from database, check uniqueness then save
        if respond_user_id and respond_user_id != user.respond_user_id:
            rid = _normalize_respond_user_id(respond_user_id)
            if rid:
                self._check_respond_user_id_unique(rid, exclude_user_id=user_id)
            setattr(user, "respond_user_id", rid or respond_user_id)
            self.db.commit()
            self.db.refresh(user)

        client = RespondClient()
        payload = client.get_user_by_id(respond_id)
        email = (
            payload.get("email")
            or payload.get("data", {}).get("email")
            or payload.get("user", {}).get("email")
        )

        if not email:
            setattr(user, "respond_synced", "failed")
            self.db.commit()
            self.db.refresh(user)
            return {"status": "failed", "message": "Respond user email not found."}

        if email.strip().lower() == user.email.strip().lower():
            setattr(user, "respond_synced", "successful")
            self.db.commit()
            self.db.refresh(user)
            return {"status": "successful", "message": "Respond user synced successfully."}

        setattr(user, "respond_synced", "failed")
        self.db.commit()
        self.db.refresh(user)
        return {"status": "failed", "message": "Respond email does not match system email."}

    def list_user_roles(self, user_id: str) -> list:
        """List roles assigned to a user (from user_role_assignments)."""
        self.get_user(user_id)  # raise if not found
        assignments = (
            self.db.query(UserRoleAssignment)
            .filter(UserRoleAssignment.user_id == user_id)
            .all()
        )
        if not assignments:
            return []
        role_ids = [a.role_id for a in assignments]
        return self.db.query(UserRole).filter(UserRole.id.in_(role_ids)).all()

    def get_roles_for_user_ids(self, user_ids: list[str]) -> dict:
        """Return map user_id -> list of UserRole for the given user ids."""
        if not user_ids:
            return {}
        assignments = (
            self.db.query(UserRoleAssignment)
            .filter(UserRoleAssignment.user_id.in_(user_ids))
            .all()
        )
        role_ids = list({a.role_id for a in assignments})
        roles_by_id = {r.id: r for r in self.db.query(UserRole).filter(UserRole.id.in_(role_ids)).all()}
        out = {uid: [] for uid in user_ids}
        for a in assignments:
            r = roles_by_id.get(a.role_id)
            a_user_id = str(getattr(a, "user_id"))
            if r and a_user_id in out:
                out[a_user_id].append(r)
        return out

    def set_user_roles(self, user_id: str, role_ids: list[str]) -> dict:
        """Replace user's role assignments with the given role_ids."""
        self.get_user(user_id)
        self.db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete(
            synchronize_session=False
        )
        self.db.flush()
        for role_id in role_ids or []:
            role = self.db.query(UserRole).filter(UserRole.id == role_id).first()
            if role:
                self.db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        self.db.commit()
        return {"message": "User roles updated successfully"}


class UserRoleService:
    """Service for user role operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_all_roles(self, query: Optional[str] = None):
        """Get all roles for select dropdowns (no pagination)."""
        q = self.db.query(UserRole).filter(UserRole.is_trashed == False)
        
        if query:
            q = q.filter(
                (UserRole.name.ilike(f"%{query}%")) |
                (UserRole.slug.ilike(f"%{query}%"))
            )
        
        roles = q.order_by(UserRole.name).all()
        return roles
    
    def list_roles(self, page: int = 1, limit: int = 50):
        """List user roles with permissions loaded."""
        q = self.db.query(UserRole).options(
            joinedload(UserRole.permissions).joinedload(UserRolePermission.permission)
        )
        total = q.count()
        offset = (page - 1) * limit
        roles = q.offset(offset).limit(limit).all()
        return {
            "data": roles,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }

    def get_role(self, role_id: str, with_permissions: bool = True):
        """Get a role by ID, optionally loading permissions."""
        query = self.db.query(UserRole)
        if with_permissions:
            query = query.options(
                joinedload(UserRole.permissions).joinedload(UserRolePermission.permission)
            )
        role = query.filter(UserRole.id == role_id).first()
        if not role:
            raise handle_not_found("User Role", role_id)
        return role
    
    def create_role(self, role_data: UserRoleCreate, created_by: str):
        """Create a new role with permissions."""
        # Check uniqueness
        existing_slug = self.db.query(UserRole).filter(UserRole.slug == role_data.slug).first()
        existing_name = self.db.query(UserRole).filter(UserRole.name == role_data.name).first()
        if existing_slug or existing_name:
            raise handle_conflict("Name and slug must be unique")
        
        role_dict = role_data.model_dump(exclude={"permissions"})
        role_dict["created_by_user_id"] = created_by
        role = UserRole(**role_dict)
        self.db.add(role)
        self.db.flush()
        
        # Create permission associations if provided
        if role_data.permissions:
            for permission_id in role_data.permissions:
                role_permission = UserRolePermission(
                    role_id=role.id,
                    permission_id=permission_id
                )
                self.db.add(role_permission)
        
        self.db.commit()
        self.db.refresh(role)
        return role
    
    def update_role(self, role_id: str, role_data: UserRoleUpdate):
        """Update a role and optionally replace its permission assignments."""
        # Avoid loading permission relationship into session before bulk replace,
        # which can trigger stale row-count errors on flush.
        role = self.get_role(role_id, with_permissions=False)
        update_data = role_data.model_dump(exclude_unset=True)
        permission_ids = update_data.pop("permissions", None)

        for key, value in update_data.items():
            setattr(role, key, value)

        if permission_ids is not None:
            existing_role_permissions = (
                self.db.query(UserRolePermission)
                .filter(UserRolePermission.role_id == role_id)
                .all()
            )
            for role_permission in existing_role_permissions:
                self.db.delete(role_permission)
            self.db.flush()
            for perm_id in permission_ids:
                self.db.add(UserRolePermission(role_id=role_id, permission_id=perm_id))

        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, role_id: str):
        """Delete a role when it is allowed by business rules."""
        # Do not eager-load permissions here; it can leave stale child rows in session
        # when deleting and trigger SQLAlchemy rowcount mismatch errors.
        role = self.get_role(role_id, with_permissions=False)

        if bool(getattr(role, "is_default", False)):
            raise handle_conflict("Default role cannot be deleted. Set another role as default first.")

        assigned_users = (
            self.db.query(UserRoleAssignment)
            .filter(UserRoleAssignment.role_id == role_id)
            .count()
        )
        if assigned_users > 0:
            raise handle_conflict(
                f"Cannot delete role: {assigned_users} user(s) are still assigned to this role."
            )

        self.db.delete(role)
        self.db.commit()
        return {"message": "Role deleted successfully", "deleted": True, "deleted_count": 1}
    
    def set_default_role(self, role_id: str):
        """Set a role as the default role."""
        role = self.get_role(role_id)
        
        # Reset all roles to is_default = False
        self.db.query(UserRole).filter(UserRole.is_default == True).update({"is_default": False})
        
        # Set the specified role to is_default = True
        setattr(role, "is_default", True)
        self.db.commit()
        self.db.refresh(role)
        return {"message": "Role successfully set as the default"}


class UserPermissionService:
    """Service for user permission operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_all_permissions(self, query: Optional[str] = None):
        """Get all permissions for select dropdowns (no pagination)."""
        q = self.db.query(UserPermission)
        if query:
            q = q.filter(
                (UserPermission.name.ilike(f"%{query}%")) |
                (UserPermission.slug.ilike(f"%{query}%"))
            )
        return q.order_by(UserPermission.name).all()

    def list_permissions(self, page: int = 1, limit: int = 50):
        """List user permissions."""
        q = self.db.query(UserPermission)
        
        total = q.count()
        offset = (page - 1) * limit
        permissions = q.offset(offset).limit(limit).all()
        
        return {
            "data": permissions,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_permission(self, permission_id: str):
        """Get a permission by ID."""
        permission = self.db.query(UserPermission).filter(UserPermission.id == permission_id).first()
        if not permission:
            raise handle_not_found("User Permission", permission_id)
        return permission
    
    def create_permission(self, permission_data: UserPermissionCreate, created_by: str):
        """Create a new permission."""
        existing = self.db.query(UserPermission).filter(
            UserPermission.slug == permission_data.slug
        ).first()
        if existing:
            raise handle_conflict("Permission slug already exists.")
        
        permission_dict = permission_data.model_dump()
        permission_dict["created_by_user_id"] = created_by
        permission = UserPermission(**permission_dict)
        self.db.add(permission)
        self.db.commit()
        self.db.refresh(permission)
        return permission
    
    def update_permission(self, permission_id: str, permission_data: UserPermissionUpdate):
        """Update a permission."""
        permission = self.get_permission(permission_id)
        
        update_data = permission_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(permission, key, value)
        
        self.db.commit()
        self.db.refresh(permission)
        return permission
    
    def bulk_delete_permissions(self, permission_ids: list[str]):
        """Bulk delete permissions."""
        # Delete linked role permissions first
        self.db.query(UserRolePermission).filter(
            UserRolePermission.permission_id.in_(permission_ids)
        ).delete(synchronize_session=False)
        
        # Delete the permissions
        deleted_count = self.db.query(UserPermission).filter(
            UserPermission.id.in_(permission_ids)
        ).delete(synchronize_session=False)
        
        self.db.commit()
        return {"message": f"Successfully deleted {deleted_count} permission(s)"}

    # --- RBAC: effective permission resolution (multi-role + legacy role_id) ---
    SUPERADMIN_ROLE_SLUG = "superadmin"

    def get_user_role_ids(self, user_id: str) -> list[str]:
        """Return all role IDs for a user (from user_role_assignments)."""
        assignments = (
            self.db.query(UserRoleAssignment.role_id)
            .filter(UserRoleAssignment.user_id == user_id)
            .all()
        )
        return [r.role_id for r in assignments]

    def get_user_role_slugs(self, user_id: str) -> set[str]:
        """Return all role slugs for a user (for superadmin bypass)."""
        role_ids = self.get_user_role_ids(user_id)
        if not role_ids:
            return set()
        roles = self.db.query(UserRole.slug).filter(UserRole.id.in_(role_ids)).all()
        return {r.slug for r in roles}

    def get_user_permission_slugs(self, user_id: str) -> set[str]:
        """Return effective permission slugs for a user (union of all assigned roles).
        Users with role slug 'superadmin' or 'admin' receive all known permissions (for frontend menu/actions)."""
        role_slugs = self.get_user_role_slugs(user_id)
        if role_slugs & {self.SUPERADMIN_ROLE_SLUG, "admin"}:
            rows = self.db.query(UserPermission.slug).all()
            return {r.slug for r in rows}
        role_ids = self.get_user_role_ids(user_id)
        if not role_ids:
            return set()
        rows = (
            self.db.query(UserPermission.slug)
            .join(UserRolePermission, UserRolePermission.permission_id == UserPermission.id)
            .filter(UserRolePermission.role_id.in_(role_ids))
            .distinct()
            .all()
        )
        return {r.slug for r in rows}

    def check_user_has_permission(self, user_id: str, permission_slug: str) -> bool:
        """True if user has the permission or is superadmin."""
        if self.get_user_role_slugs(user_id) & {self.SUPERADMIN_ROLE_SLUG, "admin"}:
            return True
        return permission_slug in self.get_user_permission_slugs(user_id)

    def check_user_has_any_permission(self, user_id: str, permission_slugs: list[str]) -> bool:
        """True if user has at least one of the permissions or is superadmin."""
        if self.get_user_role_slugs(user_id) & {self.SUPERADMIN_ROLE_SLUG, "admin"}:
            return True
        user_slugs = self.get_user_permission_slugs(user_id)
        return any(s in user_slugs for s in permission_slugs)


class AccessAgentService:
    """Service for access agent operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_agents(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List access agents."""
        q = self.db.query(AccessAgent)
        
        if query:
            q = q.filter(
                or_(
                    AccessAgent.code.ilike(f"%{query}%"),
                    AccessAgent.name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        agents = q.offset(offset).limit(limit).all()
        
        data = []
        for agent in agents:
            data.append({
                "id": str(agent.id),
                "code": agent.code,
                "name": agent.name,
                "description": agent.description,
                "is_active": agent.is_active,
                "assign_to_new_internal_contacts": agent.assign_to_new_internal_contacts,
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
                "synced_to_excel": agent.synced_to_excel,
                "last_synced_to_excel": agent.last_synced_to_excel,
            })
        
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_agent(self, agent_id: str):
        """Get an access agent by ID."""
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)

        return {
            "id": str(agent.id),
            "code": agent.code,
            "name": agent.name,
            "description": agent.description,
            "is_active": agent.is_active,
            "assign_to_new_internal_contacts": agent.assign_to_new_internal_contacts,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
            "synced_to_excel": agent.synced_to_excel,
            "last_synced_to_excel": agent.last_synced_to_excel,
        }
    
    def create_agent(self, agent_data: AccessAgentCreate):
        """Create a new access agent."""
        existing = self.db.query(AccessAgent).filter(AccessAgent.code == agent_data.code).first()
        if existing:
            raise handle_conflict("Access agent code already exists.")
        
        agent = AccessAgent(**agent_data.model_dump())
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent
    
    def update_agent(self, agent_id: str, agent_data: AccessAgentUpdate):
        """Update an access agent."""
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)
        
        update_data = agent_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)
        
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def delete_agent(self, agent_id: str) -> None:
        """Delete an access agent. Related rows cascade (contact access, agent_teams, cursors, user_agent_access)."""
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)
        self.db.delete(agent)
        self.db.commit()

    def list_agents_assign_to_new_internal_contacts(self):
        """Return access agents that should be assigned to newly created internal contacts (from sync)."""
        return (
            self.db.query(AccessAgent)
            .filter(
                AccessAgent.is_active == True,
                AccessAgent.assign_to_new_internal_contacts == True,
            )
            .all()
        )

    def list_contact_accesses(self, agent_id: str):
        """List contact access entries for an agent."""
        return self.db.query(ContactAgentAccess).filter(
            ContactAgentAccess.agent_id == agent_id
        ).order_by(ContactAgentAccess.created_at.desc()).all()
    
    def list_all_contact_accesses(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        agent_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        respond_contact_id: Optional[str] = None,  # New parameter for filtering by respond_contact_id
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List all contact access entries with filtering."""
        from app.schemas.common import ListResponse, PaginationResponse
        from app.schemas.user import ContactAgentAccessResponse
        
        q = self.db.query(ContactAgentAccess).join(AccessAgent)
        
        # Filter by respond_contact_id if provided
        if respond_contact_id:
            q = q.filter(ContactAgentAccess.respond_contact_id == respond_contact_id)
        
        if agent_id and agent_id != "all":
            q = q.filter(ContactAgentAccess.agent_id == agent_id)
        
        if contact_id:
            q = q.filter(ContactAgentAccess.respond_contact_phone.ilike(f"%{contact_id}%"))
        
        if query:
            q = q.join(AccessAgent).filter(
                or_(
                    ContactAgentAccess.respond_contact_phone.ilike(f"%{query}%"),
                    ContactAgentAccess.respond_contact_name.ilike(f"%{query}%"),
                    AccessAgent.code.ilike(f"%{query}%"),
                    AccessAgent.name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        
        # Handle sorting - map frontend field names to model attributes
        sort_map = {
            "respond_contact_phone": ContactAgentAccess.respond_contact_phone,
            "respond_contact_name": ContactAgentAccess.respond_contact_name,
            "agent_code": AccessAgent.code,
            "agent_name": AccessAgent.name,
            "created_at": ContactAgentAccess.created_at,
            "updated_at": ContactAgentAccess.updated_at,
        }
        sort_attr = sort_map.get(sort_field, ContactAgentAccess.created_at)
        if sort_dir == "desc":
            sort_attr = sort_attr.desc()
        else:
            sort_attr = sort_attr.asc()
        
        accesses = q.order_by(sort_attr).offset((page - 1) * limit).limit(limit).all()
        
        # Build response with agent details
        result_data = []
        for access in accesses:
            access_dict = {
                'id': str(access.id),
                'respond_contact_id': (
                    str(access.respond_contact_id)
                    if access.respond_contact_id is not None
                    else None
                ),
                'respond_contact_phone': access.respond_contact_phone,
                'respond_contact_name': access.respond_contact_name,
                'agent_id': str(access.agent_id),
                'is_allowed': access.is_allowed,
                'valid_from': access.valid_from,
                'valid_to': access.valid_to,
                'created_at': access.created_at,
                'created_by': access.created_by,
                'synced_to_excel': access.synced_to_excel,
                'last_synced_to_excel': access.last_synced_to_excel,
                'updated_at': access.updated_at,
                'agent_code': access.agent.code if access.agent else None,
                'agent_name': access.agent.name if access.agent else None,
            }
            result_data.append(ContactAgentAccessResponse.model_validate(access_dict))
        
        return ListResponse(
            data=result_data,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
        )

    def create_contact_access(self, agent_id: str, contact_data: ContactAgentAccessCreate):
        """Create a contact access entry for an agent."""
        from app.services.contact_service import ContactService
        from app.models.access import RespondContact
        from sqlalchemy.exc import IntegrityError
        
        # Get agent model object directly (not the dict response)
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)
        
        # Get or create the contact
        contact_service = ContactService(self.db)
        contact = contact_service.get_or_create_contact(
            phone_number=contact_data.respond_contact_phone,
            name=contact_data.respond_contact_name
        )
        
        # Check if access entry already exists for this contact and agent
        existing_access = self.db.query(ContactAgentAccess).filter(
            ContactAgentAccess.respond_contact_id == contact.id,
            ContactAgentAccess.agent_id == agent.id
        ).first()
        
        if existing_access:
            raise handle_conflict("An access agent entry already exists for this contact and agent combination.")
        
        # Create access entry with contact_id
        access_dict = contact_data.model_dump()
        access_dict['agent_id'] = agent.id
        access_dict['respond_contact_id'] = contact.id
        access = ContactAgentAccess(**access_dict)
        
        try:
            self.db.add(access)
            self.db.commit()
            self.db.refresh(access)
            return access
        except IntegrityError as e:
            self.db.rollback()
            # Check if it's a unique constraint violation
            error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'unique' in error_str.lower() or 'duplicate' in error_str.lower() or 'uq_contact_agent_access_respond_contact_id_agent_id' in error_str:
                raise handle_conflict("An access agent entry already exists for this contact and agent combination.")
            raise

    def update_contact_access(self, contact_id: str, contact_data: ContactAgentAccessUpdate):
        """Update a contact access entry."""
        access = self.db.query(ContactAgentAccess).filter(ContactAgentAccess.id == contact_id).first()
        if not access:
            raise handle_not_found("Contact Agent Access", contact_id)

        update_data = contact_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(access, key, value)

        self.db.commit()
        self.db.refresh(access)
        return access

    def delete_contact_access(self, contact_id: str):
        """Delete a contact access entry."""
        access = self.db.query(ContactAgentAccess).filter(ContactAgentAccess.id == contact_id).first()
        if not access:
            raise handle_not_found("Contact Agent Access", contact_id)
        self.db.delete(access)
        self.db.commit()

    def lookup_respond_contact_name(self, identifier: str) -> Optional[str]:
        """Lookup contact name from Respond.io by identifier."""
        client = RespondClient()
        payload = client.get_contact_by_identifier(identifier)
        return (
            payload.get("name")
            or payload.get("data", {}).get("name")
            or payload.get("contact", {}).get("name")
        )

    def sync_contact_name(self, contact_id: str) -> ContactAgentAccess:
        """Sync contact name from Respond.io and update record."""
        access = self.db.query(ContactAgentAccess).filter(ContactAgentAccess.id == contact_id).first()
        if not access:
            raise handle_not_found("Contact Agent Access", contact_id)
        # Using respond_contact_phone for lookup
        name = self.lookup_respond_contact_name(str(getattr(access, "respond_contact_phone")))
        # Update respond_contact_name field
        setattr(access, "respond_contact_name", name)
        self.db.commit()
        self.db.refresh(access)
        return access
    
    def get_next_assignee(self, agent_id: str, team_id: str) -> Optional[dict]:
        """
        Return the next assignee for (agent_id, team_id) using round-robin.
        Uses SELECT ... FOR UPDATE on the cursor for concurrency safety.
        Returns dict with id, email, name or None if no eligible members.
        """
        from sqlalchemy import and_
        # Check agent is linked to this team
        link = (
            self.db.query(AgentTeam)
            .filter(
                and_(
                    AgentTeam.agent_id == agent_id,
                    AgentTeam.team_id == team_id,
                )
            )
            .first()
        )
        if not link:
            return None
        # Get team members (user_ids) in order
        members = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
            .all()
        )
        if not members:
            return None
        user_ids = [_rr_user_id_key(m.user_id) for m in members]
        # Get or create cursor and lock it
        cursor = (
            self.db.query(AgentTeamRoundRobinCursor)
            .filter(
                and_(
                    AgentTeamRoundRobinCursor.agent_id == agent_id,
                    AgentTeamRoundRobinCursor.team_id == team_id,
                )
            )
            .with_for_update()
            .first()
        )
        if not cursor:
            cursor = AgentTeamRoundRobinCursor(
                agent_id=agent_id,
                team_id=team_id,
                last_assigned_user_id=None,
            )
            self.db.add(cursor)
            self.db.flush()
        # Find next index: after last_assigned_user_id, wrap around
        last_assigned_user_id = getattr(cursor, "last_assigned_user_id", None)
        last_key = _rr_user_id_key(last_assigned_user_id) if last_assigned_user_id is not None else ""
        try:
            idx = user_ids.index(last_key) if last_key else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(user_ids)
        next_user_id = user_ids[next_idx]
        setattr(cursor, "last_assigned_user_id", next_user_id)
        self.db.commit()
        # Load user for response
        user = self.db.query(User).filter(User.id == next_user_id).first()
        if not user:
            return {"id": next_user_id, "email": None, "name": None}
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name or user.email,
            "respond_user_id": user.respond_user_id,
        }

    def get_next_assignee_after(
        self, agent_id: str, team_id: str, current_respond_user_id: str
    ) -> Optional[dict]:
        """
        Return the next assignee after the given current assignee (by respond_user_id) in
        round-robin order. Updates the cursor to that next user so "next in line" stays consistent.
        Returns None if the agent/team link or team members are missing, or if
        current_respond_user_id is not in the team.
        """
        from sqlalchemy import and_

        link = (
            self.db.query(AgentTeam)
            .filter(
                and_(
                    AgentTeam.agent_id == agent_id,
                    AgentTeam.team_id == team_id,
                )
            )
            .first()
        )
        if not link:
            return None
        members = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
            .all()
        )
        if not members:
            return None
        user_ids = [_rr_user_id_key(m.user_id) for m in members]
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        user_by_id = {str(u.id): u for u in users}
        # Preserve member order and get respond_user_id
        ordered_respond_ids = []
        for uid in user_ids:
            u = user_by_id.get(uid)
            ordered_respond_ids.append(_normalize_respond_user_id(getattr(u, "respond_user_id", None)) if u else None)
        current_norm = _normalize_respond_user_id(str(current_respond_user_id))
        try:
            idx = ordered_respond_ids.index(current_norm)
        except ValueError:
            return None
        next_idx = (idx + 1) % len(user_ids)
        next_user_id = user_ids[next_idx]
        # Update cursor so "next in line" stays consistent
        cursor = (
            self.db.query(AgentTeamRoundRobinCursor)
            .filter(
                and_(
                    AgentTeamRoundRobinCursor.agent_id == agent_id,
                    AgentTeamRoundRobinCursor.team_id == team_id,
                )
            )
            .with_for_update()
            .first()
        )
        if not cursor:
            cursor = AgentTeamRoundRobinCursor(
                agent_id=agent_id,
                team_id=team_id,
                last_assigned_user_id=next_user_id,
            )
            self.db.add(cursor)
        else:
            setattr(cursor, "last_assigned_user_id", next_user_id)
        self.db.commit()
        user = user_by_id.get(str(next_user_id))
        if not user:
            return {"id": next_user_id, "email": None, "name": None, "respond_user_id": None}
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name or user.email,
            "respond_user_id": user.respond_user_id,
        }

    def list_agent_teams(self, agent_id: str) -> list[dict]:
        """Return list of {code, team_id, tier} assignments for this agent."""
        rows = (
            self.db.query(AgentTeam.code, AgentTeam.team_id, AgentTeam.tier)
            .filter(AgentTeam.agent_id == agent_id)
            .all()
        )
        return [{"code": r[0], "team_id": str(r[1]), "tier": r[2]} for r in rows]

    def _user_info(self, user: Optional[User]) -> Optional[dict]:
        """Return {id, name, email, respond_user_id, respond_synced} for display; None if user is None."""
        if not user:
            return None
        rid = getattr(user, "respond_user_id", None)
        rid_s = (str(rid).strip() if rid is not None else "") or None
        sync = (getattr(user, "respond_synced", None) or "pending").strip() or "pending"
        return {
            "id": user.id,
            "name": user.name or user.email or user.id,
            "email": user.email,
            "respond_user_id": rid_s,
            "respond_synced": sync,
        }

    def _peek_next_assignee(self, agent_id: str, team_id: str) -> tuple[Optional[str], Optional[str]]:
        """Return (last_assigned_user_id, next_user_id) without updating the cursor."""
        members = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
            .all()
        )
        if not members:
            return None, None
        user_ids = [_rr_user_id_key(m.user_id) for m in members]
        cursor = (
            self.db.query(AgentTeamRoundRobinCursor)
            .filter(
                AgentTeamRoundRobinCursor.agent_id == agent_id,
                AgentTeamRoundRobinCursor.team_id == team_id,
            )
            .first()
        )
        last_id = str(getattr(cursor, "last_assigned_user_id")) if cursor and getattr(cursor, "last_assigned_user_id", None) is not None else None
        last_key = _rr_user_id_key(last_id) if last_id is not None else ""
        try:
            idx = user_ids.index(last_key) if last_key else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(user_ids)
        return last_id, user_ids[next_idx]

    def list_agent_teams_with_round_robin_state(self, agent_id: str) -> list[dict]:
        """Return assignments with team name, tier, members (ordered), last_assigned, next_in_line (read-only peek)."""
        rows = (
            self.db.query(AgentTeam.code, AgentTeam.team_id, AgentTeam.tier)
            .filter(AgentTeam.agent_id == agent_id)
            .all()
        )
        result = []
        for code, team_id, tier in rows:
            team_id_str = str(team_id)
            team = self.db.query(Team).filter(Team.id == team_id).first()
            team_name = team.name if team else team_id_str
            members = (
                self.db.query(TeamMember)
                .filter(TeamMember.team_id == team_id)
                .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
                .all()
            )
            member_infos = []
            for m in members:
                u = self.db.query(User).filter(User.id == m.user_id).first()
                member_infos.append(
                    self._user_info(u)
                    or {
                        "id": m.user_id,
                        "name": m.user_id,
                        "email": None,
                        "respond_user_id": None,
                        "respond_synced": None,
                    }
                )
            last_id, next_id = self._peek_next_assignee(agent_id, team_id_str)
            last_user = self.db.query(User).filter(User.id == last_id).first() if last_id else None
            next_user = self.db.query(User).filter(User.id == next_id).first() if next_id else None
            result.append({
                "code": code,
                "team_id": team_id_str,
                "tier": tier,
                "team_name": team_name,
                "members": member_infos,
                "last_assigned": self._user_info(last_user) if last_id else None,
                "next_in_line": self._user_info(next_user) if next_id else None,
            })
        return result

    def set_agent_teams(self, agent_id: str, assignments: list[dict]) -> None:
        """Replace agent's team links with the given assignments [{code, team_id, tier?}...]."""
        seen_keys: set[tuple[str, str | int]] = set()
        for a in assignments or []:
            raw_code = a.get("code")
            code = str(raw_code).strip() if raw_code is not None else ""
            team_id = a.get("team_id")
            tier = a.get("tier")
            if tier is not None and (tier < 1 or tier > 3):
                tier = None
            if not code or not team_id:
                continue
            # Matches partial unique indexes: one row per (agent, code) when tier is null;
            # one row per (agent, code, tier) when tier is set.
            key: tuple[str, str | int] = (code, tier if tier is not None else "__null_tier__")
            if key in seen_keys:
                raise handle_validation_error(
                    f"cannot have duplicate code {code} in different groups"
                )
            seen_keys.add(key)

        self.db.query(AgentTeam).filter(AgentTeam.agent_id == agent_id).delete()
        for a in assignments or []:
            raw_code = a.get("code")
            code = str(raw_code).strip() if raw_code is not None else ""
            team_id = a.get("team_id")
            tier = a.get("tier")
            if tier is not None and (tier < 1 or tier > 3):
                tier = None
            if code and team_id:
                self.db.add(AgentTeam(agent_id=agent_id, code=code, team_id=team_id, tier=tier))
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise handle_validation_error(
                "cannot have duplicate code in different groups"
            ) from None

    def get_team_id_by_code(self, agent_id: str, code: str) -> str | None:
        """Resolve team_id for agent+code. If several tiers share this code, returns one row (undefined which). Prefer get_team_id_by_tier + list_team_ids_for_agent_code for round-robin."""
        row = (
            self.db.query(AgentTeam.team_id)
            .filter(AgentTeam.agent_id == agent_id, AgentTeam.code == code)
            .first()
        )
        return str(row[0]) if row else None

    def list_team_ids_for_agent_code(self, agent_id: str, code: str) -> list[str]:
        """All team_ids for this agent with the given assignment code (e.g. one per SLA tier)."""
        from sqlalchemy import and_

        c = str(code).strip() if code is not None else ""
        if not c:
            return []
        rows = (
            self.db.query(AgentTeam.team_id)
            .filter(and_(AgentTeam.agent_id == agent_id, AgentTeam.code == c))
            .all()
        )
        return [str(r[0]) for r in rows]

    def get_team_id_by_tier(
        self, agent_id: str, tier: int, team_set_code: Optional[str] = None
    ) -> str | None:
        """Resolve team_id for agent+tier, optionally constrained to one team set code."""
        if tier is None or tier < 1 or tier > 3:
            return None

        query = self.db.query(AgentTeam.team_id).filter(
            AgentTeam.agent_id == agent_id,
            AgentTeam.tier == tier,
        )
        if team_set_code:
            query = query.filter(AgentTeam.code == team_set_code)

        rows = query.all()
        if not rows:
            return None
        if len(rows) > 1 and not team_set_code:
            raise handle_conflict(
                f"Multiple team sets found for tier {tier}. Provide team_set_code to resolve escalation target."
            )
        return str(rows[0][0])

    def get_agent_id_by_code(self, code: str) -> str | None:
        """Resolve agent_id from access agent code. Returns None if not found."""
        agent = self.db.query(AccessAgent.id).filter(AccessAgent.code == code).first()
        return str(agent[0]) if agent else None


class TeamService:
    """Service for team and team member operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_teams(self):
        """List all teams."""
        return self.db.query(Team).order_by(Team.name.asc()).all()

    def get_team(self, team_id: str) -> Team:
        """Get team by ID."""
        t = self.db.query(Team).filter(Team.id == team_id).first()
        if not t:
            raise handle_not_found("Team", team_id)
        return t

    def create_team(self, data: TeamCreate) -> Team:
        """Create a team."""
        t = Team(**data.model_dump())
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        return t

    def update_team(self, team_id: str, data: TeamUpdate) -> Team:
        """Update a team."""
        t = self.get_team(team_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(t, k, v)
        self.db.commit()
        self.db.refresh(t)
        return t

    def delete_team(self, team_id: str) -> None:
        """Delete a team (cascades to members and agent_teams)."""
        t = self.get_team(team_id)
        self.db.delete(t)
        self.db.commit()

    def list_team_members(self, team_id: str):
        """List members of a team ordered by sort_order, user_id."""
        self.get_team(team_id)
        return (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
            .all()
        )

    def add_team_member(self, team_id: str, user_id: str, sort_order: Optional[int] = None) -> TeamMember:
        """Add a user to a team."""
        self.get_team(team_id)
        existing = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if existing:
            raise handle_conflict("User is already a member of this team.")
        m = TeamMember(team_id=team_id, user_id=user_id, sort_order=sort_order)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def remove_team_member(self, team_id: str, user_id: str) -> None:
        """Remove a user from a team."""
        m = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if not m:
            raise handle_not_found("Team member", f"{team_id}/{user_id}")
        self.db.delete(m)
        self.db.commit()
