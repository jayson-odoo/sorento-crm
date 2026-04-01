"""HTTP client for CRM GET calls (read-only)."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping, MutableMapping

import httpx

from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)


class CRMClient:
    """Thin async GET client with X-API-Key and response size guard."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.crm_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-API-Key": settings.external_api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        query: MutableMapping[str, Any] | None = None,
    ) -> str:
        """Perform GET; return JSON text or error message for the model."""
        rendered = path
        if path_params:
            for k, v in path_params.items():
                rendered = rendered.replace("{" + k + "}", str(v))
        params = {k: v for k, v in (query or {}).items() if v is not None}
        try:
            r = await self._client.get(rendered, params=params)
        except httpx.RequestError as e:
            logger.warning("CRM request failed: %s %s — %s", "GET", rendered, e)
            return json.dumps({"error": "request_failed", "detail": str(e), "path": rendered})

        body = r.content
        if len(body) > self._settings.max_response_bytes:
            return json.dumps(
                {
                    "error": "response_too_large",
                    "path": rendered,
                    "max_bytes": self._settings.max_response_bytes,
                }
            )

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return json.dumps({"error": "invalid_utf8", "path": rendered, "status_code": r.status_code})

        if r.status_code >= 400:
            logger.info(
                "CRM GET %s -> %s (first 200 chars: %s)",
                rendered,
                r.status_code,
                text[:200].replace("\n", " "),
            )

        return text
