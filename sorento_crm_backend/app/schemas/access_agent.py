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
    agent: str = Field(..., description="AccessAgent.code — stable, kebab/underscore string.")


class AgentAccessCheckOut(BaseModel):
    allowed: bool
    decision: str  # "allow" | "deny_no_access" | "deny_unknown_agent" | "deny_unknown_contact"
    agent_name: str | None = None
