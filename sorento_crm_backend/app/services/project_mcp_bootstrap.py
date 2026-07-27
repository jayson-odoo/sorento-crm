"""Make the project MCP tools usable without an admin visiting a settings screen (AC-K1).

The AC says "`agent_mcp_tools` links are seeded by the startup hook". That table, and the
tool-to-agent ownership model behind it, were REMOVED when n8n took over agent and team
routing -- see the `McpTool` docstring, which now describes a pure catalog. So the letter of
the AC no longer has a target; its INTENT does, and it takes two steps:

1. **Enable the tools for the in-app assistant.** `AIAssistantConfig.enabled_tools` is what
   the assistant's RAG selects candidates from (`ai_assistant_service._rag_select_tools`). A
   tool absent from it is invisible no matter how good its description is, which is exactly
   the "shipped but nobody enabled it" failure the AC was written to prevent.
   `it_support_bootstrap` maintains the same list for the same reason.

2. **Let the integration principals read projects.** Integration principals (`sorento-mcp`,
   `n8n`, `foundryx-esb`) were seeded with the ADMIN permission set as it stood at THEIR seed
   time, and nothing back-fills a permission introduced by a later module. Without the grant
   below, every project tool 403s forever while looking perfectly configured: in the catalog,
   enabled for the assistant, key authenticating. Found by calling the tools against a
   running stack, which is the only place it shows.

Both steps are idempotent and additive, run at startup after `sync_catalog` and
`sync_permissions`. Missing prerequisites log and skip; the next boot retries.
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Read-only by construction (AC-K2): every one is a GET. No write-capable project tool ships
# until AI-assisted quotation editing gets its own grill -- confirm-gate, diff preview,
# version semantics and price-floor enforcement on AI-written lines are each a decision.
PROJECT_TOOLS: tuple[str, ...] = (
    "crm_projects_list",
    "crm_project_detail",
    "crm_project_forecast",
    "crm_project_quotations_list",
)

READ_PERMISSION = "projects.projects.view"


def run(db: Session) -> Dict[str, int]:
    """Enable the project tools and make sure the integration principals may read them."""
    summary = {"tools_enabled": 0, "permissions_granted": 0}

    try:
        summary["tools_enabled"] = _enable_tools_for_assistant(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Project MCP bootstrap: enabling tools failed: %s", exc)
        _safe_rollback(db)

    try:
        summary["permissions_granted"] = _grant_read_to_integration_roles(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Project MCP bootstrap: permission grant failed: %s", exc)
        _safe_rollback(db)

    return summary


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass


def _enable_tools_for_assistant(db: Session) -> int:
    from app.models.ai_assistant import AIAssistantConfig

    config = db.query(AIAssistantConfig).first()
    if config is None:
        # A fresh install has no assistant configured yet. Not an error: the next boot after
        # somebody configures it picks these up.
        logger.info("Project MCP bootstrap: no AIAssistantConfig row yet; skipping enable")
        return 0

    enabled = list(config.enabled_tools or [])
    missing = [name for name in PROJECT_TOOLS if name not in enabled]
    if not missing:
        return 0

    # Append, never re-order or prune: the list is shared with every other module's tools.
    config.enabled_tools = enabled + missing
    db.flush()
    db.commit()
    logger.info("Project MCP bootstrap: enabled %s", ", ".join(missing))
    return len(missing)


def _grant_read_to_integration_roles(db: Session) -> int:
    """Grant `projects.projects.view` to every role an INTEGRATION acts as. Returns grants.

    Deliberately narrow on all three axes:

    * ONE permission, and a read one. An integration that could write projects would make
      AC-K2 a statement about the tool catalog rather than about the system.
    * Only roles reachable from an `integrations.act_as_user_id`. A boot that quietly widened
      a HUMAN role would be a security incident waiting to be discovered.
    * Only where missing, so re-running grants nothing.

    The honest trade: an admin who revokes this permission gets it back on the next boot. The
    alternative is tools that 403 with no diagnosable cause, and "read revoked while the tools
    are enabled" is a contradiction better resolved by disabling the tools.
    """
    from app.models.integration import Integration
    from app.models.user import UserPermission, UserRoleAssignment, UserRolePermission

    permission = (
        db.query(UserPermission).filter(UserPermission.slug == READ_PERMISSION).first()
    )
    if permission is None:
        # `sync_permissions` also runs at startup; if it has not yet, the next boot retries.
        logger.info(
            "Project MCP bootstrap: %s not registered yet; skipping grant", READ_PERMISSION
        )
        return 0

    act_as_ids = [
        row[0]
        for row in db.query(Integration.act_as_user_id)
        .filter(Integration.act_as_user_id.isnot(None))
        .all()
    ]
    if not act_as_ids:
        return 0

    role_ids = {
        row[0]
        for row in db.query(UserRoleAssignment.role_id)
        .filter(UserRoleAssignment.user_id.in_(act_as_ids))
        .all()
    }
    if not role_ids:
        return 0

    already = {
        row[0]
        for row in db.query(UserRolePermission.role_id)
        .filter(
            UserRolePermission.role_id.in_(role_ids),
            UserRolePermission.permission_id == permission.id,
        )
        .all()
    }

    granted = 0
    for role_id in sorted(role_ids - already):
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=role_id, permission_id=permission.id
            )
        )
        granted += 1
    if granted:
        db.flush()
        db.commit()
        logger.info(
            "Project MCP bootstrap: granted %s to %d integration role(s)",
            READ_PERMISSION,
            granted,
        )
    return granted
