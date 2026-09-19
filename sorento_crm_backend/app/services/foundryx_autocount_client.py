"""Thin client for the FoundryX AutoCount pull gateway (PLAN-autocount-pull-review.md).

One small class, sync ``httpx.Client``, no retries, no caching. The key is read from
settings and sent ONLY as the ``X-API-Key`` header - never logged, never echoed in an
exception message. Every error becomes one ``FoundryxPullError(code, message, status)``:
``status`` is the HTTP status SORENTO answers the caller with (not necessarily FoundryX's
own status - see the mapping in ``_parse``), ``code`` is FoundryX's own stable code where
it can be trusted, else ``UNREACHABLE`` / ``NOT_CONFIGURED``.

``TRANSPORT`` is a module-level seam: production leaves it ``None`` (httpx then uses its
normal outbound transport); tests replace it with an ``httpx.MockTransport`` that serves
the committed fixtures, so nothing here ever needs a live FoundryX to be exercised.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import settings

#: Test seam. See module docstring.
TRANSPORT: Optional[httpx.BaseTransport] = None

_BUILD_TIMEOUT_SECONDS = 15
_STATUS_TIMEOUT_SECONDS = 15
_ROWS_TIMEOUT_SECONDS = 30

#: A runaway upstream (`totalPages` that keeps growing, or never settles) must not page
#: forever - `all_rows` refuses once it would exceed this many pages. Generous for any
#: real snapshot (the largest today, SRT products, is about 12 pages at 1000 rows each).
MAX_PAGES = 100

#: FoundryX statuses that mean "not FoundryX's fault, ours" - a bad/expired key or a
#: company code the key cannot see. Mapped to one stable code and a 502 (upstream
#: refused us) rather than passed through, so the FE never has to special-case FoundryX's
#: own auth vocabulary and the key's validity is never implied by the response.
_NOT_CONFIGURED_HTTP_STATUSES = (401, 403, 404)

_NOT_CONFIGURED_MESSAGE = "The AutoCount connection is not set up."


class FoundryxPullError(Exception):
    """One shape for every way a FoundryX call can fail."""

    def __init__(self, *, code: str, message: str, status: int):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class FoundryxAutocountClient:
    """Talks to the FoundryX AutoCount pull gateway for one request/task."""

    def __init__(self) -> None:
        base_url = (settings.foundryx_base_url or "").strip()
        api_key = (settings.foundryx_api_key or "").strip()
        if not base_url or not api_key:
            raise FoundryxPullError(
                code="NOT_CONFIGURED", message=_NOT_CONFIGURED_MESSAGE, status=503
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=timeout, transport=TRANSPORT)

    def _request(self, method: str, path: str, *, timeout: float, **kwargs: Any) -> dict:
        try:
            with self._client(timeout) as client:
                response = client.request(method, path, headers=self._headers(), **kwargs)
        except httpx.TimeoutException as exc:
            raise FoundryxPullError(
                code="UNREACHABLE", message="Could not reach AutoCount (timed out).", status=502
            ) from exc
        except httpx.HTTPError as exc:
            raise FoundryxPullError(
                code="UNREACHABLE", message="Could not reach AutoCount.", status=502
            ) from exc
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict:
        if response.status_code < 400:
            try:
                body = response.json()
            except ValueError:
                return {}
            if not isinstance(body, dict):
                # FoundryX answered 2xx with something that is not a JSON object (a bare
                # array, a string, ...) - every caller here treats the body as a dict, so
                # this is not a shape we can trust rather than a shape to crash on.
                raise FoundryxPullError(
                    code="UNREACHABLE",
                    message="AutoCount returned an unexpected response.",
                    status=502,
                )
            return body

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code in _NOT_CONFIGURED_HTTP_STATUSES:
            raise FoundryxPullError(
                code="NOT_CONFIGURED", message=_NOT_CONFIGURED_MESSAGE, status=502
            )

        code = body.get("code") or "UNKNOWN"
        message = body.get("message") or "AutoCount returned an error."
        raise FoundryxPullError(code=code, message=message, status=response.status_code)

    # ------------------------------------------------------------- calls

    def build(self, company_code: str, entity: str) -> dict:
        """``POST /api/v1/autocount/snapshots`` - starts (or reuses, on FoundryX's own
        side) a snapshot build."""
        return self._request(
            "POST",
            "/api/v1/autocount/snapshots",
            timeout=_BUILD_TIMEOUT_SECONDS,
            json={"companyCode": company_code, "entity": entity},
        )

    def status(self, snapshot_id: str) -> dict:
        """``GET /api/v1/autocount/snapshots/{id}`` - the header, whatever state the
        snapshot is currently in (building / ready / failed)."""
        return self._request(
            "GET",
            f"/api/v1/autocount/snapshots/{snapshot_id}",
            timeout=_STATUS_TIMEOUT_SECONDS,
        )

    def rows_page(self, snapshot_id: str, page: int) -> dict:
        """``GET /api/v1/autocount/snapshots/{id}/rows?page=`` - one page of rows."""
        return self._request(
            "GET",
            f"/api/v1/autocount/snapshots/{snapshot_id}/rows",
            timeout=_ROWS_TIMEOUT_SECONDS,
            params={"page": page},
        )

    def all_rows(self, snapshot_id: str) -> list[dict]:
        """Pages through every row of a ready snapshot, in order. Refuses past `MAX_PAGES`
        (module constant) - an upstream whose `totalPages` keeps growing (or never settles)
        must not be paged forever."""
        rows: list[dict] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            if page > MAX_PAGES:
                raise FoundryxPullError(
                    code="ROW_LIMIT",
                    message=f"AutoCount snapshot exceeds {MAX_PAGES} pages; pull again.",
                    status=502,
                )
            body = self.rows_page(snapshot_id, page)
            rows.extend(body.get("rows") or [])
            try:
                total_pages = int(body.get("totalPages") or 1)
            except (TypeError, ValueError):
                total_pages = 1
            page += 1
        return rows
