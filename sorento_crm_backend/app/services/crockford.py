"""Crockford base32 tokens - the one alphabet every user-visible token uses.

Extracted from ``portal_service`` when onboarding gained a second token family.
Two modules each choosing "the Crockford alphabet" from memory is how one of
them ends up including ``O`` and starts producing tokens people mistype off a
screenshot, so the alphabet lives in one place and both import it.

The alphabet excludes ``I``, ``L``, ``O`` and ``U`` to remove the look-alike
pairs (I/l/1, O/0) and one accidental-obscenity source. That costs about 14% of
the density of base64url, which is a bargain for a string that gets read aloud
over the phone: 48 characters x 5 bits = 240 bits of entropy, equivalent to
``secrets.token_urlsafe(30)``.
"""
from __future__ import annotations

import secrets

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: The default length for a credential-grade token.
CROCKFORD_TOKEN_LEN = 48


def crockford_token(length: int = CROCKFORD_TOKEN_LEN) -> str:
    """A cryptographically random Crockford base32 string of ``length`` chars."""
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(length))
