"""User management service for business logic."""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional
from datetime import datetime
from app.models.user import User, UserRole, UserPermission, UserRolePermission
from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    UserAgentAccess,
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
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.integration_service import RespondClient


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
        respond_synced: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List users."""
        # Eagerly load the role relationship to avoid lazy loading issues
        q = self.db.query(User).options(joinedload(User.role))
        
        filters = []
        
        if status and status != "all":
            filters.append(User.status == status)
        
        if role_id and role_id != "all":
            filters.append(User.role_id == role_id)
        
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
        respond_synced: Optional[str] = None
    ):
        """List users for select dropdowns."""
        # No need to load role for select dropdowns, but keep query simple
        q = self.db.query(User)

        filters = []
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
        # Eagerly load the role and superior relationships
        user = self.db.query(User).options(
            joinedload(User.role),
            joinedload(User.superior)
        ).filter(User.id == user_id).first()
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
        import logging
        logger = logging.getLogger(__name__)
        
        user = self.get_user(user_id)
        
        # Get all fields that were explicitly set in the request
        update_data = user_data.model_dump(exclude_unset=True)
        logger.info(f"Updating user {user_id} with data: {update_data}")
        
        # Convert empty strings to None for optional fields to avoid foreign key violations
        optional_fields = ['superior_id', 'respond_user_id', 'country', 'timezone', 'avatar']
        
        # Log what we received
        logger.info(f"Received update_data keys: {list(update_data.keys())}")
        logger.info(f"Received update_data: {update_data}")
        
        # Process each field explicitly
        for key, value in update_data.items():
            logger.info(f"Processing field '{key}' with value: {repr(value)} (type: {type(value).__name__})")
            
            # Handle empty strings for optional fields
            if key in optional_fields and value == '':
                setattr(user, key, None)
                logger.info(f"✓ Set {key} = None (converted from empty string)")
            # Handle None values for optional fields
            elif value is None and key in optional_fields:
                setattr(user, key, None)
                logger.info(f"✓ Set {key} = None (explicit None)")
            # Handle None for non-optional fields (skip them)
            elif value is None:
                logger.warning(f"⚠ Skipping {key} (None value for non-optional field)")
            # Handle all other values (including empty strings for non-optional)
            else:
                setattr(user, key, value)
                logger.info(f"✓ Set {key} = {repr(value)}")
        
        # Log before commit
        logger.info(f"Before commit - role_id: {user.role_id}, respond_user_id: {user.respond_user_id}, superior_id: {user.superior_id}")
        
        self.db.commit()
        self.db.refresh(user)
        
        # Log after commit and refresh
        logger.info(f"After commit - role_id: {user.role_id}, respond_user_id: {user.respond_user_id}, superior_id: {user.superior_id}")
        return user

    def sync_respond_user(self, user_id: str, respond_user_id: Optional[str] = None) -> dict:
        """Sync user with Respond.io and update respond_synced status."""
        user = self.get_user(user_id)
        # Use provided respond_user_id or fall back to database value
        respond_id = respond_user_id if respond_user_id else user.respond_user_id
        # Check for None, empty string, or falsy values
        if not respond_id or (isinstance(respond_id, str) and respond_id.strip() == ''):
            raise handle_conflict("Respond user ID is required for sync.")
        
        # If respond_user_id was provided and different from database, save it first
        if respond_user_id and respond_user_id != user.respond_user_id:
            user.respond_user_id = respond_user_id
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
            user.respond_synced = "failed"
            self.db.commit()
            self.db.refresh(user)
            return {"status": "failed", "message": "Respond user email not found."}

        if email.strip().lower() == user.email.strip().lower():
            user.respond_synced = "successful"
            self.db.commit()
            self.db.refresh(user)
            return {"status": "successful", "message": "Respond user synced successfully."}

        user.respond_synced = "failed"
        self.db.commit()
        self.db.refresh(user)
        return {"status": "failed", "message": "Respond email does not match system email."}


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
    
    def set_default_role(self, role_id: str):
        """Set a role as the default role."""
        role = self.get_role(role_id)
        
        # Reset all roles to is_default = False
        self.db.query(UserRole).filter(UserRole.is_default == True).update({"is_default": False})
        
        # Set the specified role to is_default = True
        role.is_default = True
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


class AccessAgentService:
    """Service for access agent operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_agents(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List access agents with PIC user name resolved."""
        from app.models.user import User
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
        
        # Enrich each agent with pic_respond_user_name
        data = []
        for agent in agents:
            pic_respond_user_name = None
            if agent.pic_respond_user_id:
                user = self.db.query(User).filter(
                    User.respond_user_id == agent.pic_respond_user_id
                ).first()
                if user:
                    pic_respond_user_name = user.name or user.email
            data.append({
                "id": str(agent.id),
                "code": agent.code,
                "name": agent.name,
                "description": agent.description,
                "is_active": agent.is_active,
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
                "synced_to_excel": agent.synced_to_excel,
                "last_synced_to_excel": agent.last_synced_to_excel,
                "pic_respond_user_id": agent.pic_respond_user_id,
                "pic_respond_user_name": pic_respond_user_name,
            })
        
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_agent(self, agent_id: str):
        """Get an access agent by ID."""
        from app.models.user import User
        agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
        if not agent:
            raise handle_not_found("Access Agent", agent_id)
        
        # Get PIC respond user name if pic_respond_user_id exists
        pic_respond_user_name = None
        if agent.pic_respond_user_id:
            user = self.db.query(User).filter(
                User.respond_user_id == agent.pic_respond_user_id
            ).first()
            if user:
                pic_respond_user_name = user.name or user.email
        
        # Add the user name as a dynamic attribute for the response
        # We'll use model_validate with a dict to include the extra field
        agent_dict = {
            'id': str(agent.id),
            'code': agent.code,
            'name': agent.name,
            'description': agent.description,
            'is_active': agent.is_active,
            'created_at': agent.created_at,
            'updated_at': agent.updated_at,
            'synced_to_excel': agent.synced_to_excel,
            'last_synced_to_excel': agent.last_synced_to_excel,
            'pic_respond_user_id': agent.pic_respond_user_id,
            'pic_respond_user_name': pic_respond_user_name,
        }
        return agent_dict
    
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
        from app.schemas.common import ListResponse
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
                'respond_contact_id': str(access.respond_contact_id) if access.respond_contact_id else None,
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
            pagination={
                "total": total,
                "page": page,
                "limit": limit
            }
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
        name = self.lookup_respond_contact_name(access.respond_contact_phone)
        # Update respond_contact_name field
        access.respond_contact_name = name
        self.db.commit()
        self.db.refresh(access)
        return access
    
    def create_user_agent_access(
        self, 
        user_id: str, 
        agent_id: str,
        is_allowed: bool = True,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None
    ) -> UserAgentAccess:
        """Create a user agent access with allowed, valid_from, valid_to."""
        # Check if access already exists
        existing = self.db.query(UserAgentAccess).filter(
            UserAgentAccess.user_id == user_id,
            UserAgentAccess.agent_id == agent_id
        ).first()
        if existing:
            raise handle_conflict("User agent access already exists for this user and agent.")
        
        access = UserAgentAccess(
            user_id=user_id,
            agent_id=agent_id,
            is_allowed=is_allowed,
            valid_from=valid_from,
            valid_to=valid_to
        )
        self.db.add(access)
        self.db.commit()
        self.db.refresh(access)
        return access
    
    def update_user_agent_accesses(self, user_id: str, agent_ids: list[str]):
        """Update user agent accesses by deleting existing and creating new ones."""
        # Delete existing
        self.db.query(UserAgentAccess).filter(UserAgentAccess.user_id == user_id).delete()
        
        # Create new ones
        for agent_id in agent_ids:
            access = UserAgentAccess(user_id=user_id, agent_id=agent_id, is_allowed=True)
            self.db.add(access)
        
        self.db.commit()
        return {"message": "User agent accesses updated successfully"}

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
        user_ids = [m.user_id for m in members]
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
        try:
            idx = user_ids.index(cursor.last_assigned_user_id) if cursor.last_assigned_user_id else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(user_ids)
        next_user_id = user_ids[next_idx]
        cursor.last_assigned_user_id = next_user_id
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

    def list_agent_teams(self, agent_id: str) -> list[dict]:
        """Return list of {code, team_id} assignments for this agent."""
        rows = (
            self.db.query(AgentTeam.code, AgentTeam.team_id)
            .filter(AgentTeam.agent_id == agent_id)
            .all()
        )
        return [{"code": r[0], "team_id": str(r[1])} for r in rows]

    def _user_info(self, user: Optional[User]) -> Optional[dict]:
        """Return {id, name, email} for display; None if user is None."""
        if not user:
            return None
        return {
            "id": user.id,
            "name": user.name or user.email or user.id,
            "email": user.email,
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
        user_ids = [m.user_id for m in members]
        cursor = (
            self.db.query(AgentTeamRoundRobinCursor)
            .filter(
                AgentTeamRoundRobinCursor.agent_id == agent_id,
                AgentTeamRoundRobinCursor.team_id == team_id,
            )
            .first()
        )
        last_id = cursor.last_assigned_user_id if cursor else None
        try:
            idx = user_ids.index(last_id) if last_id else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(user_ids)
        return last_id, user_ids[next_idx]

    def list_agent_teams_with_round_robin_state(self, agent_id: str) -> list[dict]:
        """Return assignments with team name, members (ordered), last_assigned, next_in_line (read-only peek)."""
        rows = (
            self.db.query(AgentTeam.code, AgentTeam.team_id)
            .filter(AgentTeam.agent_id == agent_id)
            .all()
        )
        result = []
        for code, team_id in rows:
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
                member_infos.append(self._user_info(u) or {"id": m.user_id, "name": m.user_id, "email": None})
            last_id, next_id = self._peek_next_assignee(agent_id, team_id_str)
            last_user = self.db.query(User).filter(User.id == last_id).first() if last_id else None
            next_user = self.db.query(User).filter(User.id == next_id).first() if next_id else None
            result.append({
                "code": code,
                "team_id": team_id_str,
                "team_name": team_name,
                "members": member_infos,
                "last_assigned": self._user_info(last_user) if last_id else None,
                "next_in_line": self._user_info(next_user) if next_id else None,
            })
        return result

    def set_agent_teams(self, agent_id: str, assignments: list[dict]) -> None:
        """Replace agent's team links with the given assignments [{code, team_id}...]."""
        self.db.query(AgentTeam).filter(AgentTeam.agent_id == agent_id).delete()
        for a in assignments or []:
            code = a.get("code")
            team_id = a.get("team_id")
            if code and team_id:
                self.db.add(AgentTeam(agent_id=agent_id, code=code, team_id=team_id))
        self.db.commit()

    def get_team_id_by_code(self, agent_id: str, code: str) -> str | None:
        """Resolve team_id for agent+code. Returns None if not found."""
        row = (
            self.db.query(AgentTeam.team_id)
            .filter(AgentTeam.agent_id == agent_id, AgentTeam.code == code)
            .first()
        )
        return str(row[0]) if row else None

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
