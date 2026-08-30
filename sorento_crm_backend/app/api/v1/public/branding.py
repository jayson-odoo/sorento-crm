"""Public branding: what an anonymous visitor may see before signing in.

ONE field, and the response model is what makes "and nothing else" enforceable: anything not
declared here is dropped on serialization rather than leaking because a dict builder grew a line.
The same discipline as `GET /user-management/settings/app-config`, and a stricter reason for it,
because this route has no principal at all.

DO NOT WIDEN THIS. Not the company name, not the support email, not the logo, not the currency.
Every field added here is published to the internet with no credential; the sign-in page needs a
background image and nothing more. A caller that needs anything else has a session and can ask
`/user-management/settings/app-config` or the full settings blob.

The URL is signed and short-lived (see `app.services.signin_background`), so it is a link to the
image for the length of a login attempt rather than a permanent public address for the object.
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import SystemSetting
from app.services.signin_background import resolve_signin_background_url

logger = logging.getLogger(__name__)

router = APIRouter()


class PublicBrandingResponse(BaseModel):
    """Null means no admin has uploaded one, and the sign-in page draws its own design."""

    signin_background_url: str | None = None


@router.get("", response_model=PublicBrandingResponse)
def get_public_branding(db: Session = Depends(get_db)) -> PublicBrandingResponse:
    """The sign-in background, if one is configured.

    Never raises. The background is decoration on the one screen a person uses to get INTO the
    system, so a storage outage or a half-migrated row must cost them nothing: every failure
    resolves to "no background" and the page falls back to its designed default.
    """
    try:
        settings = db.query(SystemSetting).first()
        return PublicBrandingResponse(
            signin_background_url=resolve_signin_background_url(settings)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Public branding lookup failed; serving no background", exc_info=True)
        return PublicBrandingResponse(signin_background_url=None)
