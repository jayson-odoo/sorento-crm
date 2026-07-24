"""Contact→agent access decision service.

Single entry point: ``evaluate_agent(db, agent_code=..., contact_id=..., space_id=...)``,
called by n8n via ``POST /api/v1/external/access-agent/check`` before it routes a
conversation to an agent.

Access is enforced per *agent* only. The former per-*tool* guard (``evaluate``)
and its ``mcp_access_log`` audit table were removed once n8n took over agent and
team routing — ``mcp_tools`` remains a pure catalog with no ownership model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, ContactAgentAccess, RespondContact
from app.models.respond_workspace import RespondWorkspace

logger = logging.getLogger(__name__)

Decision = Literal[
    "allow",
    "deny_no_access",
    "deny_unknown_contact",
    "deny_unknown_agent",
]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    decision: Decision
    agent_name: str | None


def evaluate_agent(
    db: Session, *, agent_code: str, contact_id: str, space_id: str
) -> AccessDecision:
    """Decide whether `(contact_id, space_id)` is allowed to invoke `agent_code`.

    `agent_code` matches ``access_agents.code``; the agent must be active.
    Resolves the workspace by ``space_id`` (external Respond.io id), then the
    contact by ``(respond_io_id, workspace_uuid)``, then checks
    ``contact_agent_access`` for an allowed row inside the current time window.
    """
    agent = (
        db.query(AccessAgent)
        .filter(AccessAgent.code == agent_code, AccessAgent.is_active.is_(True))
        .one_or_none()
    )
    if agent is None:
        return AccessDecision(allowed=False, decision="deny_unknown_agent", agent_name=None)

    workspace = (
        db.query(RespondWorkspace)
        .filter(RespondWorkspace.space_id == space_id)
        .one_or_none()
    )
    if workspace is None:
        return AccessDecision(
            allowed=False, decision="deny_unknown_contact", agent_name=agent.name
        )

    contact = (
        db.query(RespondContact)
        .filter(
            RespondContact.respond_io_id == contact_id,
            RespondContact.workspace_id == workspace.id,
        )
        .one_or_none()
    )
    if contact is None:
        return AccessDecision(
            allowed=False, decision="deny_unknown_contact", agent_name=agent.name
        )

    now = datetime.utcnow()
    granted = (
        db.query(ContactAgentAccess.agent_id)
        .filter(
            ContactAgentAccess.respond_contact_id == contact.id,
            ContactAgentAccess.agent_id == agent.id,
            ContactAgentAccess.is_allowed.is_(True),
            or_(ContactAgentAccess.valid_to.is_(None), ContactAgentAccess.valid_to > now),
            or_(ContactAgentAccess.valid_from.is_(None), ContactAgentAccess.valid_from <= now),
        )
        .first()
    )
    if granted is None:
        return AccessDecision(
            allowed=False, decision="deny_no_access", agent_name=agent.name
        )

    return AccessDecision(allowed=True, decision="allow", agent_name=agent.name)
