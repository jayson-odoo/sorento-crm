"""Sales-report startup bootstrap (S3, PLAN-chatbot-sales-report.md, AC-1642).

Mirrors ``outstanding_report_bootstrap.py`` exactly, for the sibling tool
``crm_sales_report``: runs after ``sync_catalog`` so the ``crm_sales_report`` row
exists in ``mcp_tools``, then appends the tool name to
``AIAssistantConfig.enabled_tools`` so the in-app AI assistant's RAG includes it in
candidate selection (``ai_assistant_service._rag_select_tools`` filters candidates
by this list). Without this, a tool sitting in the code catalog is invisible to
that selector.

The chatbot lane (a DIFFERENT consumer - it picks tools from its own DOMAIN_SPEC
pools, not this list) is wired to the sales report separately (S4); this bootstrap
only concerns the in-app assistant.

Idempotent and additive: appends once, never reorders or prunes the list (shared
with every other module's tools), and skips (does not raise) when no
``AIAssistantConfig`` row exists yet - the next startup retries.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig

logger = logging.getLogger(__name__)

TOOL_NAME = "crm_sales_report"


def run(db: Session) -> dict:
    """Execute the bootstrap. Returns a small summary dict for logging."""
    summary = {"tool_added_to_ai_assistant_enabled_tools": False}
    try:
        summary["tool_added_to_ai_assistant_enabled_tools"] = _enable_tool_for_ai_assistant(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("Sales report bootstrap: AI assistant enabled_tools update failed: %s", e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    logger.info("Sales report bootstrap finished: %s", summary)
    return summary


def _enable_tool_for_ai_assistant(db: Session) -> bool:
    config = db.query(AIAssistantConfig).first()
    if not config:
        logger.info("Sales report bootstrap: AIAssistantConfig row missing; skipping enable")
        return False
    enabled = list(config.enabled_tools or [])
    if TOOL_NAME in enabled:
        return False
    enabled.append(TOOL_NAME)
    config.enabled_tools = enabled
    db.commit()
    logger.info(
        "Sales report bootstrap: appended %s to AIAssistantConfig.enabled_tools",
        TOOL_NAME,
    )
    return True
