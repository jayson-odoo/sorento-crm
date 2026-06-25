"""User management schemas."""
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Any
from datetime import datetime


# Respond Contact Schemas
class RespondContactAccessTypeRef(BaseModel):
    code: str
    name: str
    sort_order: Optional[int] = None


class RespondContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    respond_io_id: Optional[str] = None  # Respond.io contact id for inbox URL
    workspace_id: Optional[str] = None  # FK to respond_workspaces.id


class RespondContactCreate(RespondContactBase):
    access_type_codes: Optional[List[str]] = None  # Many-to-many to contact_access_types


class RespondContactUpdate(BaseModel):
    phone_number: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    respond_io_id: Optional[str] = None
    workspace_id: Optional[str] = None
    access_type_codes: Optional[List[str]] = None  # When set, replaces the contact's M2M assignment


class RespondContactResponse(RespondContactBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    respond_io_id: Optional[str] = None
    access_type_codes: List[str] = []
    access_types: List[RespondContactAccessTypeRef] = []
    workspace_name: Optional[str] = None
    workspace_space_id: Optional[str] = None

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
    contact_number: Optional[str] = None
    status: str = "INACTIVE"
    country: Optional[str] = None
    timezone: Optional[str] = None
    respond_user_id: Optional[str] = None
    respond_synced: Optional[str] = "pending"
    superior_id: Optional[str] = None
    tier: Optional[int] = None  # Conversation SLA policy tier (1, 2, ...)
    daily_sla_summary_subscribed: Optional[bool] = True  # email summary opt-in
    respond_contact_id: Optional[str] = None  # linked WhatsApp contact
    notify_whatsapp: Optional[bool] = False  # legacy; superseded by per-event toggles
    notify_whatsapp_summary: Optional[bool] = False  # daily summary template
    notify_email_on_assignment: Optional[bool] = True
    notify_email_on_escalation: Optional[bool] = True
    notify_whatsapp_on_assignment: Optional[bool] = False
    notify_whatsapp_on_escalation: Optional[bool] = False
    notify_email_on_product_discontinued: Optional[bool] = False
    notify_whatsapp_on_product_discontinued: Optional[bool] = False
    notify_email_on_deadline_extended: Optional[bool] = True
    notify_whatsapp_on_deadline_extended: Optional[bool] = False

    @field_validator("contact_number", mode="before")
    @classmethod
    def _normalize_contact_number_base(cls, v: Any) -> Optional[str]:
        from app.services.phone_utils import normalize_msisdn
        if v is None:
            return None
        return normalize_msisdn(v)


class UserCreate(UserBase):
    role_ids: Optional[list[str]] = None  # If omitted, default role is assigned


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    contact_number: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    avatar: Optional[str] = None
    respond_user_id: Optional[str] = None
    respond_synced: Optional[str] = None
    superior_id: Optional[str] = None
    tier: Optional[int] = None
    respond_contact_id: Optional[str] = None
    notify_whatsapp: Optional[bool] = None
    notify_whatsapp_summary: Optional[bool] = None
    daily_sla_summary_subscribed: Optional[bool] = None
    notify_email_on_assignment: Optional[bool] = None
    notify_email_on_escalation: Optional[bool] = None
    notify_whatsapp_on_assignment: Optional[bool] = None
    notify_whatsapp_on_escalation: Optional[bool] = None
    notify_email_on_product_discontinued: Optional[bool] = None
    notify_whatsapp_on_product_discontinued: Optional[bool] = None
    notify_email_on_deadline_extended: Optional[bool] = None
    notify_whatsapp_on_deadline_extended: Optional[bool] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s.lower() if s else None

    @field_validator("contact_number", mode="before")
    @classmethod
    def normalize_optional_contact_number(cls, v: Any) -> Optional[str]:
        from app.services.phone_utils import normalize_msisdn
        if v is None:
            return None
        return normalize_msisdn(v)


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


class AccessAgentCreate(AccessAgentBase):
    pass


class AccessAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    assign_to_new_internal_contacts: Optional[bool] = None


class AccessAgentResponse(AccessAgentBase):
    id: str
    created_at: datetime
    updated_at: datetime

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
    parent_team_id: Optional[str] = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_team_id: Optional[str] = None


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
    include_in_round_robin: bool = True
    created_at: datetime
    class Config:
        from_attributes = True


class AgentTeamAssignment(BaseModel):
    code: str
    team_id: str
    tier: Optional[int] = None  # 1=initial, 2/3=escalation; one team per tier per agent
    # Conversation SLA policy for this team set. One policy per (agent, code); the
    # service casts it onto every tier row of the set. None = unbound.
    policy_id: Optional[str] = None


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
    # Admin-curated synonyms for fuzzy resolution (e.g. ["customer","homeowner"] → end_user).
    keywords: List[str] = []


class ContactAccessTypeCreate(ContactAccessTypeBase):
    pass


class ContactAccessTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    keywords: Optional[List[str]] = None


class ContactAccessTypeResponse(ContactAccessTypeBase):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# MCP tool catalog (Phase 2 — AccessAgent ↔ Tool ownership)
# ---------------------------------------------------------------------------

class McpToolOut(BaseModel):
    """Picker row. ``current_agent_ids/names`` list every agent the tool is
    linked to (many-to-many). UI shows the list so the admin sees what other
    agents already share this tool."""
    id: str
    tool_name: str
    description: str | None = None
    module_key: str = ""
    current_agent_ids: list[str] = []
    current_agent_names: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class McpToolForAgentOut(BaseModel):
    """A row in `GET /access-agents/{id}/mcp-tools` (tools owned by THIS agent)."""
    id: str
    tool_name: str
    description: str | None = None
    module_key: str = ""

    model_config = ConfigDict(from_attributes=True)


class AccessAgentMcpToolsUpdate(BaseModel):
    """PUT /access-agents/{id}/mcp-tools body."""
    tool_ids: list[str]


class McpToolBindingIn(BaseModel):
    """One row in PUT /access-agents/{id}/mcp-tool-bindings body.

    ``team_id`` None = legacy ownership (route via AgentTeam fan-out). Set it
    to bind this tool to one specific team for routing.
    """
    tool_id: str
    team_id: str | None = None
    tier: int | None = None


class AccessAgentMcpToolBindingsUpdate(BaseModel):
    bindings: list[McpToolBindingIn]


class McpToolBindingOut(BaseModel):
    id: str
    tool_id: str
    tool_name: str
    module_key: str = ""
    description: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    tier: int | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# MCP guard (Phase 3)
# ---------------------------------------------------------------------------

class McpAccessCheckIn(BaseModel):
    tool_name: str
    contact_id: str        # respond_io_id (Respond.io external contact id)
    space_id: str          # Respond.io external workspace id (matches respond_workspaces.space_id)


class McpAccessCheckOut(BaseModel):
    allowed: bool
    decision: str          # "allow" | "deny_no_access" | "deny_tool_unlinked"
                           # | "deny_unknown_tool" | "deny_unknown_contact"
    agent_name: str | None = None


class McpAccessLogOut(BaseModel):
    id: str
    tool_name: str
    contact_external_id: str | None = None
    respond_contact_id: str | None = None
    respond_workspace_id: str | None = None
    decision: str
    matched_agent_id: str | None = None
    ts: datetime

    model_config = ConfigDict(from_attributes=True)
