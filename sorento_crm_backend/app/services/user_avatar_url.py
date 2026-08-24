"""Resolve stored user.avatar to a URL browsers can load (signed CloudFront or Cloudflare CDN)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Long enough for sessions; refreshed on each GET /me / profile update.
_AVATAR_SIGNED_URL_TTL_SEC = 7 * 24 * 3600


def resolve_avatar_url_for_client(
    stored: Optional[str],
    provider: Optional[str] = None,
) -> Optional[str]:
    """Sign the avatar URL using whichever provider currently hosts the file.

    DB stores a stable, non-signed CDN base URL. The matching
    ``avatar_storage_provider`` column tells us which backend to ask for a
    fresh signed URL. External URLs (OAuth avatars, etc.) are returned as-is.
    """
    if not stored or not str(stored).strip():
        return None
    s = str(stored).strip()
    if not s:
        return None
    # Non-HTTPS (relative or unusual) - pass through
    if not s.startswith("https://"):
        return s
    try:
        from app.services.storage_router import (
            detect_provider_from_url,
            extract_key,
            get_backend,
            normalize_provider,
        )

        # Only sign URLs we own; pass through external avatars (Google etc).
        host_provider = detect_provider_from_url(s)
        if not host_provider and provider is None:
            return s
        chosen = normalize_provider(provider) if provider else host_provider
        key = extract_key(s)
        if not key:
            return s
        return get_backend(chosen).get_signed_url(key, expires_in=_AVATAR_SIGNED_URL_TTL_SEC)
    except Exception:
        logger.debug("Could not sign avatar URL for client", exc_info=True)
    return s
