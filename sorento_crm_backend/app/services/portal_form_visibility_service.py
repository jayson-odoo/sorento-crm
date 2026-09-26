"""Portal form type visibility resolver.

Resolution logic (PLAN-portal-forms-market-segment D3, r2 lavish ruling):

1. Start from ``SUPPORTED_TYPES`` (the four legacy kinds) - every contact
   holds these by default, so a contact with no segment and no override
   still sees them.
2. Union in ``portal_form_types`` from every ACTIVE ``MarketSegment`` the
   contact belongs to (via ``respond_contact_market_segments``). An inactive
   segment's grant does not count (r4/SEC3) - deactivating a segment must
   revoke what it granted, the same as deleting it would, without needing a
   membership cleanup first. A segment only ever ADDS on top of the base
   (today: ``price_tag_request``); it cannot remove a base kind. Access
   types play no part any more (D1).
3. Apply per-contact overrides from ``contact_portal_form_overrides``:
   ``is_enabled=True`` adds a type; ``is_enabled=False`` removes it - this is
   the only way to hide a base kind, or to grant an opt-in kind without a
   segment.
"""
import logging

from fastapi import status
from sqlalchemy.orm import Session

from app.models.access import MarketSegment, respond_contact_market_segments
from app.models.price_tag import ContactPortalFormOverride
from app.services.error_handler import AppException
from app.services.portal_service import SUPPORTED_TYPES

logger = logging.getLogger(__name__)

# The BE equivalent of `LANDING_LABELS` in
# sorento_crm_frontend/lib/portal-form-kinds.ts (N3) - kept in step so a
# hidden-kind 403 reads the same name the FE's own inline messages use.
_KIND_LABELS: dict[str, str] = {
    "complaint": "Complaint",
    "stock_inquiry": "Stock Inquiry",
    "purchase_request": "Purchase Request",
    "sponsorship_form": "Sponsorship Form",
    "price_tag_request": "Price Tag Request",
    "sales_opportunity": "Sales Opportunities",
}


def inherited_form_types(db: Session, contact_id: str) -> set[str]:
    """Base four kinds plus the union of ``portal_form_types`` across the
    contact's assigned market segments.

    Shared by ``resolve_visible_form_types`` (steps 1+2 below) and the
    ``contact_portal_forms`` admin route, which needs the same union to show
    "inherited" separately from any per-contact override.
    """
    inherited: set[str] = set(SUPPORTED_TYPES)
    rows = (
        db.query(MarketSegment.portal_form_types)
        .join(
            respond_contact_market_segments,
            respond_contact_market_segments.c.segment_code == MarketSegment.code,
        )
        .filter(
            respond_contact_market_segments.c.contact_id == contact_id,
            MarketSegment.is_active.is_(True),
        )
        .all()
    )
    for (form_types,) in rows:
        if isinstance(form_types, list):
            inherited.update(form_types)
    return inherited


def resolve_visible_form_types(db: Session, contact_id: str) -> set[str]:
    """Return the set of portal form type strings visible to ``contact_id``."""

    # Steps 1+2: base four, plus the union of portal_form_types across the
    # contact's assigned market segments.
    visible = inherited_form_types(db, contact_id)

    # Step 3: apply per-contact overrides.
    overrides = (
        db.query(ContactPortalFormOverride)
        .filter(ContactPortalFormOverride.contact_id == contact_id)
        .all()
    )
    for override in overrides:
        if override.is_enabled:
            visible.add(override.form_type)
        else:
            visible.discard(override.form_type)

    return visible


def _label_for(kind: str) -> str:
    return _KIND_LABELS.get(kind, kind.replace("_", " ").capitalize())


def require_form_visible(db: Session, contact_id: str, kind: str) -> None:
    """The one gate (D5): 403 FORM_TYPE_NOT_VISIBLE when the contact's
    resolved ``visible_form_types`` excludes ``kind``. Lives here (not in
    ``app.api.v1.public.portal``) so a second router - ``ai_extract.py``
    (SEC4) - can call the same gate without importing from another router
    module or duplicating it."""
    if kind in resolve_visible_form_types(db, contact_id):
        return
    raise AppException(
        status_code=status.HTTP_403_FORBIDDEN,
        message=f"{_label_for(kind)} is not available for your account.",
        code="FORM_TYPE_NOT_VISIBLE",
    )
