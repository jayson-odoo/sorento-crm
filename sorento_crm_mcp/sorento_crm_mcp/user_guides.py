"""User-guide tool for the MCP server.

Wraps the Outline API (https://doc.foundryx.my) so an n8n / WhatsApp agent (or
the in-app AI assistant) can answer "how do I…?" questions in a single call.

One tool is registered:

- ``user_guides_read`` - given a free-text query OR an Outline doc id / url-id,
  return the full markdown body of the most relevant guide. Internally this
  does ``documents.search`` against the Sorento CRM collection and fetches the
  top hit's body via ``documents.info``. If the input already looks like a
  UUID or url-id, it skips search and goes straight to fetch.

The standalone ``user_guides_search`` tool was removed: callers always wanted
the body, never the snippet list, and forcing a two-call flow (search → read)
just added latency and a chance for the LLM to pick a wrong id from snippets.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)

_BODY_PREVIEW_CHARS = 240
_SEARCH_TOP_K = 3

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Outline url-ids are bare alphanumeric tokens of length 10-15 (e.g.
# `6nHGiMmtcg`). Only treat the input as a url-id if it matches that exact
# shape - random hyphenated phrases like `how-do-i-upload-a-packing-list`
# previously matched and made us send junk ids to Outline.
_URL_ID_RE = re.compile(r"^[A-Za-z0-9]{10,15}$")


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


def _looks_like_id(s: str) -> bool:
    s = s.strip()
    if " " in s:
        return False
    if _UUID_RE.match(s):
        return True
    if any(ch in s for ch in "?!,.\n\t/-_"):
        return False
    return bool(_URL_ID_RE.match(s))


async def _fetch_doc_body(settings: Settings, identifier: str) -> dict[str, Any]:
    data = await _outline_post(settings, "documents.info", {"id": identifier.strip()})
    doc = data.get("data") or {}
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "url": _build_doc_url(settings, doc.get("url")),
        "url_id": doc.get("urlId"),
        "updated_at": doc.get("updatedAt"),
        "text": doc.get("text", ""),
    }


async def read_user_guide_impl(settings: Settings, query: str) -> str:
    """Resolve `query` to a single guide body.

    - If `query` looks like a UUID / url-id, fetch directly via documents.info.
    - Otherwise run documents.search (top 3) against the Sorento CRM
      collection, take the best-ranked hit, and fetch its body.
    """
    q = (query or "").strip()
    if not q:
        return json.dumps(
            {"error": "query is required.", "code": "MISSING_QUERY"}
        )

    if _looks_like_id(q):
        try:
            body = await _fetch_doc_body(settings, q)
            return json.dumps(body)
        except Exception as e:
            logger.warning("user_guides_read direct fetch failed for %r: %s", q, e)
            # Fall through to search - caller may have passed a slug-shaped
            # natural language phrase (e.g. 'upload-packing-list').
    try:
        search = await _outline_post(
            settings,
            "documents.search",
            {
                "query": q,
                "collectionId": settings.outline_collection_id,
                "limit": _SEARCH_TOP_K,
            },
        )
    except Exception as e:
        logger.warning("user_guides_read search failed for %r: %s", q, e)
        return json.dumps({"error": str(e), "code": "OUTLINE_ERROR"})

    hits = search.get("data") or []
    if not hits:
        return json.dumps(
            {
                "error": "No matching user guide.",
                "code": "NO_MATCH",
                "query": q,
            }
        )

    # Try each hit until one returns a body. Some hits (e.g. virtual
    # `__parent__` nodes from the sync script, or docs whose id was stripped
    # by an upstream proxy) may fail with a 400 from documents.info. Don't
    # let one bad hit poison an otherwise-valid result.
    body: dict[str, Any] | None = None
    matched_hit_index: int | None = None
    last_err: Exception | None = None
    for idx, hit in enumerate(hits):
        doc = (hit or {}).get("document") or {}
        candidate_id = (doc.get("id") or doc.get("urlId") or "").strip()
        if not candidate_id:
            continue
        try:
            body = await _fetch_doc_body(settings, candidate_id)
            matched_hit_index = idx
            break
        except Exception as e:
            last_err = e
            logger.warning(
                "user_guides_read body fetch failed for hit[%d] id=%r: %s",
                idx,
                candidate_id,
                e,
            )
    if body is None:
        return json.dumps(
            {
                "error": str(last_err) if last_err else "All hits returned no body.",
                "code": "OUTLINE_ERROR",
            }
        )

    body["matched_via"] = "search"
    body["matched_query"] = q
    body["alternative_titles"] = [
        {
            "id": (h.get("document") or {}).get("id"),
            "title": (h.get("document") or {}).get("title"),
            "snippet": _short_preview(h.get("context") or (h.get("document") or {}).get("text", "")),
        }
        for i, h in enumerate(hits)
        if i != matched_hit_index
    ]
    return json.dumps(body)


def register_user_guide_tools(mcp: Any, settings: Settings) -> None:
    """Register the single user-guide tool on the given FastMCP instance."""

    async def user_guides_read(query: str) -> str:
        """Read the most relevant Sorento CRM user guide for a question.

        Pass the user's natural-language how-to question as ``query`` (e.g.
        "How do I upload a packing list?"). The tool searches the Sorento CRM
        Outline collection and returns the top match's full markdown body in
        one round trip - no separate search call is needed.

        If the caller already has an Outline doc id (UUID) or url-id (e.g.
        ``portal-overview-aBcDe``), pass it as ``query`` and the tool fetches
        the body directly.
        """

        return await read_user_guide_impl(settings, query=query)

    mcp.add_tool(
        user_guides_read,
        name="user_guides_read",
        description=(
            "Read the Sorento CRM user guide that best matches a how-to "
            "question. Use whenever the user asks 'how do I…?', 'how to…?', "
            "'where do I find…?', 'what's the process for…?', 'steps to…?' "
            "about CRM features (uploading a packing list, submitting a stock "
            "inquiry, sending a purchase request for approval, OTP / portal "
            "access, approving via email link, etc.). Pass the user's "
            "question verbatim as `query`; the tool searches Outline and "
            "returns the full markdown body of the best match in one call. "
            "Quote the steps verbatim and preserve inline markdown links "
            "exactly when answering the user."
        ),
    )
