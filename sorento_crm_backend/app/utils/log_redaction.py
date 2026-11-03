"""Strip customer link tokens from URLs before they reach a log line (SIGN-TOKEN-LOG-REDACT).

A counter-sign, ticket-draft, supplier-request, idea or file-share link is a bearer credential:
whoever holds the URL opens the page. The request log, uvicorn's access log and the error
handlers all wrote those URLs verbatim, so log access was link access. Every such token is
replaced with `[redacted:<8 hex of sha256>]`: not reversible, but stable, so two log lines for
the same link can still be correlated.

Plan: documentation/plans/security/PLAN-sign-token-log-redact-03nov.md.
"""
from __future__ import annotations

import hashlib
import logging
import re

# Public routes whose next path segment is the link token (app/api/v1/public/__init__.py).
_PATH_TOKEN_PREFIXES = (
    "/api/v1/public/quotation-sign/",
    "/api/v1/public/ticket-drafts/",
    "/api/v1/public/supplier-request/",
    "/api/v1/public/portal/ideas/",
    "/api/v1/public/file-links/",
)

_PATH_TOKEN_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in _PATH_TOKEN_PREFIXES) + r")([^/?#\s\"']+)"
)
# The customer-facing page URLs the backend builds and returns (an `/external` response body
# lands in api_call_logs): sign page, idea, ticket draft, supplier request, onboarding, file link.
# Anchored to the start of a path, a host, or a quote, so a staff route that merely contains
# "onboarding" is not touched.
_PAGE_TOKEN_RE = re.compile(
    r"((?:^|(?<=[\s\"'=(])|https?://[^/\s\"'?#]+)"
    r"(?:/c/[^/\s\"'?#]+)?"
    r"/(?:quotation-sign|portal/ideas|portal/ticket-draft|supplier-request|onboarding|f)/)"
    r"([^/?#\s\"']+)"
)
# Any query parameter whose name ends in "token" (token, access_token, ...): the view,
# approval, print, portal token-info and unsubscribe links all carry `?token=`.
_QUERY_TOKEN_RE = re.compile(r"([?&][A-Za-z0-9_]*token=)([^&#\s\"']+)", re.IGNORECASE)


def _marker(secret: str) -> str:
    return "[redacted:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8] + "]"


def redact_url(text: str) -> str:
    """`text` (a path, path + query, or full URL) with every link token replaced."""
    if not text:
        return text
    text = _PATH_TOKEN_RE.sub(lambda m: m.group(1) + _marker(m.group(2)), text)
    text = _PAGE_TOKEN_RE.sub(
        lambda m: m.group(0) if m.group(2).startswith("[redacted:") else m.group(1) + _marker(m.group(2)),
        text,
    )
    return _QUERY_TOKEN_RE.sub(lambda m: m.group(1) + _marker(m.group(2)), text)


class RedactUrlTokensFilter(logging.Filter):
    """Rewrites uvicorn's access record (`'%s - "%s %s HTTP/%s" %d'`, path with query as the
    third argument) so the access log carries no link token. Never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and args:
            record.args = tuple(redact_url(a) if isinstance(a, str) else a for a in args)
        elif isinstance(record.msg, str):
            record.msg = redact_url(record.msg)
        return True


def install_access_log_filter() -> None:
    """Idempotent: attach the filter to the `uvicorn.access` logger (dev uvicorn and the gunicorn
    UvicornWorker both log requests through it), and keep httpx's per-request INFO line (the full
    outbound URL, e.g. the portal idea proxy's `/public/ideas/<token>`) out of the log."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactUrlTokensFilter) for f in access.filters):
        access.addFilter(RedactUrlTokensFilter())
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
