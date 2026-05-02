"""AccessAgent <-> McpTool ownership service (many-to-many).

Tools and agents share a M:N relationship via ``agent_mcp_tools``. Each link
row stands for "agent X is allowed to invoke tool Y".

``set_tools_for_agent`` is replace-semantics in a single transaction:
1. Insert links for any tool in ``tool_ids`` not already linked to ``agent_id``.
2. Delete links for tools currently linked to ``agent_id`` but not in ``tool_ids``.

Reassignments are logged with structured fields (tool_id, agent_id, action) so
audits can reconstruct ownership history.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool, agent_mcp_tools

logger = logging.getLogger(__name__)


def list_tools_for_agent(db: Session, agent_id: str) -> list[McpTool]:
    """Return every active McpTool linked to ``agent_id``, ordered by tool_name."""
    return (
        db.query(McpTool)
        .join(agent_mcp_tools, agent_mcp_tools.c.tool_id == McpTool.id)
        .filter(
            agent_mcp_tools.c.agent_id == agent_id,
            McpTool.is_active.is_(True),
        )
        .order_by(McpTool.tool_name.asc())
        .all()
    )


def list_picker_tools(
    db: Session, *, only_active: bool = True, limit: int = 500
) -> list[dict[str, Any]]:
    """Return tools for the AccessAgentForm picker.

    With many-to-many, a single tool can belong to multiple agents. Each row
    carries the comma-separated list of agent ids/names already linked, so the
    UI can show "shared with X, Y" instead of warning about reassignment.
    """
    q = db.query(McpTool)
    if only_active:
        q = q.filter(McpTool.is_active.is_(True))
    q = q.order_by(McpTool.module_key.asc(), McpTool.tool_name.asc()).limit(limit)
    tools = q.all()
    if not tools:
        return []

    tool_ids = [t.id for t in tools]
    rows = (
        db.execute(
            select(
                agent_mcp_tools.c.tool_id,
                AccessAgent.id,
                AccessAgent.name,
            )
            .select_from(agent_mcp_tools)
            .join(AccessAgent, AccessAgent.id == agent_mcp_tools.c.agent_id)
            .where(agent_mcp_tools.c.tool_id.in_(tool_ids))
        )
        .all()
    )
    by_tool: dict[str, list[tuple[str, str]]] = {}
    for tool_id, ag_id, ag_name in rows:
        by_tool.setdefault(tool_id, []).append((ag_id, ag_name))

    out: list[dict[str, Any]] = []
    for tool in tools:
        owners = by_tool.get(tool.id, [])
        out.append(
            {
                "id": tool.id,
                "tool_name": tool.tool_name,
                "description": tool.description,
                "module_key": tool.module_key or "",
                "current_agent_ids": [ag_id for ag_id, _ in owners],
                "current_agent_names": [ag_name for _, ag_name in owners],
            }
        )
    return out


def set_tools_for_agent(db: Session, agent_id: str, tool_ids: list[str]) -> None:
    """Replace ``agent_id``'s tool ownership set in one transaction."""
    desired = {tid for tid in tool_ids if tid}

    existing_rows = db.execute(
        select(agent_mcp_tools.c.tool_id).where(
            agent_mcp_tools.c.agent_id == agent_id
        )
    ).all()
    existing = {row[0] for row in existing_rows}

    to_add = desired - existing
    to_remove = existing - desired

    if to_add:
        db.execute(
            pg_insert(agent_mcp_tools)
            .values([{"agent_id": agent_id, "tool_id": tid} for tid in to_add])
            .on_conflict_do_nothing()
        )
        for tid in to_add:
            logger.info(
                "mcp_tool_linked",
                extra={"tool_id": tid, "agent_id": agent_id, "action": "linked"},
            )

    if to_remove:
        db.execute(
            agent_mcp_tools.delete().where(
                agent_mcp_tools.c.agent_id == agent_id,
                agent_mcp_tools.c.tool_id.in_(to_remove),
            )
        )
        for tid in to_remove:
            logger.info(
                "mcp_tool_unlinked",
                extra={"tool_id": tid, "agent_id": agent_id, "action": "unlinked"},
            )
