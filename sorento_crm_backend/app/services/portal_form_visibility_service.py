"""Portal form type visibility resolver.

Resolution logic (AC-A.1 through AC-A.3):

1. Collect the ``portal_form_types`` JSONB from every ``ContactAccessType`` the
   contact is assigned to (via the ``respond_contact_access_types`` m2m).
2. Union all those lists into a single set of type strings.
3. Apply per-contact overrides from ``contact_portal_form_overrides``:
   ``is_enabled=True`` adds a type; ``is_enabled=False`` removes it.
4. Empty resolved set = contact sees nothing (fail-closed).
"""
import logging

from sqlalchemy.orm import Session

from app.models.access import (
    ContactAccessType,
    respond_contact_access_types,
)
from app.models.price_tag import ContactPortalFormOverride

logger = logging.getLogger(__name__)


def inherited_form_types(db: Session, contact_id: str) -> set[str]:
    """Union of ``portal_form_types`` across the contact's assigned access types.

    Shared by ``resolve_visible_form_types`` (step 1+2 below) and the
    ``contact_portal_forms`` admin route, which needs the same union to show
    "inherited" separately from any per-contact override.
    """
    rows = (
        db.query(ContactAccessType.portal_form_types)
        .join(
            respond_contact_access_types,
            respond_contact_access_types.c.access_type_code == ContactAccessType.code,
        )
        .filter(respond_contact_access_types.c.contact_id == contact_id)
        .all()
    )
    inherited: set[str] = set()
    for (form_types,) in rows:
        if isinstance(form_types, list):
            inherited.update(form_types)
    return inherited


def resolve_visible_form_types(db: Session, contact_id: str) -> set[str]:
    """Return the set of portal form type strings visible to ``contact_id``."""

    # Step 1+2: union of portal_form_types across assigned access types.
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
