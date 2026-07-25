"""Per-integration rate limiting for external API callers (AC-AC-10).

Wraps the existing Redis fixed-window limiter, keyed by integration id so one
noisy caller cannot throttle the others -- ``/external`` has no limiting at all
today, so a single misbehaving workflow can saturate the API for everyone.

**Fail-open, and say so.** If the limiter backend is unreachable the request is
allowed and an alert is raised. Rate limiting here is abuse control, not
authorization: a dead limiter grants nobody access, because authentication is
DB-backed and still fully enforced. The worst case is an already-authenticated
caller going unthrottled for the duration of an outage. Fail-closed would trade
that for turning a Redis blip into a simultaneous ESB-sync and n8n outage --
a much worse failure. This matches the deliberate choice already made for
signup/login in ``app/services/rate_limit.py``.

The alert is what keeps that honest. A limiter that is quietly off looks
identical to one that is working.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.services import rate_limit

logger = logging.getLogger(__name__)

_BUCKET = "integration_api"
_WINDOW_SECONDS = 60

# Generous by design: this is an abuse ceiling, not a quota. The ESB pushing a
# masters batch and n8n servicing a conversation burst both sit well under it,
# so the limit only bites on genuinely pathological traffic. Tighten per
# integration via config_json when a real number is known.
DEFAULT_LIMIT_PER_MINUTE = 600


@dataclass
class RateLimitOutcome:
    allowed: bool
    limit: int
    retry_after_seconds: Optional[int] = None
    # True when the backend could not answer and the request was let through.
    degraded: bool = False


def limit_for(integration: Any) -> int:
    """Requests-per-minute ceiling for this integration.

    ``config_json.rate_limit_per_minute`` overrides the default; ``0`` disables
    limiting entirely, matching the underlying limiter's convention.

    config_json is operator-editable, so a nonsense value falls back to the
    default rather than propagating an exception onto the authentication path --
    a typo in a config field must not take an integration offline.
    """
    config = getattr(integration, "config_json", None) or {}
    raw = config.get("rate_limit_per_minute") if isinstance(config, dict) else None
    if raw is None:
        return DEFAULT_LIMIT_PER_MINUTE
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "integration.rate_limit_invalid integration=%s value=%r; using default",
            getattr(integration, "name", "?"),
            raw,
        )
        return DEFAULT_LIMIT_PER_MINUTE
    if value < 0:
        return DEFAULT_LIMIT_PER_MINUTE
    return value


def _alert_limiter_degraded(integration: Any, error: Exception) -> None:
    """Surface that the limiter is not actually limiting anything."""
    logger.error(
        "integration.rate_limiter_degraded integration=%s error=%s -- requests are "
        "being allowed unthrottled until the limiter backend recovers",
        getattr(integration, "name", "?"),
        error,
    )


def check_integration_rate_limit(integration: Any) -> RateLimitOutcome:
    """Register one request for ``integration`` and report whether it is allowed."""
    limit = limit_for(integration)
    if limit <= 0:
        return RateLimitOutcome(allowed=True, limit=limit)

    try:
        result = rate_limit.hit(
            _BUCKET,
            str(getattr(integration, "id", "")),
            limit=limit,
            window_seconds=_WINDOW_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - infra
        try:
            _alert_limiter_degraded(integration, exc)
        except Exception:
            # Observability must never become a new failure mode on the auth
            # path. If alerting is also down, the request still proceeds.
            logger.exception("integration.rate_limiter_alert_failed")
        return RateLimitOutcome(allowed=True, limit=limit, degraded=True)

    return RateLimitOutcome(
        allowed=bool(result.allowed),
        limit=limit,
        retry_after_seconds=getattr(result, "retry_after_seconds", None),
    )
