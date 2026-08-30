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


def clear_signin_background(db) -> None:
    """Drop the configured background so the sign-in page draws its default wash.

    Two callers need exactly this, which is why it is here rather than inline in the
    route: `POST /settings/signin-background` with `backgroundAction=remove`, and the
    deferred `signin_background.remove` record action (D7, S6b). The object itself is
    left in storage; what is removed is the setting that points at it.
    """
    from app.models.user import SystemSetting
    from app.services.error_handler import handle_not_found

    settings = db.query(SystemSetting).first()
    if not settings:
        raise handle_not_found("Settings", "current")
    # setattr, like every other write on the settings router: the legacy SQLAlchemy
    # mapping types a column attribute as Column[str], so a direct assignment reads as
    # an error to the type checker while behaving identically at runtime.
    setattr(settings, "signin_background", None)
    setattr(settings, "signin_background_storage_provider", None)
    db.commit()
