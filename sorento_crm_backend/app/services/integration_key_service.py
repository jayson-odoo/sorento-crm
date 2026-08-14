"""Lifecycle of integration API keys: issue, resolve, rotate, revoke.

The authentication path for every external caller runs through ``resolve``.

Two design points worth keeping in mind when changing this file:

**The grace window closes passively.** ``rotate_key`` stamps ``expires_at`` on
the superseded key and nothing else ever touches it -- ``resolve`` compares
against the clock on each request. There is deliberately no scheduled job:
``ENABLE_SCHEDULER`` is opt-in and defaults off, so a cron-driven expiry would
leave superseded keys valid indefinitely in any deployment where nobody set it.
A security control must not fail open because an unrelated env var is missing.

**Failure reasons are part of the contract.** ``resolve`` reports *why* it
refused. An operator whose ESB starts 401-ing at 3am needs to tell "you rotated
and never migrated" apart from "this key was never valid". The distinction leaks
nothing: observing KEY_EXPIRED requires already holding a real, if superseded,
key.

See ``documentation/plans/autocount/PLAN-autocount-integration.md`` §2.
"""
from __future__ import annotations

import enum
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.integration import Integration, IntegrationApiKey
from app.services.integration_key_crypto import (
    generate_api_key,
    hash_api_key,
    key_prefix,
)

logger = logging.getLogger(__name__)

# Long enough to cover a weekend plus someone being away; short enough that a
# forgotten rotation surfaces rather than lingering. Callers may override.
DEFAULT_GRACE_DAYS = 7


class AuthFailure(enum.Enum):
    """Why a key was refused. Surfaced to the caller as a distinct error code."""

    INVALID_KEY = "invalid_key"
    KEY_EXPIRED = "key_expired"
    KEY_REVOKED = "key_revoked"
    INTEGRATION_INACTIVE = "integration_inactive"


class IntegrationKeyService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ issue

    def issue_key(self, integration: Integration) -> str:
        """Mint a key for ``integration`` and return the plaintext.

        This is the only moment the plaintext exists outside the caller's own
        configuration -- only its hash is persisted, so it cannot be recovered
        later, only rotated.
        """
        plaintext = generate_api_key()
        self.db.add(
            IntegrationApiKey(
                integration_id=integration.id,
                key_hash=hash_api_key(plaintext),
                key_prefix=key_prefix(plaintext),
            )
        )
        self.db.flush()
        logger.info("integration.key_issued integration=%s", integration.name)
        return plaintext

    # ---------------------------------------------------------------- resolve

    def resolve(
        self, presented_key: Optional[str]
    ) -> Tuple[Optional[Integration], Optional[AuthFailure]]:
        """Authenticate a presented key.

        Returns ``(integration, None)`` on success or ``(None, AuthFailure)``.
        Never raises -- the caller decides the HTTP shape of the refusal.
        """
        if not presented_key:
            return None, AuthFailure.INVALID_KEY

        # Indexed lookup on the hash rather than a scan-and-compare over every
        # stored key. The hash is deterministic precisely so this can be one
        # query on the hot path of every external request.
        row = (
            self.db.query(IntegrationApiKey)
            .filter(IntegrationApiKey.key_hash == hash_api_key(presented_key))
            .first()
        )
        if row is None:
            return None, AuthFailure.INVALID_KEY

        # Revocation is deliberate and immediate, so it outranks expiry: a key
        # revoked during its grace window must report revoked, not expired.
        if row.revoked_at is not None:
            return None, AuthFailure.KEY_REVOKED

        if row.expires_at is not None and row.expires_at <= datetime.utcnow():
            return None, AuthFailure.KEY_EXPIRED

        integration = (
            self.db.query(Integration).filter(Integration.id == row.integration_id).first()
        )
        if integration is None:
            return None, AuthFailure.INVALID_KEY
        if not integration.is_active:
            return None, AuthFailure.INTEGRATION_INACTIVE

        # Stamped only on success. A failed attempt must not make a dead key
        # look live on the integrations screen -- that reading is what an admin
        # uses to decide whether closing a grace window is safe.
        self._stamp_usage(row, integration)

        return integration, None

    # ------------------------------------------------------------ usage stamp

    # How stale ``last_used_at`` may get before it is rewritten. It answers "is
    # this key still live?", which does not need second precision -- and writing
    # it on every request is precisely what made it a contention point.
    USAGE_STAMP_INTERVAL = timedelta(minutes=1)

    @classmethod
    def _stamp_is_stale(cls, value: Optional[datetime], now: datetime) -> bool:
        """True when the stamp needs rewriting.

        ``abs`` deliberately: the column is naive and everything here writes
        ``utcnow()``, but a value that ends up in the FUTURE -- clock skew, or a
        backfill run through a session on a non-UTC server timezone -- would make
        ``now - value`` negative and never reach the interval, silently disabling
        the stamp forever. Treating a far-future value as stale lets the next
        request correct it, while ordinary small skew still reads as fresh.
        """
        if value is None:
            return True
        return abs(now - value) >= cls.USAGE_STAMP_INTERVAL

    def _stamp_usage(self, key_row: IntegrationApiKey, integration: Integration) -> None:
        """Refresh ``last_used_at`` on the key and its integration, best-effort.

        This was ``key_row.last_used_at = now; integration.last_used_at = now;
        self.db.flush()``. Three things were wrong with it:

        1. The UPDATE took a row-exclusive lock on the SAME ``integrations`` row
           for EVERY api-key request, and a lock is held until the transaction
           ends -- which here is the end of the request. So the concurrency
           ceiling for all integration traffic was one request at a time, and a
           single slow request froze every other caller behind it. On 2026-08-10
           that produced 13 minutes of 504s with individual waits up to 155s.
        2. It was taken at the FIRST dependency and released at the LAST, so the
           lock spanned the caller's entire workload -- the worst possible hold.
        3. ``flush()`` never commits, and ``get_db`` only closes (which rolls
           back), so on read-only requests the write was discarded anyway. The
           timestamps admins were reading were wrong: a live read-only
           integration showed NULL forever.

        Now: skipped entirely unless the stamp is genuinely stale, and otherwise
        written on its own connection that commits immediately -- so the lock is
        held for microseconds and never spans the caller's work.

        Never raises. A stale timestamp is bookkeeping; failing an otherwise
        valid authentication over it would be far worse. That also covers the
        rare case where the extra connection cannot be checked out under pool
        pressure: we skip the stamp rather than make the shortage worse.
        """
        now = datetime.utcnow()
        if not self._stamp_is_stale(key_row.last_used_at, now) and not self._stamp_is_stale(
            integration.last_used_at, now
        ):
            return

        cutoff = now - self.USAGE_STAMP_INTERVAL
        # `get_bind()` is an Engine in production but a Connection under the
        # rolled-back-transaction test fixture; `.engine` normalises both.
        bind = self.db.get_bind()
        engine = getattr(bind, "engine", bind)
        try:
            with engine.connect() as conn:
                # Far below the connection-wide lock_timeout. If someone else is
                # mid-write on this row the stamp is already being refreshed, or
                # something is wrong -- either way waiting seconds to record a
                # timestamp is not worth a caller's latency. Give up almost at
                # once and let the next request try.
                conn.execute(text("SET LOCAL lock_timeout = '250ms'"))
                # The WHERE guard makes concurrent stampers idempotent: whoever
                # gets there first wins and the rest are no-ops, so a burst of
                # requests still produces one write per interval.
                conn.execute(
                    text(
                        "UPDATE integration_api_keys SET last_used_at = :now "
                        "WHERE id = :id "
                        "AND (last_used_at IS NULL OR last_used_at < :cutoff)"
                    ),
                    {"now": now, "id": key_row.id, "cutoff": cutoff},
                )
                conn.execute(
                    text(
                        "UPDATE integrations SET last_used_at = :now, updated_at = now() "
                        "WHERE id = :id "
                        "AND (last_used_at IS NULL OR last_used_at < :cutoff)"
                    ),
                    {"now": now, "id": integration.id, "cutoff": cutoff},
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001 - bookkeeping never fails auth
            logger.warning(
                "integration.usage_stamp_failed integration=%s: %s",
                integration.name,
                exc,
            )
            return

        # Reflect the stamp on the in-session objects so callers still read a
        # current value. `set_committed_value` writes the attribute WITHOUT
        # marking it dirty, so nothing is flushed and no lock is taken in the
        # caller's transaction -- which is the entire point of this method.
        # Only after a successful write, so a failed stamp never reads as a
        # successful one.
        set_committed_value(key_row, "last_used_at", now)
        set_committed_value(integration, "last_used_at", now)

    # ----------------------------------------------------------------- rotate

    def rotate_key(
        self, integration: Integration, grace_days: int = DEFAULT_GRACE_DAYS
    ) -> str:
        """Issue a replacement key and start the grace window on the current ones.

        Both old and new authenticate until the window lapses, so a caller with
        the key pasted across many places can migrate incrementally.
        """
        expires_at = datetime.utcnow() + timedelta(days=grace_days)

        superseded = (
            self.db.query(IntegrationApiKey)
            .filter(
                IntegrationApiKey.integration_id == integration.id,
                IntegrationApiKey.revoked_at.is_(None),
                IntegrationApiKey.expires_at.is_(None),
            )
            .all()
        )

        plaintext = generate_api_key()
        replacement = IntegrationApiKey(
            integration_id=integration.id,
            key_hash=hash_api_key(plaintext),
            key_prefix=key_prefix(plaintext),
            rotated_from_id=superseded[0].id if superseded else None,
        )
        for key in superseded:
            key.expires_at = expires_at

        self.db.add(replacement)
        self.db.flush()
        logger.info(
            "integration.key_rotated integration=%s superseded=%d grace_days=%d",
            integration.name,
            len(superseded),
            grace_days,
        )
        return plaintext

    # ----------------------------------------------------------------- revoke

    def revoke_key(self, key: IntegrationApiKey) -> None:
        """Kill a key immediately, ignoring any grace window it may be inside.

        This is the lever for a leaked key: waiting out a seven-day window is
        not an acceptable response to a secret that is already public.
        """
        key.revoked_at = datetime.utcnow()
        self.db.flush()
        logger.info(
            "integration.key_revoked integration_id=%s prefix=%s",
            key.integration_id,
            key.key_prefix,
        )
