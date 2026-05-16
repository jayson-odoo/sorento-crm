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

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool, Team, agent_mcp_tools

logger = logging.getLogger(__name__)


def list_tools_for_agent(db: Session, agent_id: str) -> list[McpTool]:
    """Return every active McpTool linked to ``agent_id`` (distinct), ordered by tool_name."""
    return (
        db.query(McpTool)
        .join(agent_mcp_tools, agent_mcp_tools.c.tool_id == McpTool.id)
        .filter(
            agent_mcp_tools.c.agent_id == agent_id,
            McpTool.is_active.is_(True),
        )
        .order_by(McpTool.tool_name.asc())
        .distinct()
        .all()
    )


def list_tool_bindings_for_agent(db: Session, agent_id: str) -> list[dict[str, Any]]:
    """Return per-(tool, team) binding rows owned by ``agent_id``.

    Rows with ``team_id`` NULL are legacy ownership entries that route via
    AgentTeam fan-out; team-bound rows are the new per-tool routing edges.
    """
    rows = (
        db.execute(
            select(
                agent_mcp_tools.c.id,
                McpTool.id.label("tool_id"),
                McpTool.tool_name,
                McpTool.module_key,
                McpTool.description,
                agent_mcp_tools.c.team_id,
                Team.name.label("team_name"),
                agent_mcp_tools.c.tier,
            )
            .select_from(agent_mcp_tools)
            .join(McpTool, McpTool.id == agent_mcp_tools.c.tool_id)
            .outerjoin(Team, Team.id == agent_mcp_tools.c.team_id)
            .where(
                agent_mcp_tools.c.agent_id == agent_id,
                McpTool.is_active.is_(True),
            )
            .order_by(McpTool.tool_name.asc(), Team.name.asc().nullslast())
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "tool_id": r.tool_id,
            "tool_name": r.tool_name,
            "module_key": r.module_key or "",
            "description": r.description,
            "team_id": r.team_id,
            "team_name": r.team_name,
            "tier": r.tier,
        }
        for r in rows
    ]


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
            .distinct()
        )
        .all()
    )
    by_tool: dict[str, list[tuple[str, str]]] = {}
    seen_by_tool: dict[str, set[str]] = {}
    for tool_id, ag_id, ag_name in rows:
        if ag_id in seen_by_tool.setdefault(tool_id, set()):
            continue
        seen_by_tool[tool_id].add(ag_id)
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
    """Replace ``agent_id``'s legacy (team_id NULL) tool ownership set.

    Touches only ``team_id IS NULL`` rows; team-bound bindings are managed
    separately by :func:`set_tool_bindings_for_agent`.
    """
    desired = {tid for tid in tool_ids if tid}

    existing_rows = db.execute(
        select(agent_mcp_tools.c.tool_id).where(
            agent_mcp_tools.c.agent_id == agent_id,
            agent_mcp_tools.c.team_id.is_(None),
        )
    ).all()
    existing = {row[0] for row in existing_rows}

    to_add = desired - existing
    to_remove = existing - desired

    if to_add:
        db.execute(
            pg_insert(agent_mcp_tools)
            .values(
                [
                    {"agent_id": agent_id, "tool_id": tid, "team_id": None, "tier": None}
                    for tid in to_add
                ]
            )
            .on_conflict_do_nothing(
                index_elements=["agent_id", "tool_id"],
                index_where=text("team_id IS NULL"),
            )
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
                agent_mcp_tools.c.team_id.is_(None),
                agent_mcp_tools.c.tool_id.in_(to_remove),
            )
        )
        for tid in to_remove:
            logger.info(
                "mcp_tool_unlinked",
                extra={"tool_id": tid, "agent_id": agent_id, "action": "unlinked"},
            )


def set_tool_bindings_for_agent(
    db: Session, agent_id: str, bindings: list[dict[str, Any]]
) -> None:
    """Replace ``agent_id``'s full tool/team binding set in one transaction.

    Each binding = ``{"tool_id": str, "team_id": str | None, "tier": int | None}``.
    Bindings with ``team_id`` None are legacy ownership rows (route via
    AgentTeam fan-out); bindings with ``team_id`` set route directly to that
    team for this tool.

    Duplicates inside ``bindings`` are de-duplicated by (tool_id, team_id).
    """
    seen: set[tuple[str, str | None]] = set()
    desired: dict[tuple[str, str | None], dict[str, Any]] = {}
    for b in bindings:
        tid = b.get("tool_id")
        if not tid:
            continue
        team_id = b.get("team_id") or None
        key = (tid, team_id)
        if key in seen:
            continue
        seen.add(key)
        desired[key] = {
            "agent_id": agent_id,
            "tool_id": tid,
            "team_id": team_id,
            "tier": b.get("tier"),
        }

    db.execute(
        agent_mcp_tools.delete().where(agent_mcp_tools.c.agent_id == agent_id)
    )
    if desired:
        db.execute(pg_insert(agent_mcp_tools).values(list(desired.values())))
    logger.info(
        "mcp_tool_bindings_replaced",
        extra={
            "agent_id": agent_id,
            "count": len(desired),
        },
    )
