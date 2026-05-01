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

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
)

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
    `space_id` is the respond workspace id (`respond_contacts.respond_workspace_id`).
    """
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
            respond_workspace_id=space_id,
            decision="deny_unknown_tool",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_tool", agent_name=None)

    if tool.agent_id is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_tool_unlinked",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None)

    owner = (
        db.query(AccessAgent)
        .filter(AccessAgent.id == tool.agent_id, AccessAgent.is_active.is_(True))
        .one_or_none()
    )
    if owner is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_tool_unlinked",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None)

    contact = (
        db.query(RespondContact)
        .filter(
            RespondContact.respond_io_id == contact_id,
            RespondContact.workspace_id == space_id,
        )
        .one_or_none()
    )
    if contact is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_unknown_contact",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_contact", agent_name=owner.name)

    now = datetime.utcnow()
    granted = (
        db.query(ContactAgentAccess.id)
        .filter(
            ContactAgentAccess.respond_contact_id == contact.id,
            ContactAgentAccess.agent_id == owner.id,
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
            respond_workspace_id=space_id,
            decision="deny_no_access",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_no_access", agent_name=owner.name)

    _record_log(
        db,
        tool_name=tool_name,
        contact_external_id=contact_id,
        respond_contact_id=contact.id,
        respond_workspace_id=space_id,
        decision="allow",
        matched_agent_id=owner.id,
    )
    return AccessDecision(allowed=True, decision="allow", agent_name=owner.name)
