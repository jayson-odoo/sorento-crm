"""Record-action write-tool startup bootstrap.

Runs after ``sync_catalog`` so the four record-action rows
(``crm_complaint_close`` / ``crm_order_cancel`` /
``crm_purchase_request_approve`` / ``crm_purchase_request_reject``) exist in
``mcp_tools``. Idempotently, for each tool:

1. Links the tool to its domain ``AccessAgent`` via ``agent_mcp_tools`` (so
   n8n agents tied to that agent can call it) — falling back to the
   ``general_enquiries`` agent when a domain agent is missing. Mirrors
   ``it_support_bootstrap`` (which links its tool to the ``it_support`` agent).
2. Appends the tool name to ``AIAssistantConfig.enabled_tools`` so the in-app
   AI assistant's Tool-RAG includes it as a candidate. The in-app chat does not
   use AccessAgent ownership — see ``ai_assistant_service: _rag_select_tools``,
   which filters candidates by this list. The write-confirmation gate
   (``_is_write_tool``) still halts each call until the user confirms.

All steps log + skip on missing prerequisites; the next startup retries.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool, agent_mcp_tools
from app.models.ai_assistant import AIAssistantConfig

logger = logging.getLogger(__name__)


# tool_name → preferred domain AccessAgent code. Falls back to FALLBACK_AGENT.
TOOL_AGENT_LINKS: dict[str, str] = {
    "crm_complaint_close": "complaint",
    "crm_order_cancel": "order_enquiries",
    "crm_purchase_request_approve": "purchase_request",
    "crm_purchase_request_reject": "purchase_request",
}
FALLBACK_AGENT = "general_enquiries"


def run(db: Session) -> dict:
    """Execute the bootstrap for all record-action tools. Returns a summary dict."""
    summary = {
        "tools_linked_to_agent": [],
        "tools_added_to_ai_assistant_enabled_tools": [],
    }
    for tool_name, agent_code in TOOL_AGENT_LINKS.items():
        try:
            if _link_tool_to_agent(db, tool_name, agent_code):
                summary["tools_linked_to_agent"].append(tool_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Record-action bootstrap: agent_mcp_tools link failed for %s: %s",
                tool_name,
                e,
            )
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    try:
        summary["tools_added_to_ai_assistant_enabled_tools"] = (
            _enable_tools_for_ai_assistant(db, list(TOOL_AGENT_LINKS.keys()))
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Record-action bootstrap: AI assistant enabled_tools update failed: %s", e
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    logger.info("Record-action bootstrap finished: %s", summary)
    return summary


def _link_tool_to_agent(db: Session, tool_name: str, agent_code: str) -> bool:
    tool = db.query(McpTool).filter(McpTool.tool_name == tool_name).first()
    if not tool:
        logger.info(
            "Record-action bootstrap: %s not yet in mcp_tools; will retry next startup",
            tool_name,
        )
        return False
    agent = (
        db.query(AccessAgent).filter(AccessAgent.code == agent_code).first()
        or db.query(AccessAgent).filter(AccessAgent.code == FALLBACK_AGENT).first()
    )
    if not agent:
        logger.info(
            "Record-action bootstrap: neither AccessAgent %s nor %s exists; skipping link for %s",
            agent_code,
            FALLBACK_AGENT,
            tool_name,
        )
        return False
    existing = db.execute(
        text(
            "SELECT 1 FROM agent_mcp_tools WHERE agent_id = :agent_id AND tool_id = :tool_id"
        ),
        {"agent_id": str(agent.id), "tool_id": str(tool.id)},
    ).first()
    if existing:
        return False
    db.execute(
        agent_mcp_tools.insert().values(agent_id=str(agent.id), tool_id=str(tool.id))
    )
    db.commit()
    logger.info(
        "Record-action bootstrap: linked %s to agent %s", tool_name, agent.code
    )
    return True


def _enable_tools_for_ai_assistant(db: Session, tool_names: list[str]) -> list[str]:
    config = db.query(AIAssistantConfig).first()
    if not config:
        logger.info(
            "Record-action bootstrap: AIAssistantConfig row missing; skipping enable"
        )
        return []
    enabled = list(config.enabled_tools or [])
    added: list[str] = []
    for tool_name in tool_names:
        if tool_name not in enabled:
            enabled.append(tool_name)
            added.append(tool_name)
    if added:
        config.enabled_tools = enabled
        db.commit()
        logger.info(
            "Record-action bootstrap: appended %s to AIAssistantConfig.enabled_tools",
            added,
        )
    return added
