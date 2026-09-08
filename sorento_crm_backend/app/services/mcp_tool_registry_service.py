"""Sync the persisted MCP tool catalog (`mcp_tools` table) from the code
catalog (`sorento_crm_mcp.catalog.CATALOG` + `merged_catalog` per-module
overlay).

Contract:
- Idempotent. Re-running with the same code catalog leaves rows untouched
  except for `last_seen_at`.
- Sync NEVER touches `agent_id`. Admin-set ownership survives every sync.
- Tools that disappear from the code catalog are flipped to `is_active=false`,
  not deleted. They come back to `is_active=true` if re-introduced.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.access import McpTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncReport:
    added: int
    updated: int
    deactivated: int


def _restricted_fields(spec) -> list[dict[str, str]]:
    """`ToolSpec.restricted_fields` (key, label) pairs, as the JSONB the table
    stores. `getattr` default so a `_FakeSpec` fixture with no such attribute -
    every tool that ships with nothing restricted - syncs to `[]`, not a crash.
    """
    pairs = getattr(spec, "restricted_fields", None) or ()
    return [{"key": key, "label": label} for key, label in pairs]


def _load_specs() -> Iterable:
    """Return every `ToolSpec` from the code catalog (base + per-module overlay).

    Isolated as a function so tests can monkeypatch it without importing the
    real MCP catalog.
    """
    from sorento_crm_mcp.catalog import CATALOG
    from sorento_crm_mcp.module_loader import merged_catalog

    return tuple(merged_catalog(CATALOG))


def sync_catalog(db: Session) -> SyncReport:
    sync_started_at = datetime.utcnow()
    specs = list(_load_specs())
    # `CHATBOT_TOOL_DOMAINS` is what `search_tool_chunks` filters a chatbot pool on
    # instead of the tool NAME - see `mcp_tools.chatbot_domain`'s own docstring for the
    # leak that forced it. It lives in `app/services/`, not `app/services/chatbot/`:
    # this is core, and core must never import the chatbot package (AC-002,
    # `tests/chatbot/test_import_boundary.py`) - D17, after D15 got that backwards.
    from app.services.mcp_tool_domains import CHATBOT_TOOL_DOMAINS

    added = 0
    updated = 0

    for spec in specs:
        existing = (
            db.query(McpTool).filter(McpTool.tool_name == spec.name).one_or_none()
        )
        chatbot_domain = CHATBOT_TOOL_DOMAINS.get(spec.name)
        if existing is None:
            db.add(
                McpTool(
                    id=str(uuid.uuid4()),
                    tool_name=spec.name,
                    description=spec.description,
                    module_key=getattr(spec, "module", "") or "",
                    http_path=spec.path,
                    http_method=spec.method,
                    is_active=True,
                    last_seen_at=sync_started_at,
                    restricted_fields=_restricted_fields(spec),
                    chatbot_domain=chatbot_domain,
                )
            )
            added += 1
            continue

        # Update mutable fields only. agent_id and id are NEVER touched.
        existing.description = spec.description
        existing.module_key = getattr(spec, "module", "") or ""
        existing.http_path = spec.path
        existing.http_method = spec.method
        existing.is_active = True
        existing.last_seen_at = sync_started_at
        existing.restricted_fields = _restricted_fields(spec)
        existing.chatbot_domain = chatbot_domain
        updated += 1

    db.flush()

    deactivated = (
        db.query(McpTool)
        .filter(McpTool.last_seen_at < sync_started_at, McpTool.is_active.is_(True))
        .update({"is_active": False}, synchronize_session=False)
    )

    logger.info(
        "MCP tool catalog sync: added=%d updated=%d deactivated=%d",
        added,
        updated,
        deactivated,
    )
    return SyncReport(added=added, updated=updated, deactivated=deactivated)
