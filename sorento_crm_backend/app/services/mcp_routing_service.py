"""Tool→team routing lookup.

For a given MCP tool, joins agent_mcp_tools × AccessAgent × AgentTeam × Team to
return the deterministic list of (team_code, team_name, agent_code,
agent_name, tier) entries that the chatbot can offer as escalation targets
when the tool returns empty / not-found.

Used both by the MCP server wrapper (to auto-attach `suggested_escalation` to
empty tool responses) and by an external/admin route for n8n or frontend
inspection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import AccessAgent, AgentTeam, McpTool, Team, agent_mcp_tools


@dataclass(frozen=True)
class RoutingEntry:
    team_code: str
    team_name: str
    agent_code: str
    agent_name: str
    tier: Optional[int]


@dataclass(frozen=True)
class RoutingResult:
    tool_name: str
    entries: list[RoutingEntry]
    primary: Optional[RoutingEntry]

    def to_payload(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "entries": [
                {
                    "team_code": e.team_code,
                    "team_name": e.team_name,
                    "agent_code": e.agent_code,
                    "agent_name": e.agent_name,
                    "tier": e.tier,
                }
                for e in self.entries
            ],
            "primary": (
                {
                    "team_code": self.primary.team_code,
                    "team_name": self.primary.team_name,
                    "agent_code": self.primary.agent_code,
                    "agent_name": self.primary.agent_name,
                    "tier": self.primary.tier,
                }
                if self.primary is not None
                else None
            ),
        }


def _format_escalation_message(team_name: str) -> str:
    return f"We don't have that information available. Would you like me to route you to our {team_name} team?"


def resolve_tool_routing(db: Session, tool_name: str) -> RoutingResult:
    """Return routing entries for `tool_name`, ordered by tier ascending.

    Tier-NULL rows sort last (treated as catch-all). Result entries may be empty
    if the tool is unknown or is not linked to any active agent with a team set.
    """
    tool = (
        db.query(McpTool)
        .filter(McpTool.tool_name == tool_name, McpTool.is_active.is_(True))
        .one_or_none()
    )
    if tool is None:
        return RoutingResult(tool_name=tool_name, entries=[], primary=None)

    # Prefer per-tool team bindings in `agent_mcp_tools` (team_id NOT NULL).
    # Falls back to legacy AgentTeam fan-out only when no per-tool binding
    # exists for this tool.
    bound_rows = (
        db.query(
            Team.id.label("team_code"),
            Team.name.label("team_name"),
            AccessAgent.code.label("agent_code"),
            AccessAgent.name.label("agent_name"),
            agent_mcp_tools.c.tier.label("tier"),
        )
        .join(AccessAgent, AccessAgent.id == agent_mcp_tools.c.agent_id)
        .join(Team, Team.id == agent_mcp_tools.c.team_id)
        .filter(
            agent_mcp_tools.c.tool_id == tool.id,
            agent_mcp_tools.c.team_id.isnot(None),
            AccessAgent.is_active.is_(True),
        )
        .all()
    )
    if bound_rows:
        rows = bound_rows
    else:
        rows = (
            db.query(
                AgentTeam.code.label("team_code"),
                Team.name.label("team_name"),
                AccessAgent.code.label("agent_code"),
                AccessAgent.name.label("agent_name"),
                AgentTeam.tier.label("tier"),
            )
            .join(AccessAgent, AccessAgent.id == AgentTeam.agent_id)
            .join(agent_mcp_tools, agent_mcp_tools.c.agent_id == AccessAgent.id)
            .join(Team, Team.id == AgentTeam.team_id)
            .filter(
                agent_mcp_tools.c.tool_id == tool.id,
                AccessAgent.is_active.is_(True),
            )
            .all()
        )

    def _tier_sort_key(r):
        return (0, r.tier) if r.tier is not None else (1, 0)

    rows_sorted = sorted(rows, key=_tier_sort_key)

    seen: set[tuple[str, str]] = set()
    entries: list[RoutingEntry] = []
    for r in rows_sorted:
        key = (r.team_code, r.agent_code)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            RoutingEntry(
                team_code=r.team_code,
                team_name=r.team_name,
                agent_code=r.agent_code,
                agent_name=r.agent_name,
                tier=r.tier,
            )
        )

    primary = entries[0] if entries else None
    return RoutingResult(tool_name=tool_name, entries=entries, primary=primary)


def build_suggested_escalation(db: Session, tool_name: str) -> Optional[dict]:
    """Build the `suggested_escalation` payload attached to empty tool results.

    Returns None when there is no routable team for the tool — caller should
    omit the field in that case.
    """
    result = resolve_tool_routing(db, tool_name)
    if result.primary is None:
        return None
    return {
        "team": result.primary.team_code,
        "team_name": result.primary.team_name,
        "agent": result.primary.agent_code,
        "agent_display_name": result.primary.agent_name,
        "tier": result.primary.tier,
        "message": _format_escalation_message(result.primary.team_name),
        "alternatives": [
            {
                "team": e.team_code,
                "team_name": e.team_name,
                "agent": e.agent_code,
                "tier": e.tier,
            }
            for e in result.entries[1:]
        ],
    }
