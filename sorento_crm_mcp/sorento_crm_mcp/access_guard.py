"""MCP access guard: backend round-trip + 60 s TTL cache.

Used by `_compile_tool` to validate (tool_name, contact_id, space_id) before
forwarding the underlying CRM request. Failed checks return a verbatim
JSON deny payload that the LLM caller surfaces to the end user.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx

CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    decision: str
    agent_name: Optional[str]


_cache: dict[tuple[str, str, str], tuple[float, AccessDecision]] = {}
_cache_lock = asyncio.Lock()


async def check_access(
    tool_name: str,
    contact_id: str,
    space_id: str,
    *,
    api_url: str,
    api_key: str,
    timeout: float = 5.0,
) -> AccessDecision:
    """Look up access decision for `(tool, contact, space)` against backend.

    Cache hits (within `CACHE_TTL_SECONDS`) skip the network call.
    """
    key = (tool_name, contact_id, space_id)
    now = time.monotonic()

    async with _cache_lock:
        entry = _cache.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    ) as client:
        resp = await client.post(
            f"{api_url.rstrip('/')}/api/v1/system/mcp-access/check",
            json={"tool_name": tool_name, "contact_id": contact_id, "space_id": space_id},
        )
        resp.raise_for_status()
        body = resp.json()
    decision = AccessDecision(
        allowed=bool(body.get("allowed")),
        decision=str(body.get("decision", "deny_unknown_tool")),
        agent_name=body.get("agent_name"),
    )

    async with _cache_lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, decision)

    return decision


def deny_payload(decision: AccessDecision) -> str:
    """Build the verbatim JSON deny payload for a non-allowed decision."""
    if decision.decision == "deny_no_access" or decision.decision == "deny_unknown_contact":
        agent = decision.agent_name or "this agent"
        body = {
            "error": "ACCESS_DENIED",
            "code": "CONTACT_NOT_AUTHORIZED",
            "message": f"you are not allowed to access this function: {agent}",
            "agent_name": decision.agent_name,
        }
    elif decision.decision == "deny_tool_unlinked":
        body = {
            "error": "ACCESS_DENIED",
            "code": "TOOL_NOT_LINKED",
            "message": "the required tools are not linked to any supported agents in the system",
            "agent_name": None,
        }
    else:  # deny_unknown_tool
        body = {
            "error": "ACCESS_DENIED",
            "code": "UNKNOWN_TOOL",
            "message": "the required tools are not linked to any supported agents in the system",
            "agent_name": None,
        }
    return json.dumps(body)
