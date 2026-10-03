"""DEV-LOGIN-BYPASS: passwordless sign-in for LOCAL test copies only.

Plan: documentation/plans/identity/PLAN-dev-login-bypass-03oct.md.

Every guard must hold or the dev-login routes answer a plain 404 (fail closed):

1. ``DEV_AUTO_LOGIN`` is on (default off).
2. ``ENVIRONMENT`` is in ``ALLOWED_ENVIRONMENTS``. Anything else, an empty value included,
   refuses; and the process refuses to START with the flag on outside that list.
3. The request ``Host`` hostname is ``localhost``, ``*.localhost`` or ``127.0.0.1``.
4. The TCP peer is loopback. The frontend's server calls the backend on localhost; a deployed
   backend sits behind Docker / a reverse proxy and never sees a loopback peer. Uvicorn only
   rewrites the peer from ``X-Forwarded-For`` when the real peer is itself 127.0.0.1, so the
   header cannot fake this from outside.
5. The email is in ``DEV_AUTO_LOGIN_USERS`` and that user is ACTIVE and not trashed.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ALLOWED_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})


def environment_allowed(environment: Optional[str]) -> bool:
    return (environment or "").strip().lower() in ALLOWED_ENVIRONMENTS


def assert_safe_startup(*, enabled: bool, environment: Optional[str]) -> None:
    """Crash the process when the flag is on outside a dev environment; warn when active."""
    if not enabled:
        return
    if not environment_allowed(environment):
        raise RuntimeError(
            f"DEV_AUTO_LOGIN is on while ENVIRONMENT={environment!r}. Passwordless dev sign-in "
            f"is only allowed when ENVIRONMENT is one of {sorted(ALLOWED_ENVIRONMENTS)}. "
            "Refusing to start."
        )
    logger.warning(
        "!!! DEV_AUTO_LOGIN is ACTIVE (ENVIRONMENT=%s): passwordless sign-in is open to "
        "localhost requests for the DEV_AUTO_LOGIN_USERS allowlist. Never run this in production. !!!",
        environment,
    )


def is_local_host(host_header: Optional[str]) -> bool:
    """True for ``localhost``, ``*.localhost`` and ``127.0.0.1``, with an optional port."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        return False  # IPv6 literal: not on the allowlist
    name, sep, port = host.rpartition(":")
    if sep:
        if not port.isdigit():
            return False
        host = name
    if host in ("localhost", "127.0.0.1"):
        return True
    if host.endswith(".localhost"):
        label = host[: -len(".localhost")]
        return bool(label) and all(part and (part.replace("-", "").isalnum()) for part in label.split("."))
    return False


def is_loopback_peer(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def allowed_emails(raw: Optional[str]) -> list[str]:
    """The allowlist in order (first = default), lowercased, de-duplicated."""
    seen: list[str] = []
    for part in (raw or "").split(","):
        email = part.strip().lower()
        if email and email not in seen:
            seen.append(email)
    return seen


def request_allowed(*, enabled: bool, environment: Optional[str], host_header: Optional[str],
                    peer_ip: Optional[str]) -> bool:
    return (
        bool(enabled)
        and environment_allowed(environment)
        and is_local_host(host_header)
        and is_loopback_peer(peer_ip)
    )
