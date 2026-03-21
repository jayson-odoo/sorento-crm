"""User management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime


# Respond Contact Schemas
class RespondContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    user_type: Optional[str] = None
    respond_io_id: Optional[str] = None  # Respond.io contact id for inbox URL


class RespondContactCreate(RespondContactBase):
    pass


class RespondContactUpdate(BaseModel):
    phone_number: Optional[str] = None
    name: Optional[str] = None
    user_type: Optional[str] = None
    respond_io_id: Optional[str] = None


class RespondContactResponse(RespondContactBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    respond_io_id: Optional[str] = None
    access_type_code: Optional[str] = None  # Resolved from user_type via catalog/mappings

    class Config:
        from_attributes = True


class UserRoleBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    is_protected: bool = False
    is_default: bool = False


class UserRoleCreate(UserRoleBase):
    permissions: Optional[list[str]] = None  # Permission IDs


class UserRoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_protected: Optional[bool] = None
    is_default: Optional[bool] = None
    permissions: Optional[list[str]] = None  # Permission IDs; when set, replaces role's permissions


class UserRoleSimple(BaseModel):
    id: str
    name: str
    
    class Config:
        from_attributes = True


class UserSelectResponse(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    respond_user_id: Optional[str] = None
    respond_synced: Optional[str] = None

    class Config:
        from_attributes = True


class UserRolePermissionRef(BaseModel):
    """Minimal permission ref for role response."""
    id: str
    slug: str

    class Config:
        from_attributes = True


class UserRoleResponse(UserRoleBase):
    id: str
    created_at: datetime
    permissions: Optional[List[UserRolePermissionRef]] = None

    class Config:
        from_attributes = True

    @field_validator("permissions", mode="before")
    @classmethod
    def permissions_from_orm(cls, v: Any) -> Optional[List[dict]]:
        if v is None:
            return None
        if isinstance(v, list):
            out = []
            for p in v:
                if hasattr(p, "permission") and p.permission:
                    out.append({"id": p.permission.id, "slug": p.permission.slug})
                elif isinstance(p, dict) and "id" in p and "slug" in p:
                    out.append(p)
            return out if out else None
        return None


class UserPermissionBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None


class UserPermissionCreate(UserPermissionBase):
    pass


class UserPermissionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserPermissionResponse(UserPermissionBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: str
    name: Optional[str] = None
    status: str = "INACTIVE"
    country: Optional[str] = None
    timezone: Optional[str] = None
    respond_user_id: Optional[str] = None
    respond_synced: Optional[str] = "pending"
    superior_id: Optional[str] = None
    tier: Optional[int] = None  # Conversation SLA policy tier (1, 2, ...)


class UserCreate(UserBase):
    role_ids: Optional[list[str]] = None  # If omitted, default role is assigned


class UserUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    avatar: Optional[str] = None
    respond_user_id: Optional[str] = None
    respond_synced: Optional[str] = None
    superior_id: Optional[str] = None
    tier: Optional[int] = None


class UserResponse(UserBase):
    id: str
    avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_sign_in_at: Optional[datetime] = None
    email_verified_at: Optional[datetime] = None
    is_trashed: Optional[bool] = False
    is_protected: Optional[bool] = False
    roles: Optional[List[UserRoleSimple]] = None  # Assigned roles from user_role_assignments
    superior_name: Optional[str] = None  # Superior's name for display

    class Config:
        from_attributes = True


class AccessAgentBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    assign_to_new_internal_contacts: bool = False
    pic_respond_user_id: Optional[str] = None


class AccessAgentCreate(AccessAgentBase):
    pass


class AccessAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    assign_to_new_internal_contacts: Optional[bool] = None
    pic_respond_user_id: Optional[str] = None


class AccessAgentResponse(AccessAgentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    pic_respond_user_name: Optional[str] = None  # User name from users table
    
    class Config:
        from_attributes = True


class ContactAgentAccessBase(BaseModel):
    respond_contact_id: Optional[str] = None  # FK to respond_contacts
    respond_contact_phone: str  # Keep for backward compatibility
    respond_contact_name: Optional[str] = None  # Keep for backward compatibility
    agent_id: str
    is_allowed: bool = True
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class ContactAgentAccessCreate(ContactAgentAccessBase):
    pass


class ContactAgentAccessUpdate(BaseModel):
    respond_contact_id: Optional[str] = None
    respond_contact_phone: Optional[str] = None
    respond_contact_name: Optional[str] = None
    is_allowed: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class ContactAgentAccessResponse(ContactAgentAccessBase):
    id: str
    created_at: datetime
    created_by: Optional[str] = None
    synced_to_excel: bool
    last_synced_to_excel: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    agent_code: Optional[str] = None  # Added for frontend display
    agent_name: Optional[str] = None  # Added for frontend display

    class Config:
        from_attributes = True


class RespondContactLookupRequest(BaseModel):
    identifier: str


class RespondContactLookupResponse(BaseModel):
    contact_name: Optional[str] = None


# Team schemas (for round-robin assignee)
class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TeamResponse(TeamBase):
    id: str
    created_at: datetime
    class Config:
        from_attributes = True


class TeamMemberResponse(BaseModel):
    id: str
    team_id: str
    user_id: str
    sort_order: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True


class AgentTeamAssignment(BaseModel):
    code: str
    team_id: str
    tier: Optional[int] = None  # 1=initial, 2/3=escalation; one team per tier per agent


class AgentTeamsUpdate(BaseModel):
    """Legacy: team_ids for backwards compat. Use assignments instead."""
    team_ids: list[str] | None = None
    assignments: list[AgentTeamAssignment] | None = None


# Contact access type catalog (admin CRUD)
class ContactAccessTypeBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: Optional[int] = None


class ContactAccessTypeCreate(ContactAccessTypeBase):
    pass


class ContactAccessTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ContactAccessTypeResponse(ContactAccessTypeBase):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Respond access type mapping (admin CRUD)
class RespondAccessTypeMappingBase(BaseModel):
    source_key: str
    access_type_code: str
    is_active: bool = True


class RespondAccessTypeMappingCreate(RespondAccessTypeMappingBase):
    pass


class RespondAccessTypeMappingUpdate(BaseModel):
    source_key: Optional[str] = None
    access_type_code: Optional[str] = None
    is_active: Optional[bool] = None


class RespondAccessTypeMappingResponse(RespondAccessTypeMappingBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
