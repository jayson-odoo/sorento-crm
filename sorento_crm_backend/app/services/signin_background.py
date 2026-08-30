"""Resolve the stored sign-in background to a URL a browser can actually load.

`system_settings.signin_background` holds a stable, NON-signed CDN URL; the CDN itself
serves signed URLs only. So every read has to re-sign, and three call sites need the same
answer: the settings GET (for the admin's preview), the upload response, and the public
`GET /api/v1/public/branding` the anonymous sign-in page asks. One function so the TTL and
the strictness cannot drift between them.

`strict=True` is the whole point of doing this in one place: an unsignable key must come
back as "no background" and let the sign-in page draw its designed default, not as a raw
URL the CDN answers 403 to and the visitor sees as a broken image behind the login form.
"""
from __future__ import annotations

from typing import Any, Optional

#: Long enough that a sign-in page left open over lunch still shows the image, short
#: enough that a URL copied out of the anonymous response is not a durable public link
#: to the object.
SIGNIN_BACKGROUND_URL_TTL_SECONDS = 6 * 3600


def resolve_signin_background_url(settings: Optional[Any]) -> Optional[str]:
    """Return a signed URL for the configured background, or None when there is none."""
    stored = getattr(settings, "signin_background", None) if settings else None
    if not stored:
        return None
    from app.services.storage_router import resolve_signed_url

    return resolve_signed_url(
        stored,
        provider=getattr(settings, "signin_background_storage_provider", None),
        expires_in=SIGNIN_BACKGROUND_URL_TTL_SECONDS,
        strict=True,
    )
