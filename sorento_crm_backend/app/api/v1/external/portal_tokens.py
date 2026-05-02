"""External API: mint a user submission portal token for a contact.

Auth: X-API-Key header (get_external_api_user). Used by the MCP server / n8n to
hand the contact a 7-day portal link. n8n is trusted, so OTP is bypassed here;
when a token expires the contact re-verifies themselves via the portal's OTP
flow on the public router.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.portal_service import PortalService

router = APIRouter()


class PortalTokenRequest(BaseModel):
    contact_id: str = Field(..., description="Respond.io contact id (respond_contacts.id).")
    space_id: str = Field(..., description="Respond.io space id.")
    base_url: str | None = Field(
        default=None,
        description="Optional FE base URL; falls back to FRONTEND_BASE_URL.",
    )
    submission_type: str | None = Field(
        default=None,
        description=(
            "Optional submission tab to deep-link: complaint | stock_inquiry | "
            "purchase_request | sponsorship_form. When provided, the portal opens "
            "directly on that tab after token verify."
        ),
    )


class PortalTokenResponse(BaseModel):
    token: str
    expires_at: str
    portal_url: str


@router.post("/", response_model=PortalTokenResponse)
def mint_portal_token(
    payload: PortalTokenRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    service = PortalService(db)
    try:
        token = service.mint_token(payload.contact_id, payload.space_id)
    except HTTPException:
        raise
    return PortalTokenResponse(
        token=token.token,
        expires_at=token.expires_at.isoformat(),
        portal_url=service.build_portal_url(
            token.token, payload.base_url, payload.submission_type
        ),
    )
