"""Record-action write-tool startup bootstrap.

Runs after ``sync_catalog`` so the four record-action rows
(``crm_complaint_close`` / ``crm_order_cancel`` /
``crm_purchase_request_approve`` / ``crm_purchase_request_reject``) exist in
``mcp_tools``. Idempotently, for each tool it appends the tool name to
``AIAssistantConfig.enabled_tools`` so the in-app AI assistant's Tool-RAG
includes it as a candidate — see ``ai_assistant_service: _rag_select_tools``,
which filters candidates by this list. The write-confirmation gate
(``_is_write_tool``) still halts each call until the user confirms.

Tool→AccessAgent linking used to happen here too; it was dropped along with the
tool-ownership model once n8n took over agent/team routing.

All steps log + skip on missing prerequisites; the next startup retries.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.access import McpTool
from app.models.ai_assistant import AIAssistantConfig

logger = logging.getLogger(__name__)


RECORD_ACTION_TOOLS: list[str] = [
    "crm_complaint_close",
    "crm_order_cancel",
    "crm_purchase_request_approve",
    "crm_purchase_request_reject",
]


def run(db: Session) -> dict:
    """Execute the bootstrap for all record-action tools. Returns a summary dict."""
    summary = {
        "tools_added_to_ai_assistant_enabled_tools": [],
    }
    try:
        summary["tools_added_to_ai_assistant_enabled_tools"] = (
            _enable_tools_for_ai_assistant(db, list(RECORD_ACTION_TOOLS))
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
