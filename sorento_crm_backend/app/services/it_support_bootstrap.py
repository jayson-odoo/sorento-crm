"""IT-Support startup bootstrap.

Runs after ``sync_catalog`` so the ``crm_it_support_ticket_create`` row exists
in ``mcp_tools``. Idempotently:

1. Links the new tool to the ``it_support`` AccessAgent via
   ``agent_mcp_tools`` (so n8n agents tied to that agent can call it).
2. Appends the tool name to ``AIAssistantConfig.enabled_tools`` so the
   in-app AI assistant RAG includes it in candidate selection. The in-app
   chat does not use AccessAgent ownership — see ``ai_assistant_service:
   _rag_select_tools``, which filters candidates by this list.
3. Inserts a default ``form_sla_configs`` row for ``ticket`` /
   ``it_support`` / ``it_admin`` using the first available SLA policy
   (preferring ``NORMAL`` by name) so the SLA timer starts the moment a
   ticket is created — no admin intervention required.

All steps log + skip on missing prerequisites; the next startup retries.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool, agent_mcp_tools
from app.models.ai_assistant import AIAssistantConfig
from app.models.sla import FormSLAConfig, SLAPolicy

logger = logging.getLogger(__name__)


TOOL_NAME = "crm_it_support_ticket_create"
AGENT_CODE = "it_support"
TEAM_SET_CODE = "it_admin"
SOURCE_ENTITY_TYPE = "ticket"


def run(db: Session) -> dict:
    """Execute all bootstrap steps. Returns a small summary dict for logging."""
    summary = {
        "tool_linked_to_it_support_agent": False,
        "tool_added_to_ai_assistant_enabled_tools": False,
        "form_sla_config_seeded": False,
    }
    try:
        summary["tool_linked_to_it_support_agent"] = _link_tool_to_it_support_agent(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("IT support bootstrap: agent_mcp_tools link failed: %s", e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    try:
        summary["tool_added_to_ai_assistant_enabled_tools"] = _enable_tool_for_ai_assistant(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("IT support bootstrap: AI assistant enabled_tools update failed: %s", e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    try:
        summary["form_sla_config_seeded"] = _seed_default_form_sla_config(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("IT support bootstrap: form_sla_config seed failed: %s", e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    logger.info("IT support bootstrap finished: %s", summary)
    return summary


def _link_tool_to_it_support_agent(db: Session) -> bool:
    tool = db.query(McpTool).filter(McpTool.tool_name == TOOL_NAME).first()
    if not tool:
        logger.info(
            "IT support bootstrap: %s not yet in mcp_tools; will retry next startup",
            TOOL_NAME,
        )
        return False
    agent = db.query(AccessAgent).filter(AccessAgent.code == AGENT_CODE).first()
    if not agent:
        logger.info(
            "IT support bootstrap: AccessAgent %s missing; run migration 183",
            AGENT_CODE,
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
    logger.info("IT support bootstrap: linked %s to agent %s", TOOL_NAME, AGENT_CODE)
    return True


def _enable_tool_for_ai_assistant(db: Session) -> bool:
    config = db.query(AIAssistantConfig).first()
    if not config:
        logger.info("IT support bootstrap: AIAssistantConfig row missing; skipping enable")
        return False
    enabled = list(config.enabled_tools or [])
    if TOOL_NAME in enabled:
        return False
    enabled.append(TOOL_NAME)
    config.enabled_tools = enabled
    db.commit()
    logger.info(
        "IT support bootstrap: appended %s to AIAssistantConfig.enabled_tools",
        TOOL_NAME,
    )
    return True


def _seed_default_form_sla_config(db: Session) -> bool:
    existing = (
        db.query(FormSLAConfig)
        .filter(
            FormSLAConfig.source_entity_type == SOURCE_ENTITY_TYPE,
            FormSLAConfig.is_active.is_(True),
        )
        .first()
    )
    if existing:
        return False
    policy = (
        db.query(SLAPolicy).filter(SLAPolicy.name == "NORMAL").first()
        or db.query(SLAPolicy).order_by(SLAPolicy.created_at.asc()).first()
    )
    if not policy:
        logger.info(
            "IT support bootstrap: no SLA policy found; admin must seed one before tickets get SLA tracking"
        )
        return False
    config = FormSLAConfig(
        source_entity_type=SOURCE_ENTITY_TYPE,
        stage_code="main",
        policy_id=str(policy.id),
        agent_code=AGENT_CODE,
        team_set_code=TEAM_SET_CODE,
        start_event="submit",
        respond_event="responded",
        resolve_event="resolved",
        is_active=True,
    )
    db.add(config)
    db.commit()
    logger.info(
        "IT support bootstrap: seeded form_sla_configs row (policy=%s)", policy.name
    )
    return True
