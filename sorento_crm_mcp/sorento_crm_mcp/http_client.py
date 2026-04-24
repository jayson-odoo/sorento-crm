"""HTTP client for CRM API calls."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping, MutableMapping

import httpx

from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)


class CRMClient:
    """Thin async client with X-API-Key and response size guard."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.crm_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-API-Key": settings.external_api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            # Avoid stale keep-alive sockets causing first-request read timeouts.
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=0),
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
        return await self.request("GET", path, path_params=path_params, query=query)

    async def post(
        self,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        query: MutableMapping[str, Any] | None = None,
        body: Any = None,
    ) -> str:
        """Perform POST; return JSON text or error message for the model."""
        return await self.request("POST", path, path_params=path_params, query=query, body=body)

    async def request(
        self,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, Any] | None = None,
        query: MutableMapping[str, Any] | None = None,
        body: Any = None,
    ) -> str:
        """Perform HTTP request; return JSON text or error message for the model."""
        rendered = path
        if path_params:
            for k, v in path_params.items():
                rendered = rendered.replace("{" + k + "}", str(v))
        params = {k: v for k, v in (query or {}).items() if v is not None}
        method_upper = method.upper()
        started = time.perf_counter()
        logger.info(
            "CRM request start: %s %s params=%s timeout=%.1fs",
            method_upper,
            rendered,
            params,
            float(self._settings.request_timeout_seconds),
        )
        try:
            r = await self._client.request(method_upper, rendered, params=params, json=body)
        except httpx.RequestError as e:
            err_type = type(e).__name__
            detail = str(e) or repr(e)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "CRM request failed: %s %s params=%s elapsed_ms=%.1f — %s: %s",
                method_upper,
                rendered,
                params,
                elapsed_ms,
                err_type,
                detail,
            )
            return json.dumps(
                {
                    "error": "request_failed",
                    "error_type": err_type,
                    "detail": detail,
                    "path": rendered,
                    "method": method_upper,
                }
            )

        body = r.content
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "CRM request done: %s %s status=%s elapsed_ms=%.1f bytes=%s",
            method_upper,
            rendered,
            r.status_code,
            elapsed_ms,
            len(body),
        )
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
                "CRM %s %s -> %s (first 200 chars: %s)",
                method.upper(),
                rendered,
                r.status_code,
                text[:200].replace("\n", " "),
            )

        return text
