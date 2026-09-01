"""Per-contact portal form visibility override, for the CRM operator.

`GET|PUT /api/v1/user-management/contacts/{contact_id}/portal-forms`.

Resolution lives in `app.services.portal_form_visibility_service`: a contact's
visible form types are the union of `portal_form_types` across its assigned
access types, then per-contact rows in `contact_portal_form_overrides` win
(`is_enabled=True` adds a type even if no access type grants it, `False`
removes one even if every access type does). That table and resolver existed
with nothing writing to it; this route is the admin surface that writes it.

Only GATED kinds are subject to this at all - the four legacy submission kinds
(complaint, stock_inquiry, purchase_request, sponsorship_form) are always on
the portal landing and are never listed here. `GATED_FORM_TYPES` below mirrors
`GATED_LANDING_KINDS` in `sorento_crm_frontend/lib/portal-form-kinds.ts`; the
next gated form joins both lists.
"""
import logging

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.access import ContactAccessType, RespondContact, respond_contact_access_types
from app.models.price_tag import ContactPortalFormOverride
from app.services.error_handler import handle_internal_error, handle_not_found, handle_unprocessable

logger = logging.getLogger(__name__)

router = APIRouter()

CONTACT_VIEW_PERMISSION = "user_management.contacts.view"
CONTACT_EDIT_PERMISSION = "user_management.contacts.edit"

# Mirrors GATED_LANDING_KINDS in sorento_crm_frontend/lib/portal-form-kinds.ts.
GATED_FORM_TYPES: tuple[str, ...] = ("price_tag_request",)


class ContactPortalFormOverrideInput(BaseModel):
    form_type: str
    is_enabled: bool | None = None


class ContactPortalFormsUpdate(BaseModel):
    overrides: list[ContactPortalFormOverrideInput]


def _require_contact(db: Session, contact_id: str) -> RespondContact:
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)
    return contact


def _inherited_form_types(db: Session, contact_id: str) -> set[str]:
    """Union of portal_form_types across the contact's assigned access types."""
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


def _build_view(db: Session, contact_id: str) -> dict:
    inherited = _inherited_form_types(db, contact_id)
    overrides = {
        row.form_type: row.is_enabled
        for row in db.query(ContactPortalFormOverride)
        .filter(ContactPortalFormOverride.contact_id == contact_id)
        .all()
    }
    forms = []
    for form_type in GATED_FORM_TYPES:
        is_inherited = form_type in inherited
        override = overrides.get(form_type)
        effective = override if override is not None else is_inherited
        forms.append(
            {
                "form_type": form_type,
                "inherited": is_inherited,
                "override": override,
                "effective": effective,
            }
        )
    return {"forms": forms}


@router.get("/{contact_id}/portal-forms", status_code=status.HTTP_200_OK)
async def get_contact_portal_forms(
    contact_id: str,
    current_user: dict = Depends(require_permission(CONTACT_VIEW_PERMISSION)),
    db: Session = Depends(get_db),
):
    """One row per gated form kind: whether it is inherited, overridden, and effective."""
    _ = current_user
    try:
        _require_contact(db, contact_id)
        return _build_view(db, contact_id)
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.exception("failed to read portal forms for contact %s", contact_id)
        raise handle_internal_error(str(exc))


@router.put("/{contact_id}/portal-forms", status_code=status.HTTP_200_OK)
async def update_contact_portal_forms(
    contact_id: str,
    payload: ContactPortalFormsUpdate,
    current_user: dict = Depends(require_permission(CONTACT_EDIT_PERMISSION)),
    db: Session = Depends(get_db),
):
    """Upsert or clear override rows, then return the recomputed view.

    `is_enabled=None` deletes the row (back to inherit); True/False upserts it,
    updating an existing row in place rather than inserting a duplicate - the
    unique constraint is on (contact_id, form_type).
    """
    _ = current_user
    try:
        _require_contact(db, contact_id)
        for item in payload.overrides:
            if item.form_type not in GATED_FORM_TYPES:
                raise handle_unprocessable(f"'{item.form_type}' is not a gated form type.")

        existing = {
            row.form_type: row
            for row in db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact_id)
            .all()
        }
        for item in payload.overrides:
            row = existing.get(item.form_type)
            if item.is_enabled is None:
                if row is not None:
                    db.delete(row)
            elif row is not None:
                row.is_enabled = item.is_enabled
            else:
                db.add(
                    ContactPortalFormOverride(
                        contact_id=contact_id,
                        form_type=item.form_type,
                        is_enabled=item.is_enabled,
                    )
                )
        db.commit()
        return _build_view(db, contact_id)
    except Exception as exc:
        if hasattr(exc, "status_code"):
            db.rollback()
            raise
        db.rollback()
        logger.exception("failed to update portal forms for contact %s", contact_id)
        raise handle_internal_error(str(exc))
