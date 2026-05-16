"""Seed per-tool team bindings for the `general_enquiries` access agent.

Mapping (tier 1):
- crm_inventory_*       → Warehouse Executive
- crm_marketing_*       → Marketing - Promotion
- crm_master_product_*  → Purchasing Executive

Idempotent: ON CONFLICT DO NOTHING against the partial unique index
`uq_agent_mcp_tools_agent_tool_team_not_null`. Run as:

    python -m scripts.seed_general_enquiries_tool_team_bindings
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models.access import AccessAgent, McpTool, Team, agent_mcp_tools

logger = logging.getLogger(__name__)

AGENT_CODE = "general_enquiries"
RULES: list[tuple[str, str, int]] = [
    ("crm_inventory_", "Warehouse Executive", 1),
    ("crm_marketing_", "Marketing - Promotion", 1),
    ("crm_master_product_", "Purchasing Executive", 1),
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = SessionLocal()
    try:
        agent = db.query(AccessAgent).filter(AccessAgent.code == AGENT_CODE).one_or_none()
        if agent is None:
            logger.error("Agent %s not found", AGENT_CODE)
            return 1

        total_inserted = 0
        for prefix, team_name, tier in RULES:
            team = db.query(Team).filter(Team.name == team_name).one_or_none()
            if team is None:
                logger.error("Team %s not found, skipping prefix %s", team_name, prefix)
                continue
            tools = (
                db.query(McpTool)
                .filter(
                    McpTool.tool_name.like(prefix + "%"),
                    McpTool.is_active.is_(True),
                )
                .order_by(McpTool.tool_name.asc())
                .all()
            )
            if not tools:
                logger.warning("No active tools match %s*", prefix)
                continue

            values = [
                {
                    "agent_id": agent.id,
                    "tool_id": t.id,
                    "team_id": team.id,
                    "tier": tier,
                }
                for t in tools
            ]
            stmt = (
                pg_insert(agent_mcp_tools)
                .values(values)
                .on_conflict_do_nothing(
                    index_elements=["agent_id", "tool_id", "team_id"],
                    index_where=text("team_id IS NOT NULL"),
                )
            )
            result = db.execute(stmt)
            inserted = result.rowcount or 0
            total_inserted += inserted
            logger.info(
                "Prefix %s* → team %s (tier %d): %d tools, %d inserted",
                prefix,
                team_name,
                tier,
                len(tools),
                inserted,
            )

        db.commit()
        logger.info("Done. Total bindings inserted: %d", total_inserted)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
