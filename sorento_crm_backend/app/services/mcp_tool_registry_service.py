"""Sync the persisted MCP tool catalog (`mcp_tools` table) from the code
catalog: the backend's verbatim copy `app/services/mcp_catalog_copy.py` of
`sorento_crm_mcp/sorento_crm_mcp/catalog.py`.

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

from sqlalchemy import text
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
    """Return every `ToolSpec` from the code catalog.

    Read from the backend's own copy because the backend image has no
    `sorento_crm_mcp` package (built from `./sorento_crm_backend` alone): the
    old `from sorento_crm_mcp.catalog import CATALOG` failed on every production
    boot and the table was never synced (MCP-REGISTRY-IMAGE, 2 Nov 2026).
    `tests/test_mcp_catalog_in_image.py` keeps the copy byte-identical.

    No per-module `tools.json` overlay: no module ships one, and production's
    MCP server (its own image) cannot see the backend's modules either, so this
    is exactly the set it serves.

    Isolated as a function so tests can monkeypatch it.
    """
    from app.services.mcp_catalog_copy import CATALOG

    return CATALOG


def sync_catalog(db: Session) -> SyncReport:
    # Each gunicorn worker runs `startup_event`, so several syncs start at once on
    # every boot. Without the lock they insert the same new names and all but one
    # fail on the unique `tool_name`; this makes them queue. Released at commit.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('mcp_tools.sync_catalog'))"))
    sync_started_at = datetime.utcnow()
    specs = list(_load_specs())
    # `CHATBOT_TOOL_DOMAINS` is stamped onto `mcp_tools.chatbot_domain`, which nothing
    # reads since the chatbot's tool search was dropped (8 Sep 2026) - see that column's
    # own docstring. It lives in `app/services/`, not `app/services/chatbot/`:
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
