"""Resolve stored user.avatar to a URL browsers can load (e.g. CloudFront signed)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Long enough for sessions; refreshed on each GET /me / profile update.
_AVATAR_SIGNED_URL_TTL_SEC = 7 * 24 * 3600


def resolve_avatar_url_for_client(stored: Optional[str]) -> Optional[str]:
    """
    DB stores stable CloudFront *base* URLs (https://dist/key) from get_cloudfront_base_url.
    If the distribution uses signed URLs, plain URLs 403 in <img>; sign here on read.
    External URLs (OAuth avatars, etc.) are returned unchanged.
    """
    if not stored or not str(stored).strip():
        return None
    s = str(stored).strip()
    if not s:
        return None
    # Already signed (CloudFront query params)
    if "Signature=" in s or "Policy=" in s or "Key-Pair-Id=" in s.lower():
        return s
    # Non-HTTPS (relative or unusual) — pass through
    if not s.startswith("https://"):
        return s
    try:
        from app.services.s3_service import S3Service

        s3 = S3Service()
        domain = s3._cloudfront_signer.dist_domain  # pylint: disable=protected-access
        prefix = f"https://{domain}/"
        if s.startswith(prefix):
            key = s[len(prefix) :].split("?")[0].lstrip("/")
            if key:
                return s3.get_signed_url(key, expires_in=_AVATAR_SIGNED_URL_TTL_SEC)
    except Exception:
        logger.debug("Could not sign avatar URL for client", exc_info=True)
    return s
