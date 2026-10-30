"""The MCP server's bearer token, set from Settings > Integrations (MCP-TOKEN-UI).

Plan: documentation/plans/security/PLAN-mcp-token-ui-30oct.md.

The token used to be the `MCP_AUTH_TOKEN` env value on the MCP server, the backend and the
workers. It now lives on the `system_settings` singleton as `encrypt_secret` ciphertext:

- ``current_token`` is what this process sends to the MCP server (`MCPRuntimeClient`). It is
  cached for ``CACHE_TTL_SECONDS`` so a chatbot turn does not read the row per tool call.
- ``mcp_answer`` is what the MCP server is told (`GET /api/v1/system/mcp-auth`): SHA-256
  digests of the valid tokens (current, plus the previous one while its rotation grace window
  is open) and the Enforce switch. Never a token.
- ``rotate`` makes a new random token current and keeps the old one valid for
  ``GRACE_HOURS``, so n8n can be re-pasted without an outage. The new value is returned once,
  to the screen, and never again.

No token (the first deploy) means the backend sends no header and the MCP server lets a
headerless call through until Enforce is switched on. There is no env fallback: one source.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import SystemSetting
from app.utils.field_encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

AUDIT_EVENT = "MCP_AUTH_TOKEN"
GRACE_HOURS = 24
CACHE_TTL_SECONDS = 5.0
# After a rotate this process keeps sending the previous token (or none, after a first
# generate) for this long. The MCP server re-fetches on an unknown bearer at most every
# 5 s (`sorento_crm_mcp/auth.py` MISS_REFRESH_SECONDS); a new token sent sooner can meet a
# list fetched just before the rotate and be refused (review S1).
SEND_NEW_AFTER_SECONDS = 10.0
TOKEN_BYTES = 32  # 43 url-safe characters, over the 32-character floor SEC-MCP-AUTH set


class RevokeTooSoon(ValueError):
    """Revoking inside SEND_NEW_AFTER_SECONDS of a rotate would leave this process nothing to
    send: the new token is not sent yet and the previous one would be gone (review nit 3)."""


class EnforceWithoutToken(ValueError):
    """Enforce cannot be switched on without a readable token: it would refuse every caller."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decrypt(ciphertext: Optional[str]) -> tuple[Optional[str], bool]:
    """(plain or None, unreadable)."""
    if not ciphertext:
        return None, False
    try:
        return decrypt_secret(ciphertext) or None, False
    except ValueError:
        logger.warning("mcp_auth_token: a stored token does not decrypt (key changed?); treated as unset")
        return None, True


def _row(db: Session) -> Optional[SystemSetting]:
    return db.query(SystemSetting).first()


def _previous_live(row: SystemSetting, now: datetime) -> bool:
    expires = _aware(row.mcp_auth_previous_expires_at)
    return bool(row.mcp_auth_previous_token_ciphertext) and expires is not None and expires > now


# (generation, read at, token), swapped whole; `clear_cache` bumps the generation so a read
# that started before a save never writes its older value back (same shape as
# `runtime_settings`).
_cache: tuple[int, float, Optional[str]] = (0, float("-inf"), None)
_cache_lock = threading.Lock()


def clear_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = (_cache[0] + 1, float("-inf"), None)


def _token_to_send(row: Optional[SystemSetting]) -> Optional[str]:
    if row is None:
        return None
    rotated = _aware(row.mcp_auth_token_rotated_at)
    if rotated is not None and (_now() - rotated).total_seconds() < SEND_NEW_AFTER_SECONDS:
        # Still inside the window the MCP server may not have seen the new token in.
        if not row.mcp_auth_previous_token_ciphertext:
            return None
        return _decrypt(row.mcp_auth_previous_token_ciphertext)[0]
    return _decrypt(row.mcp_auth_token_ciphertext)[0]


def current_token(db: Optional[Session] = None) -> Optional[str]:
    """The token this process sends to the MCP server, or None (send no header)."""
    if db is not None:
        return _token_to_send(_row(db))
    global _cache
    generation, at, cached = _cache
    now = time.monotonic()
    if now - at < CACHE_TTL_SECONDS:
        return cached
    try:
        session = SessionLocal()
        try:
            token = _token_to_send(_row(session))
        finally:
            session.close()
    except Exception:  # noqa: BLE001 - keep the last value rather than drop the header
        logger.exception("mcp_auth_token: could not read system_settings")
        return cached
    with _cache_lock:
        if _cache[0] == generation:
            _cache = (generation, now, token)
    return token


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mcp_answer(db: Session) -> dict[str, Any]:
    """What the MCP server needs: the Enforce switch and the digests of the valid tokens."""
    row = _row(db)
    if row is None:
        return {"enforce": False, "token_sha256": []}
    now = _now()
    tokens = [_decrypt(row.mcp_auth_token_ciphertext)[0]]
    if _previous_live(row, now):
        tokens.append(_decrypt(row.mcp_auth_previous_token_ciphertext)[0])
    return {
        "enforce": bool(row.mcp_auth_enforce),
        "token_sha256": [_digest(t) for t in tokens if t],
    }


def _mask(value: Optional[str]) -> Optional[str]:
    return f"****{value[-4:]}" if value else None


def describe(db: Session) -> dict[str, Any]:
    """The screen's view: masked, never the token."""
    row = _row(db)
    token, unreadable = _decrypt(row.mcp_auth_token_ciphertext if row else None)
    now = _now()
    previous_until = (
        _aware(row.mcp_auth_previous_expires_at) if row is not None and _previous_live(row, now) else None
    )
    return {
        "configured": bool(row is not None and row.mcp_auth_token_ciphertext),
        "masked": _mask(token),
        "unreadable": unreadable,
        "enforce": bool(row.mcp_auth_enforce) if row is not None else False,
        "rotated_at": _aware(row.mcp_auth_token_rotated_at).isoformat()
        if row is not None and row.mcp_auth_token_rotated_at
        else None,
        "previous_valid_until": previous_until.isoformat() if previous_until else None,
        "grace_hours": GRACE_HOURS,
    }


def _locked_row(db: Session) -> tuple[SystemSetting, tuple[str, str]]:
    row = db.query(SystemSetting).with_for_update().first()
    created = row is None
    if created:
        row = SystemSetting(id=str(uuid.uuid4()))
    # This action's audit is the one MCP_AUTH_TOKEN row written below; the generic listener
    # would add a second one for the same flush (an INSERT row, when the singleton is created).
    skip = ("system_settings", str(row.id))
    db.info.setdefault("skip_audit_for", []).append(skip)
    if created:
        db.add(row)
        db.flush()
    return row, skip


def _release(db: Session, skip: tuple[str, str]) -> None:
    skips = db.info.get("skip_audit_for") or []
    if skip in skips:
        skips.remove(skip)


def _finish(db: Session, row: SystemSetting, skip: tuple[str, str], action: str, actor_user_id: Optional[str]) -> None:
    from app.services.audit_service import log_audit

    try:
        # The action name only: no token, no ciphertext, no digest.
        log_audit(
            db, "system_settings", str(row.id), "UPDATE",
            event=AUDIT_EVENT,
            new_values={"action": action, "enforce": bool(row.mcp_auth_enforce)},
            user_id=actor_user_id,
        )
        db.commit()
    finally:
        _release(db, skip)
    clear_cache()


def rotate(db: Session, actor_user_id: Optional[str]) -> str:
    """Make a new random token current; the old one stays valid for ``GRACE_HOURS``.
    Returns the new token, the only time it leaves the server."""
    row, skip = _locked_row(db)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    first = not row.mcp_auth_token_ciphertext
    if first:
        row.mcp_auth_previous_token_ciphertext = None
        row.mcp_auth_previous_expires_at = None
    else:
        row.mcp_auth_previous_token_ciphertext = row.mcp_auth_token_ciphertext
        row.mcp_auth_previous_expires_at = now + timedelta(hours=GRACE_HOURS)
    row.mcp_auth_token_ciphertext = encrypt_secret(token)
    row.mcp_auth_token_rotated_at = now
    _finish(db, row, skip, "generated" if first else "rotated", actor_user_id)
    return token


def set_enforce(db: Session, enforce: bool, actor_user_id: Optional[str]) -> None:
    row, skip = _locked_row(db)
    # A token that no longer decrypts counts as none: the backend could not send it, so Enforce
    # would refuse every caller (review S2).
    no_token = enforce and _decrypt(row.mcp_auth_token_ciphertext)[0] is None
    if no_token or bool(row.mcp_auth_enforce) == enforce:
        db.rollback()
        _release(db, skip)
        if no_token:
            raise EnforceWithoutToken("Generate or rotate the token before switching Enforce on.")
        return
    row.mcp_auth_enforce = enforce
    _finish(db, row, skip, "enforce_on" if enforce else "enforce_off", actor_user_id)


def revoke_previous(db: Session, actor_user_id: Optional[str]) -> None:
    """End the previous token's grace window now."""
    row, skip = _locked_row(db)
    rotated = _aware(row.mcp_auth_token_rotated_at)
    if rotated is not None and (_now() - rotated).total_seconds() < SEND_NEW_AFTER_SECONDS:
        db.rollback()
        _release(db, skip)
        raise RevokeTooSoon("The new token is still being picked up; try again in a few seconds.")
    row.mcp_auth_previous_token_ciphertext = None
    row.mcp_auth_previous_expires_at = None
    _finish(db, row, skip, "previous_revoked", actor_user_id)
