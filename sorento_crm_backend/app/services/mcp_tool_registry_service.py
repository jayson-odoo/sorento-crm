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


def _chatbot_domain_by_tool() -> dict[str, str]:
    """Invert `DOMAIN_SPEC[domain].tools` into `{tool_name: domain}` (D9, 8 Sep 2026).

    This is what `search_tool_chunks` filters a chatbot pool on instead of the tool
    NAME - see `mcp_tools.chatbot_domain`'s own docstring for the leak that forced it.
    A tool listed under two domains is a `DOMAIN_SPEC` authoring defect (one domain
    per tool is the invariant `tests/chatbot/test_domain_spec.py` also checks
    statically), so it raises here rather than silently picking one.
    """
    from app.services.chatbot.contracts import DOMAIN_SPEC

    by_tool: dict[str, str] = {}
    for domain, spec in DOMAIN_SPEC.items():
        for tool_name in spec.tools:
            existing_domain = by_tool.get(tool_name)
            if existing_domain is not None and existing_domain != domain:
                raise ValueError(
                    f"Tool {tool_name!r} is listed under two DOMAIN_SPEC domains: "
                    f"{existing_domain!r} and {domain!r}"
                )
            by_tool[tool_name] = domain
    return by_tool


def sync_catalog(db: Session) -> SyncReport:
    sync_started_at = datetime.utcnow()
    specs = list(_load_specs())
    domain_by_tool = _chatbot_domain_by_tool()

    added = 0
    updated = 0

    for spec in specs:
        existing = (
            db.query(McpTool).filter(McpTool.tool_name == spec.name).one_or_none()
        )
        chatbot_domain = domain_by_tool.get(spec.name)
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
