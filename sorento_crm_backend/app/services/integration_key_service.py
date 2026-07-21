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

from sqlalchemy.orm import Session

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
        now = datetime.utcnow()
        row.last_used_at = now
        integration.last_used_at = now
        self.db.flush()

        return integration, None

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
