"""AccessAgent ↔ McpTool ownership service (Phase 2).

Tools are N:1 to access agents — each `mcp_tools.agent_id` either points at
exactly one agent or is NULL.

`set_tools_for_agent` is replace-semantics in a single transaction:
1. Claim every tool in `tool_ids` for `agent_id` (overwrites any prior owner).
2. Release every tool currently owned by `:agent_id` not in `tool_ids` get `agent_id = NULL`.

Reassignment of a tool from one agent to another is logged with structured
fields (tool_id, from_agent_id, to_agent_id) so audits can reconstruct
ownership history.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool

logger = logging.getLogger(__name__)


def list_tools_for_agent(db: Session, agent_id: str) -> list[McpTool]:
    """Return every active McpTool owned by `agent_id`, ordered by tool_name."""
    return (
        db.query(McpTool)
        .filter(McpTool.agent_id == agent_id, McpTool.is_active.is_(True))
        .order_by(McpTool.tool_name.asc())
        .all()
    )


def list_picker_tools(
    db: Session, *, only_active: bool = True, limit: int = 500
) -> list[dict[str, Any]]:
    """Return tools for the AccessAgentForm picker.

    Joins to `access_agents` so the UI can render "currently owned by X"
    warnings before the admin reassigns. Active tools only by default —
    inactive tools (deactivated by sync) are normally hidden.
    """
    q = (
        db.query(McpTool, AccessAgent.name)
        .outerjoin(AccessAgent, AccessAgent.id == McpTool.agent_id)
    )
    if only_active:
        q = q.filter(McpTool.is_active.is_(True))
    q = q.order_by(McpTool.module_key.asc(), McpTool.tool_name.asc()).limit(limit)

    rows: list[dict[str, Any]] = []
    for tool, agent_name in q.all():
        rows.append(
            {
                "id": tool.id,
                "tool_name": tool.tool_name,
                "description": tool.description,
                "module_key": tool.module_key or "",
                "current_agent_id": tool.agent_id,
                "current_agent_name": agent_name,
            }
        )
    return rows


def set_tools_for_agent(db: Session, agent_id: str, tool_ids: list[str]) -> None:
    """Replace `agent_id`'s tool ownership set.

    Single transaction:
    - Tools in `tool_ids` get `agent_id = :agent_id` (claim / reassign).
    - Tools currently owned by `:agent_id` not in `tool_ids` get `agent_id = NULL`.
    """
    if tool_ids:
        prior = {
            t.id: t.agent_id
            for t in db.query(McpTool).filter(McpTool.id.in_(tool_ids)).all()
        }
    else:
        prior = {}

    if tool_ids:
        db.query(McpTool).filter(McpTool.id.in_(tool_ids)).update(
            {"agent_id": agent_id}, synchronize_session=False
        )

    release_q = db.query(McpTool).filter(McpTool.agent_id == agent_id)
    if tool_ids:
        release_q = release_q.filter(~McpTool.id.in_(tool_ids))
    release_q.update({"agent_id": None}, synchronize_session=False)

    for tid, old in prior.items():
        if old is not None and old != agent_id:
            logger.info(
                "mcp_tool_reassigned",
                extra={
                    "tool_id": tid,
                    "from_agent_id": old,
                    "to_agent_id": agent_id,
                },
            )
