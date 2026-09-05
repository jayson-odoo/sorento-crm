"""The contact-to-agent access check, in process.

n8n POSTs `/external/access-agent/check` and puts the response on `ctx.access`. The port
calls the SAME service that endpoint calls, so the item shape on `ctx.access` is
byte-identical - which matters because `route-turn` spreads it into its own output and
every n8n node downstream of the migration boundary still reads those keys by name.

Not an MCP tool and not an HTTP hop: this is a service call in the same process.
`space_id` comes from the default respond workspace row rather than n8n's hard-coded
`364817` (D5).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.mcp_access_service import evaluate_agent

logger = logging.getLogger(__name__)


def check_access(
    db: Session,
    *,
    agent_code: Any,
    contact_id: str,
    space_id: str | None,
) -> dict[str, Any]:
    """`ctx.access`: `{allowed, decision, agent_name, attributes, all_attributes_allowed}`.

    `attributes` / `all_attributes_allowed` are the per-field answers the endpoint only
    computes when a caller asks for them. The spine never does, so both stay null and the
    shape still matches what `check-access` returns today.

    An unknown agent fails CLOSED (`deny_unknown_agent`) - `deriveRouting`'s `ideate` case
    is the single source of truth for that agent name, and the denial message is rendered
    from the same field, so a stale agent cannot make the refusal say the wrong thing.
    """
    decision = evaluate_agent(
        db,
        agent_code=agent_code,
        contact_id=contact_id,
        space_id=space_id,
    )
    return {
        "allowed": decision.allowed,
        "decision": decision.decision,
        "agent_name": decision.agent_name,
        "attributes": None,
        "all_attributes_allowed": None,
    }


def default_space_id(db: Session) -> str | None:
    """The default respond workspace's `space_id` (D5, kills the hard-coded 364817)."""
    from app.services.respond_workspace_service import RespondWorkspaceService

    try:
        workspace = RespondWorkspaceService(db).get_default()
    except Exception:  # noqa: BLE001 - a missing workspace must not fail the turn here
        logger.warning("chatbot: default respond workspace lookup failed", exc_info=True)
        return None
    space_id = getattr(workspace, "space_id", None) if workspace is not None else None
    return str(space_id) if space_id else None
