"""External access-agent preflight schemas.

Wraps :func:`app.services.mcp_access_service.evaluate_agent`. n8n calls this
endpoint with (contact_id, space_id, agent) before launching the agent run; the
MCP tool surface no longer carries contact_id/space_id, so verification moves
one hop earlier.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentAccessCheckIn(BaseModel):
    contact_id: str = Field(..., description="Respond.io contact id (respond_io_id).")
    space_id: str = Field(..., description="Respond.io workspace id (matches respond_workspaces.space_id).")
    agent: str = Field(..., description="AccessAgent.code - stable, kebab/underscore string.")
    resource: str | None = Field(
        None,
        description=(
            "Namespace for `attributes`, e.g. `incoming_stock`. Required only when "
            "asking about specific fields."
        ),
    )
    attributes: list[str] | None = Field(
        None,
        description=(
            "Optional field keys to check, e.g. ['eta_delay_date', 'gatepass_date']. "
            "Holding the agent is not the same as being allowed every field it can "
            "reach, so ask here before promising the caller a value."
        ),
    )


class AttributeAccess(BaseModel):
    """Why one field is or is not available, in terms an admin can act on."""

    field: str
    agent_code: str | None = None
    #: "allowed" | "not_gated" | "agent_not_assigned" | "field_not_allowed"
    #: | "contact_not_found"
    outcome: str
    reason: str | None = None


class AgentAccessCheckOut(BaseModel):
    allowed: bool
    decision: str  # "allow" | "deny_no_access" | "deny_unknown_agent" | "deny_unknown_contact"
    agent_name: str | None = None
    #: Present only when `attributes` was asked for. `allowed` above stays the
    #: answer about the AGENT; a caller holding the agent can still be refused a
    #: field, and conflating the two loses the distinction that tells an admin
    #: whether to grant the agent or tick the field.
    attributes: list[AttributeAccess] | None = None
    all_attributes_allowed: bool | None = None
