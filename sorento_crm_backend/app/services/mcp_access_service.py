"""MCP guard decision service (Phase 3).

Single entry point: ``evaluate(db, tool_name, contact_id, space_id)``.
Writes one ``mcp_access_log`` row per call (every branch).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
    agent_mcp_tools,
)
from app.models.respond_workspace import RespondWorkspace

logger = logging.getLogger(__name__)

Decision = Literal[
    "allow",
    "deny_no_access",
    "deny_tool_unlinked",
    "deny_unknown_tool",
    "deny_unknown_contact",
]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    decision: Decision
    agent_name: str | None


def _record_log(
    db: Session,
    *,
    tool_name: str,
    contact_external_id: str | None,
    respond_contact_id: str | None,
    respond_workspace_id: str | None,
    decision: Decision,
    matched_agent_id: str | None,
) -> None:
    db.add(
        McpAccessLog(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            contact_external_id=contact_external_id,
            respond_contact_id=respond_contact_id,
            respond_workspace_id=respond_workspace_id,
            decision=decision,
            matched_agent_id=matched_agent_id,
        )
    )
    db.flush()


def evaluate(
    db: Session, *, tool_name: str, contact_id: str, space_id: str
) -> AccessDecision:
    """Decide whether `(tool_name, contact_id, space_id)` may proceed.

    `contact_id` is the respond.io contact id (`respond_contacts.respond_io_id`).
    `space_id` is the Respond.io external workspace id
    (`respond_workspaces.space_id`, e.g. ``"364817"``). It is resolved here to
    the internal workspace UUID before any FK comparison or log write.

    Special case: when both ``contact_id`` and ``space_id`` are empty, treat
    the call as a system / AI-assistant context (no Respond.io contact in
    play) and allow as long as the tool exists and is linked to at least
    one active agent. Backend authentication is still enforced by the
    underlying CRM endpoint via X-API-Key + permission gates.
    """
    is_system_call = not (contact_id or "").strip() and not (space_id or "").strip()

    workspace = (
        db.query(RespondWorkspace)
        .filter(RespondWorkspace.space_id == space_id)
        .one_or_none()
    )
    workspace_uuid = workspace.id if workspace is not None else None

    tool = (
        db.query(McpTool)
        .filter(McpTool.tool_name == tool_name, McpTool.is_active.is_(True))
        .one_or_none()
    )
    if tool is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=workspace_uuid,
            decision="deny_unknown_tool",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_tool", agent_name=None)

    linked_agents = (
        db.query(AccessAgent)
        .join(agent_mcp_tools, agent_mcp_tools.c.agent_id == AccessAgent.id)
        .filter(
            agent_mcp_tools.c.tool_id == tool.id,
            AccessAgent.is_active.is_(True),
        )
        .all()
    )
    if not linked_agents:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=workspace_uuid,
            decision="deny_tool_unlinked",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None)

    fallback_name = linked_agents[0].name

    if is_system_call:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=None,
            respond_contact_id=None,
            respond_workspace_id=None,
            decision="allow",
            matched_agent_id=linked_agents[0].id,
        )
        return AccessDecision(allowed=True, decision="allow", agent_name=fallback_name)

    if workspace_uuid is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=None,
            decision="deny_unknown_contact",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_contact", agent_name=fallback_name)

    contact = (
        db.query(RespondContact)
        .filter(
            RespondContact.respond_io_id == contact_id,
            RespondContact.workspace_id == workspace_uuid,
        )
        .one_or_none()
    )
    if contact is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=workspace_uuid,
            decision="deny_unknown_contact",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_contact", agent_name=fallback_name)

    now = datetime.utcnow()
    agent_ids = [a.id for a in linked_agents]
    granted = (
        db.query(ContactAgentAccess.agent_id)
        .filter(
            ContactAgentAccess.respond_contact_id == contact.id,
            ContactAgentAccess.agent_id.in_(agent_ids),
            ContactAgentAccess.is_allowed.is_(True),
            or_(ContactAgentAccess.valid_to.is_(None), ContactAgentAccess.valid_to > now),
            or_(ContactAgentAccess.valid_from.is_(None), ContactAgentAccess.valid_from <= now),
        )
        .first()
    )
    if granted is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=contact.id,
            respond_workspace_id=workspace_uuid,
            decision="deny_no_access",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_no_access", agent_name=fallback_name)

    matched_agent_id = granted[0]
    matched_name = next(
        (a.name for a in linked_agents if a.id == matched_agent_id),
        fallback_name,
    )
    _record_log(
        db,
        tool_name=tool_name,
        contact_external_id=contact_id,
        respond_contact_id=contact.id,
        respond_workspace_id=workspace_uuid,
        decision="allow",
        matched_agent_id=matched_agent_id,
    )
    return AccessDecision(allowed=True, decision="allow", agent_name=matched_name)
