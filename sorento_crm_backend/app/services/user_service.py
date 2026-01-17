"""User management service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.models.user import User, UserRole, UserPermission, UserRolePermission
from app.models.access import AccessAgent
from app.schemas.user import (
    UserCreate, UserUpdate, UserRoleCreate, UserRoleUpdate,
    UserPermissionCreate, UserPermissionUpdate, AccessAgentCreate, AccessAgentUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


class UserService:
    """Service for user operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_users(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        status: Optional[str] = None,
        role_id: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List users."""
        q = self.db.query(User)
        
        filters = []
        
        if status and status != "all":
            filters.append(User.status == status)
        
        if role_id and role_id != "all":
            filters.append(User.role_id == role_id)
        
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
            "last_sign_in_at": User.last_sign_in_at,
        }
        sort_column = sort_map.get(sort_field, User.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        users = q.offset(offset).limit(limit).all()
        
        return {
            "data": users,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_user(self, user_id: str):
        """Get a user by ID."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise handle_not_found("User", user_id)
        return user
    
    def create_user(self, user_data: UserCreate):
        """Create a new user."""
        existing = self.db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise handle_conflict("Email is already registered.")
        
        user = User(**user_data.model_dump())
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def update_user(self, user_id: str, user_data: UserUpdate):
        """Update a user."""
        user = self.get_user(user_id)
        
        update_data = user_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(user, key, value)
        
        self.db.commit()
        self.db.refresh(user)
        return user


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
        """List user roles."""
        q = self.db.query(UserRole)
        
        total = q.count()
        offset = (page - 1) * limit
        roles = q.offset(offset).limit(limit).all()
        
        return {
            "data": roles,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_role(self, role_id: str):
        """Get a role by ID."""
        role = self.db.query(UserRole).filter(UserRole.id == role_id).first()
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
        """Update a role."""
        role = self.get_role(role_id)
        
        update_data = role_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(role, key, value)
        
        self.db.commit()
        self.db.refresh(role)
        return role


class UserPermissionService:
    """Service for user permission operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
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
        
        return {
            "data": agents,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_agent(self, agent_id: str):
        """Get an access agent by ID."""
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)
        return agent
    
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
        agent = self.get_agent(agent_id)
        
        update_data = agent_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)
        
        self.db.commit()
        self.db.refresh(agent)
        return agent
