"""Spec visibility policy admin API.

Which product spec keys (Thickness, Material, ...) the chatbot may reveal to a
contact. Three tiers, one body shape (`{effective, override}`) - same doctrine as
`app.api.v1.inventory.stock_visibility`. Mounted under user-management (contact-
side admin, not inventory) because the tier axis is the CONTACT and its market
segments, and reuses `user_management.contacts.view` / `.edit` - no new
permission slug (field-reveal precedent).

`GET /effective` is the n8n preflight CONVENIENCE, reachable with the
integration key's act-as principal. Enforcement itself lives in
`check_access` / `output_structurer`; forgetting to call this must never be the
difference between safe and leaking.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.spec_visibility import (
    SpecKeyRef,
    SpecVisibilityInput,
    SpecVisibilityPolicyOut,
    SpecVisibilityPolicyResponse,
)
from app.services.error_handler import handle_not_found
from app.services.spec_visibility import (
    SpecPolicy,
    active_registry_rows,
    contact_override,
    default_policy,
    delete_policy,
    effective_policy_for_segment,
    policy_payload,
    require_segment,
    resolve_policy,
    segment_override,
    upsert_policy,
)

router = APIRouter()

READ = "user_management.contacts.view"
WRITE = "user_management.contacts.edit"


def _contact_effective(db: Session, resolved_contact_id: str) -> SpecPolicy:
    """The tier this contact actually gets. `resolve_policy` never returns
    "no policy" - an unresolvable contact already fails closed to the default."""
    return resolve_policy(db, resolved_contact_id)


def _resolved_contact(db: Session, contact_id: str, space_id: Optional[str] = None) -> str:
    """Either id form -> the internal `respond_contacts.id`, or 404."""
    from app.services.field_access import resolve_contact_id

    resolved = resolve_contact_id(db, contact_id, space_id)
    if not resolved:
        raise handle_not_found("Contact", contact_id)
    return resolved


def _response(db: Session, *, effective: SpecPolicy, has_override: bool) -> dict:
    """`{effective, override}` - override null when the tier inherits.

    When the tier DOES hold a row, that row is what `effective` was resolved
    from, so the two payloads are the same object rather than a second
    hand-rebuilt copy that could drift from it.
    """
    payload = policy_payload(db, effective)
    return {"effective": payload, "override": payload if has_override else None}


# ------------------------------------------------------------------ preflight


@router.get("/effective", response_model=SpecVisibilityPolicyOut)
def get_effective_policy(
    contact_id: Optional[str] = Query(
        None,
        description=(
            "respond_contacts.id or the Respond.io id. Omitted = the global "
            "default, which is what a caller with no contact identity gets."
        ),
    ),
    space_id: Optional[str] = Query(
        None, description="Respond.io workspace id, to disambiguate a Respond.io contact_id."
    ),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The policy that would be applied to this contact's next spec question."""
    if not contact_id:
        return policy_payload(db, default_policy(db))
    return policy_payload(db, resolve_policy(db, contact_id, space_id))


# -------------------------------------------------------------- contact tier


@router.get("/contacts/{contact_id}", response_model=SpecVisibilityPolicyResponse)
def get_contact_policy(
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    space_id: Optional[str] = Query(
        None, description="Respond.io workspace id, to disambiguate a Respond.io contact_id."
    ),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    resolved = _resolved_contact(db, contact_id, space_id)
    effective = _contact_effective(db, resolved)
    return _response(
        db, effective=effective, has_override=contact_override(db, resolved) is not None
    )


@router.put("/contacts/{contact_id}", response_model=SpecVisibilityPolicyResponse)
def put_contact_policy(
    body: SpecVisibilityInput,
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    space_id: Optional[str] = Query(
        None, description="Respond.io workspace id, to disambiguate a Respond.io contact_id."
    ),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    """Upsert the contact override. Saving on an inheriting tier is what creates it."""
    resolved = _resolved_contact(db, contact_id, space_id)
    upsert_policy(
        db,
        spec_keys=body.spec_keys,
        excluded_spec_keys=body.excluded_spec_keys,
        contact_id=resolved,
    )
    effective = _contact_effective(db, resolved)
    return _response(
        db, effective=effective, has_override=contact_override(db, resolved) is not None
    )


@router.delete("/contacts/{contact_id}", response_model=SpecVisibilityPolicyResponse)
def delete_contact_policy(
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    space_id: Optional[str] = Query(
        None, description="Respond.io workspace id, to disambiguate a Respond.io contact_id."
    ),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    """Hard delete of the override. 404 when the tier already inherits - there
    is nothing here for DELETE to have done."""
    resolved = _resolved_contact(db, contact_id, space_id)
    if not delete_policy(db, contact_id=resolved):
        raise handle_not_found("Spec visibility override", contact_id)
    effective = _contact_effective(db, resolved)
    return _response(db, effective=effective, has_override=False)


# --------------------------------------------------------- market segment tier


@router.get("/segments/{segment_code}", response_model=SpecVisibilityPolicyResponse)
def get_segment_policy(
    segment_code: str = Path(..., description="market_segments.code, e.g. `retail`."),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    require_segment(db, segment_code)
    return _response(
        db,
        effective=effective_policy_for_segment(db, segment_code),
        has_override=segment_override(db, segment_code) is not None,
    )


@router.put("/segments/{segment_code}", response_model=SpecVisibilityPolicyResponse)
def put_segment_policy(
    body: SpecVisibilityInput,
    segment_code: str = Path(..., description="market_segments.code, e.g. `retail`."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    require_segment(db, segment_code)
    upsert_policy(
        db,
        spec_keys=body.spec_keys,
        excluded_spec_keys=body.excluded_spec_keys,
        segment_code=segment_code,
    )
    return _response(
        db,
        effective=effective_policy_for_segment(db, segment_code),
        has_override=segment_override(db, segment_code) is not None,
    )


@router.delete("/segments/{segment_code}", response_model=SpecVisibilityPolicyResponse)
def delete_segment_policy(
    segment_code: str = Path(..., description="market_segments.code, e.g. `retail`."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    require_segment(db, segment_code)
    if not delete_policy(db, segment_code=segment_code):
        raise handle_not_found("Spec visibility override", segment_code)
    return _response(
        db,
        effective=effective_policy_for_segment(db, segment_code),
        has_override=False,
    )


# ------------------------------------------------------------- default tier


@router.get("/default", response_model=SpecVisibilityPolicyResponse)
def get_default_policy(
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The floor of the chain. Its override is always present and equals the
    effective policy, and there is deliberately NO delete."""
    policy = default_policy(db)
    payload = policy_payload(db, policy)
    return {"effective": payload, "override": payload}


@router.put("/default", response_model=SpecVisibilityPolicyResponse)
def put_default_policy(
    body: SpecVisibilityInput,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    upsert_policy(db, spec_keys=body.spec_keys, excluded_spec_keys=body.excluded_spec_keys)
    payload = policy_payload(db, default_policy(db))
    return {"effective": payload, "override": payload}


# ------------------------------------------------------------------- picker


@router.get("/keys", response_model=list[SpecKeyRef])
def get_spec_keys(
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """Active registry keys, sorted by label - a separate route from the
    products list so a contacts admin does not need `master_data.products.view`
    to open this card."""
    return [{"key": key, "label": label} for key, label in active_registry_rows(db)]
