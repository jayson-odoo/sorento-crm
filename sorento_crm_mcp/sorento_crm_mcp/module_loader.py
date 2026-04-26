"""
Discover per-module MCP tool slices from the backend modules tree.

When a backend module ships `app/modules/<key>/mcp/tools.json`, those tools merge
into the runtime catalog at startup. The central CATALOG remains the legacy/fallback
source.

tools.json format mirrors ToolSpec:
[
  {
    "name": "crm_notifications_list",
    "description": "...",
    "path": "/api/v1/notifications",
    "path_params": [],
    "query_params": ["page", "limit"],
    "method": "GET",
    "body_params": []
  }
]
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from sorento_crm_mcp.catalog import ToolSpec

logger = logging.getLogger(__name__)


def _backend_modules_root() -> Path | None:
    """
    Resolve the path to sorento_crm_backend/app/modules/.

    Order:
      1. CRM_BACKEND_MODULES_DIR env var
      2. Repo-relative guess (../sorento_crm_backend/app/modules from this file)
    """
    explicit = os.environ.get("CRM_BACKEND_MODULES_DIR")
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_dir() else None
    here = Path(__file__).resolve()
    candidate = here.parents[2] / "sorento_crm_backend" / "app" / "modules"
    return candidate if candidate.is_dir() else None


def _load_tools_json(path: Path, module_key: str) -> list[ToolSpec]:
    try:
        raw = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read %s: %s", path, exc)
        return []
    if not isinstance(raw, list):
        logger.warning("%s must be a JSON array", path)
        return []
    out: list[ToolSpec] = []
    for entry in raw:
        try:
            out.append(
                ToolSpec(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    path=entry["path"],
                    path_params=tuple(entry.get("path_params") or ()),
                    query_params=tuple(entry.get("query_params") or ()),
                    method=entry.get("method", "GET"),
                    body_params=tuple(entry.get("body_params") or ()),
                    module=module_key,
                )
            )
        except KeyError as exc:
            logger.warning("Skipping malformed tool in %s: missing %s", path, exc)
    return out


def discover_module_tools() -> list[ToolSpec]:
    root = _backend_modules_root()
    if root is None:
        return []
    out: list[ToolSpec] = []
    for module_dir in sorted(root.iterdir()):
        if not module_dir.is_dir():
            continue
        tools_file = module_dir / "mcp" / "tools.json"
        if tools_file.is_file():
            out.extend(_load_tools_json(tools_file, module_dir.name))
    if out:
        logger.info("Discovered %d MCP tools from per-module slices", len(out))
    return out


def merged_catalog(base_catalog: tuple[ToolSpec, ...]) -> tuple[ToolSpec, ...]:
    """Return base_catalog + discovered, with discovered overriding by name."""
    discovered = discover_module_tools()
    if not discovered:
        return base_catalog
    by_name: dict[str, ToolSpec] = {t.name: t for t in base_catalog}
    for t in discovered:
        by_name[t.name] = t
    return tuple(by_name.values())
