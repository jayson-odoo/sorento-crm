"""User-guide tools for the MCP server.

Wraps the Outline API (https://doc.foundryx.my) so an n8n / WhatsApp agent can
answer "how do I…?" questions by searching and reading the user guides we
publish at the **Sorento CRM** collection.

Two tools are registered:

- ``user_guides_search`` — full-text search over the collection. Returns the
  top matches (title, doc id, snippet).
- ``user_guides_read`` — fetch the full markdown body of a single guide by
  doc id (UUID) or url-id (e.g. ``portal-overview-AbCd``).

Tools are read-only and unauthenticated from the agent's perspective — the
MCP server holds the Outline API token. They're intentionally kept simple so
a plain JSON contract works for any LLM caller.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 25
_BODY_PREVIEW_CHARS = 240


async def _outline_post(
    settings: Settings, path: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if not settings.outline_api_token:
        raise RuntimeError(
            "OUTLINE_API_TOKEN is not configured on the MCP server. "
            "Set it in sorento_crm_mcp/.env to enable user-guide tools."
        )
    url = f"{settings.outline_base_url.rstrip('/')}/api/{path}"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        r = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.outline_api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Outline {path} -> {r.status_code} {r.text}")
        return r.json()


def _short_preview(text: str | None) -> str:
    if not text:
        return ""
    snippet = text.strip().replace("\n", " ")
    if len(snippet) <= _BODY_PREVIEW_CHARS:
        return snippet
    return snippet[: _BODY_PREVIEW_CHARS - 1] + "…"


def _build_doc_url(settings: Settings, url: str | None) -> str | None:
    if not url:
        return None
    base = settings.outline_base_url.rstrip("/")
    if url.startswith("http"):
        return url
    return f"{base}{url}"


async def search_user_guides_impl(
    settings: Settings, query: str, limit: int | None = None
) -> str:
    if not query or not query.strip():
        return json.dumps(
            {"error": "Query is required.", "code": "MISSING_QUERY"}
        )
    bounded_limit = max(1, min(int(limit or _DEFAULT_LIMIT), _MAX_LIMIT))
    try:
        data = await _outline_post(
            settings,
            "documents.search",
            {
                "query": query.strip(),
                "collectionId": settings.outline_collection_id,
                "limit": bounded_limit,
            },
        )
    except Exception as e:
        logger.warning("user_guides_search failed: %s", e)
        return json.dumps({"error": str(e), "code": "OUTLINE_ERROR"})

    rows = []
    for hit in data.get("data", []):
        doc = hit.get("document") or {}
        rows.append(
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "url": _build_doc_url(settings, doc.get("url")),
                "url_id": doc.get("urlId"),
                "ranking": hit.get("ranking"),
                "snippet": _short_preview(hit.get("context") or doc.get("text", "")),
            }
        )
    return json.dumps(
        {
            "query": query.strip(),
            "limit": bounded_limit,
            "count": len(rows),
            "results": rows,
        }
    )


async def read_user_guide_impl(settings: Settings, identifier: str) -> str:
    if not identifier or not identifier.strip():
        return json.dumps(
            {"error": "Identifier (doc id or url-id) is required.", "code": "MISSING_ID"}
        )
    payload: dict[str, Any] = {}
    ident = identifier.strip()
    # Heuristic: UUIDs use canonical 8-4-4-4-12 format. Outline url-ids are
    # short alphanumeric (e.g. 'portal-overview-A1bC').
    if len(ident) == 36 and ident.count("-") == 4:
        payload["id"] = ident
    else:
        payload["id"] = ident  # Outline accepts both forms on `id` parameter.
    try:
        data = await _outline_post(settings, "documents.info", payload)
    except Exception as e:
        logger.warning("user_guides_read failed: %s", e)
        return json.dumps({"error": str(e), "code": "OUTLINE_ERROR"})
    doc = data.get("data") or {}
    return json.dumps(
        {
            "id": doc.get("id"),
            "title": doc.get("title"),
            "url": _build_doc_url(settings, doc.get("url")),
            "url_id": doc.get("urlId"),
            "updated_at": doc.get("updatedAt"),
            "text": doc.get("text", ""),
        }
    )


def register_user_guide_tools(mcp: Any, settings: Settings) -> None:
    """Register the two user-guide tools on the given FastMCP instance."""

    async def user_guides_search(query: str, limit: int = _DEFAULT_LIMIT) -> str:
        """Search Sorento CRM user guides by free-text query.

        Use this whenever a user asks "how do I…?" / "how to…" questions about
        the CRM. Returns up to ``limit`` matching guides with their title,
        canonical URL on doc.foundryx.my, and a short snippet. Pass the
        returned ``id`` (or ``url_id``) to ``user_guides_read`` to fetch the
        full body before answering the user.
        """

        return await search_user_guides_impl(settings, query=query, limit=limit)

    async def user_guides_read(identifier: str) -> str:
        """Read the full markdown body of a Sorento CRM user guide.

        Accepts either the Outline document UUID (e.g.
        ``b8df43f6-9082-4625-a07b-393a9db18636``) or the human url-id (e.g.
        ``portal-overview-aBcDe``) returned from ``user_guides_search``.
        """

        return await read_user_guide_impl(settings, identifier=identifier)

    mcp.add_tool(
        user_guides_search,
        name="user_guides_search",
        description=(
            "Search Sorento CRM end-user how-to guides (Outline collection). "
            "Use first whenever the user asks how to perform an action — "
            "uploading a packing list, submitting a stock inquiry, approving a "
            "purchase request, etc."
        ),
    )
    mcp.add_tool(
        user_guides_read,
        name="user_guides_read",
        description=(
            "Read the full markdown body of a Sorento CRM user guide. "
            "Pass an id from user_guides_search; returns the markdown so you "
            "can answer the user with concrete steps and exact UI labels."
        ),
    )
