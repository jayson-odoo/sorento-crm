"""Crypto primitives for integration API keys (AutoCount Group A, slice 1).

Four functions, deliberately small and dependency-free, because every other
authorization decision in Group A rests on them:

    generate_api_key()  mint a new key   -> shown to the operator exactly once
    hash_api_key()      what we persist  -> the plaintext is never stored
    key_prefix()        safe to display  -> identifies a key without revealing it
    verify_api_key()    the check itself -> constant-time

Why SHA-256 and not bcrypt/argon2: these are 256-bit random secrets, not
human-chosen passwords. There is no dictionary to attack and no meaningful
offline-cracking advantage to slow down, so a slow KDF buys nothing. What it
would cost is real: a deterministic hash lets verification be a single indexed
lookup on ``key_hash``, whereas a salted KDF forces a scan of every stored key
with a KDF invocation per row — on the hot path of every external request.

See ``documentation/plans/autocount/PLAN-autocount-integration.md`` §2 (A1-A8).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

# Marks a Sorento-issued key on sight, in a config file or a leaked log line.
KEY_PREFIX = "sk_"

# 32 bytes -> 256 bits of entropy, ~43 urlsafe-base64 characters.
_KEY_BYTES = 32

# How much of the key we are willing to show. Long enough to tell two keys
# apart in a list; short enough that displaying it reveals nothing usable.
_DISPLAY_PREFIX_LEN = 11


def generate_api_key() -> str:
    """Mint a new plaintext API key. Shown once at creation, then never again."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(_KEY_BYTES)}"


def hash_api_key(key: str) -> str:
    """Return the hex SHA-256 digest persisted in ``integration_api_keys.key_hash``."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_prefix(key: str) -> str:
    """Return the short, non-secret fragment shown in the UI to identify a key."""
    return key[:_DISPLAY_PREFIX_LEN]


def verify_api_key(key: Optional[str], stored_hash: Optional[str]) -> bool:
    """Constant-time check of a presented key against a stored hash (AC-AC-04).

    Returns False — never raises — for absent input on either side. A blank or
    missing ``stored_hash`` must never authenticate anyone: that is the state a
    naive seed would leave behind if ``EXTERNAL_API_KEY`` were absent at
    migration time (AC-AC-09).
    """
    if not key or not stored_hash:
        return False
    return hmac.compare_digest(hash_api_key(key), stored_hash)
