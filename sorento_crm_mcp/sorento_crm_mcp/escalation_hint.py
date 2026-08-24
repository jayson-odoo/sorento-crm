"""Auto-attach `suggested_escalation` to empty MCP tool responses.

When a list-style tool returns `data: []` or a get-style tool returns
not-found, we lookup the tool's routing (team/agent) via the backend
`/api/v1/system/mcp-routing` endpoint and embed a single-shot escalation
hint directly in the response payload. This removes the need for the LLM
agent to chain a second tool call to formulate "would you like me to route
you to team X?" - small models (gpt-4.1-mini) drop those second calls
unreliably, so the data must arrive in the first tool's response.

Lookups are cached per tool name for 5 minutes (routing rarely changes).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx

CACHE_TTL_SECONDS = 300.0

_cache: dict[str, tuple[float, Optional[dict[str, Any]]]] = {}
_cache_lock = asyncio.Lock()

logger = logging.getLogger(__name__)


async def _fetch_routing(
    tool_name: str,
    *,
    api_url: str,
    api_key: str,
    timeout: float = 5.0,
) -> Optional[dict[str, Any]]:
    now = time.monotonic()

    async with _cache_lock:
        entry = _cache.get(tool_name)
        if entry is not None and entry[0] > now:
            return entry[1]

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        ) as client:
            resp = await client.get(
                f"{api_url.rstrip('/')}/api/v1/system/mcp-routing",
                params={"tool_name": tool_name},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        logger.warning("Routing lookup failed for tool=%s: %s", tool_name, e)
        async with _cache_lock:
            _cache[tool_name] = (now + 30.0, None)
        return None

    primary = body.get("primary")
    alternatives = [e for e in (body.get("entries") or []) if e != primary][1:] if primary else []

    if primary is None:
        result = None
    else:
        team_name = primary.get("team_name") or primary.get("team_code")
        result = {
            "team": primary.get("team_code"),
            "team_name": team_name,
            "agent": primary.get("agent_code"),
            "agent_display_name": primary.get("agent_name"),
            "tier": primary.get("tier"),
            "message": f"We don't have that information available. Would you like me to route you to our {team_name} team?",
            "alternatives": [
                {
                    "team": e.get("team_code"),
                    "team_name": e.get("team_name"),
                    "agent": e.get("agent_code"),
                    "tier": e.get("tier"),
                }
                for e in alternatives
            ],
        }

    async with _cache_lock:
        _cache[tool_name] = (now + CACHE_TTL_SECONDS, result)
    return result


def _is_empty_response(data: Any) -> bool:
    """Detect empty list / not-found shapes returned by CRM tools.

    Treat as empty:
      - {"data": []} (list endpoints)
      - {"data": null}, {"data": {}}
      - {"items": []} (alternate list shape)
      - bare empty list `[]`
      - {"detail": "...not found..."} from a 404 passthrough
      - {"error": "..."} that is not an ACCESS_DENIED (those are handled separately)

    Caller must not invoke this for ACCESS_DENIED payloads.
    """
    if isinstance(data, list):
        return len(data) == 0
    if not isinstance(data, dict):
        return False

    if data.get("error") == "ACCESS_DENIED":
        return False

    if "data" in data:
        d = data["data"]
        if d is None:
            return True
        if isinstance(d, list) and len(d) == 0:
            return True
        if isinstance(d, dict) and len(d) == 0:
            return True

    if "items" in data and isinstance(data["items"], list) and len(data["items"]) == 0:
        return True

    detail = str(data.get("detail") or data.get("message") or "").lower()
    if "not found" in detail or "no records" in detail or "no results" in detail:
        return True

    if "error" in data and not any(k in data for k in ("data", "items")):
        # Generic error payload (non-access) - treat as empty for escalation purposes.
        return True

    return False


async def attach_suggested_escalation(
    tool_name: str,
    sanitized_json: str,
    *,
    api_url: str,
    api_key: str,
) -> str:
    """If `sanitized_json` is an empty/not-found shape, attach `suggested_escalation`.

    Returns the (possibly augmented) JSON string. Idempotent: if the payload
    already has `suggested_escalation` or is not empty, returns the input
    unchanged.
    """
    try:
        data = json.loads(sanitized_json)
    except (TypeError, ValueError):
        return sanitized_json

    if isinstance(data, dict) and "suggested_escalation" in data:
        return sanitized_json

    if not _is_empty_response(data):
        return sanitized_json

    hint = await _fetch_routing(tool_name, api_url=api_url, api_key=api_key)
    if hint is None:
        return sanitized_json

    if isinstance(data, list):
        data = {"data": data, "suggested_escalation": hint}
    else:
        data["suggested_escalation"] = hint

    return json.dumps(data)
