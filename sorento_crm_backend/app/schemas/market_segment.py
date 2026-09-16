"""Market-segment catalog + assignment schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_portal_form_types(value: Optional[List[str]]) -> Optional[List[str]]:
    """Reject a portal form kind the portal does not serve.

    Raising here rather than in the service is deliberate: an unknown kind is a
    malformed request and answers 422, the same as any other bad field. The
    canonical list is imported lazily because ``portal_service`` pulls in models
    and services that must not be loaded while the schema module is importing.
    """
    if value is None:
        return value
    from app.services.portal_service import GRANTABLE_PORTAL_FORM_TYPES

    unknown = [v for v in value if v not in GRANTABLE_PORTAL_FORM_TYPES]
    if unknown:
        raise ValueError(
            f"Unknown portal form type(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(GRANTABLE_PORTAL_FORM_TYPES)}."
        )
    return value


class MarketSegmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: Optional[int] = None
    # Contacts in this segment are offered in the requestor picker ("Requested by" /
    # "Salesperson") on PR / SF / stock inquiry. Admin-visible indicator.
    is_requestor_selectable: bool = False
    # Portal forms this segment grants BEYOND the base four every contact
    # already sees (PLAN-portal-forms-market-segment D1/D3/D4). Empty = this
    # segment grants nothing extra; today the only valid entry beyond the
    # base is "price_tag_request".
    portal_form_types: List[str] = []

    @field_validator("portal_form_types")
    @classmethod
    def _known_portal_form_types(cls, v):
        return _validate_portal_form_types(v)


class MarketSegmentCreate(MarketSegmentBase):
    code: str


class MarketSegmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    is_requestor_selectable: Optional[bool] = None
    portal_form_types: Optional[List[str]] = None

    @field_validator("portal_form_types")
    @classmethod
    def _known_portal_form_types(cls, v):
        return _validate_portal_form_types(v)


class MarketSegmentResponse(MarketSegmentBase):
    model_config = ConfigDict(from_attributes=True)
    code: str


class MarketSegmentCodesUpdate(BaseModel):
    """Replace a contact's / member's segment assignment with this exact set."""
    codes: List[str] = []


class MarketSegmentCodesResponse(BaseModel):
    codes: List[str] = []
