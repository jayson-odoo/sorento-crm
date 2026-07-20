"""Request telemetry for `/api/v1/external/*` — total coverage by construction.

Today only 3 of ~30 external endpoints log anything, because logging is opt-in
per endpoint. Middleware inverts that: a new external route is logged the day it
is added, with no per-endpoint code and no way to forget.

Pure ASGI, not BaseHTTPMiddleware, for the same reason as
`idempotency_middleware`: reading the request body in BaseHTTPMiddleware consumes
it and the downstream handler receives an empty body. Here the body is buffered
and replayed, and the response is captured as it streams past.

**Synchronous write, deliberately.** A buffered/async writer drops exactly the
records you need at the moment the process dies — i.e. the incident you are
trying to explain. The cost is per-request latency (measured, see the test
report). The write failing must never affect the response.
"""
from __future__ import annotations

import logging
import time

from app.config import settings

logger = logging.getLogger(__name__)

# Strictly scoped. Widening this to all of /api/v1 would log the health
# dashboard's own polling and the log page's own reads back into the table —
# a feedback loop that grows without bound and drowns the real traffic.
_LOGGED_PREFIX = "/api/v1/external"

# Bodies above this are not buffered at all (file uploads). The row is still
# written; the payload records the reason instead of megabytes of bytes.
_MAX_BUFFER_BYTES = 262144
_OVERSIZE_MARKER = "[body too large to log]"


def _decode_headers(raw) -> dict:
    out = {}
    for key, value in raw or []:
        try:
            out[key.decode("latin-1")] = value.decode("latin-1")
        except Exception:  # noqa: BLE001
            continue
    return out


class ApiCallLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "") or ""
        if not path.startswith(_LOGGED_PREFIX):
            return await self.app(scope, receive, send)
        if not getattr(settings, "api_call_log_enabled", True):
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET")
        headers = _decode_headers(scope.get("headers"))

        # ---- buffer the request body so it can be logged AND replayed ----
        body = b""
        messages: list[dict] = []
        oversize = False
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if not oversize:
                body += chunk
                if len(body) > _MAX_BUFFER_BYTES:
                    oversize = True
                    body = b""
            more = message.get("more_body", False)
            messages.append(message)

        replay = iter(messages)

        async def receive_replay():
            try:
                return next(replay)
            except StopIteration:
                # Downstream may poll past the buffered messages.
                return {"type": "http.request", "body": b"", "more_body": False}

        status_code: int | None = None
        response_body = b""
        response_oversize = False

        async def send_capture(message):
            nonlocal status_code, response_body, response_oversize
            if message["type"] == "http.response.start":
                status_code = message.get("status")
            elif message["type"] == "http.response.body":
                if not response_oversize:
                    response_body += message.get("body", b"")
                    if len(response_body) > _MAX_BUFFER_BYTES:
                        response_oversize = True
                        response_body = b""
            await send(message)

        started = time.perf_counter()
        error_message = None
        try:
            await self.app(scope, receive_replay, send_capture)
        except Exception as exc:  # noqa: BLE001
            # Log the failure, then re-raise: the row is evidence about the
            # request, it does not get to swallow it.
            error_message = f"{type(exc).__name__}: {exc}"
            self._write(
                path=path,
                method=method,
                headers=headers,
                status_code=None,
                request_body=_OVERSIZE_MARKER if oversize else body,
                response_body=None,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error_message=error_message,
            )
            raise

        self._write(
            path=path,
            method=method,
            headers=headers,
            status_code=status_code,
            request_body=_OVERSIZE_MARKER if oversize else body,
            response_body=_OVERSIZE_MARKER if response_oversize else response_body,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=None,
        )

    def _write(
        self,
        *,
        path,
        method,
        headers,
        status_code,
        request_body,
        response_body,
        latency_ms,
        error_message,
    ) -> None:
        """Persist one row. Wrapped so no telemetry failure reaches the caller."""
        try:
            from app.database import SessionLocal
            from app.services.api_call_log_service import (
                classify_outcome,
                resolve_correlation_id,
                resolve_source,
                resolve_tool_name,
                sanitize_body,
                write_call_log,
            )

            db = SessionLocal()
            try:
                write_call_log(
                    db,
                    endpoint=path[:512],
                    method=method[:10],
                    source=resolve_source(headers),
                    tool_name=resolve_tool_name(headers),
                    actor=None,
                    status_code=status_code,
                    outcome=classify_outcome(status_code),
                    latency_ms=latency_ms,
                    correlation_id=resolve_correlation_id(headers),
                    request_payload=sanitize_body(request_body),
                    response_payload=sanitize_body(response_body),
                    error_message=error_message,
                )
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.warning("api_call_log middleware write failed", exc_info=True)
