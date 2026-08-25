"""Stock visibility policy admin API.

Three tiers, one body shape (`{effective, override}`), so the one admin card can
serve the contact page, the access-type admin and the settings default. Reads are
gated on `inventory.stock.view` and writes on `inventory.stock.edit` - no new
permission slug, because "who may be told about which stock" is a stock decision
and minting a slug would need a grant sweep before anybody could use the screen.

`GET /effective` is the n8n preflight CONVENIENCE. It exists so a workflow can
phrase an answer without fetching, and it is deliberately reachable with the
integration key's act-as principal. Enforcement itself lives in
`StockService.list_stock`; forgetting to call this must never be the difference
between safe and leaking.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.stock_visibility import (
    StockVisibilityInput,
    StockVisibilityPolicyOut,
    StockVisibilityPolicyResponse,
)
from app.services.error_handler import handle_not_found
from app.services.stock_visibility import (
    Policy,
    access_type_override,
    contact_override,
    default_policy,
    delete_policy,
    effective_policy_for_access_type,
    policy_payload,
    resolve_policy,
    upsert_policy,
    validated_warehouse_ids,
)

router = APIRouter()

READ = "inventory.stock.view"
WRITE = "inventory.stock.edit"


def _contact_effective(db: Session, resolved_contact_id: str) -> Policy:
    """The tier this contact actually gets. The contact has already been resolved
    by the caller, so the fail-closed `None` arm cannot be reached here."""
    return resolve_policy(db, resolved_contact_id) or default_policy(db)


def _resolved_contact(db: Session, contact_id: str) -> str:
    """Either id form -> the internal `respond_contacts.id`, or 404."""
    from app.services.field_access import resolve_contact_id

    resolved = resolve_contact_id(db, contact_id)
    if not resolved:
        raise handle_not_found("Contact", contact_id)
    return resolved


def _require_access_type(db: Session, code: str) -> str:
    """404 rather than a dangling row: the FK would refuse it anyway, and a 500
    tells the admin nothing about which code was wrong."""
    from app.models.access import ContactAccessType

    exists = db.query(ContactAccessType.code).filter(ContactAccessType.code == code).first()
    if not exists:
        raise handle_not_found("Contact access type", code)
    return code


def _response(db: Session, *, effective: Policy, override_row) -> dict:
    """`{effective, override}` - override null when the tier inherits."""
    override = None
    if override_row is not None:
        override = policy_payload(
            db,
            Policy(
                mode=override_row.mode,
                warehouse_ids=(
                    None
                    if override_row.warehouse_ids is None
                    else frozenset(str(w) for w in override_row.warehouse_ids)
                ),
                source=effective.source,
                source_label=effective.source_label,
            ),
        )
    return {"effective": policy_payload(db, effective), "override": override}


# ------------------------------------------------------------------ preflight


@router.get("/effective", response_model=StockVisibilityPolicyOut)
def get_effective_policy(
    contact_id: Optional[str] = Query(
        None,
        description=(
            "respond_contacts.id or the Respond.io id. Omitted = the global default, "
            "which is what a caller with no contact identity gets."
        ),
    ),
    space_id: Optional[str] = Query(
        None, description="Respond.io workspace id, to disambiguate a Respond.io contact_id."
    ),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The policy that would be applied to this contact's next stock question."""
    if not contact_id:
        return policy_payload(db, default_policy(db))
    policy = resolve_policy(db, contact_id, space_id)
    if policy is None:
        raise handle_not_found("Contact", contact_id)
    return policy_payload(db, policy)


# -------------------------------------------------------------- contact tier


@router.get("/contacts/{contact_id}", response_model=StockVisibilityPolicyResponse)
def get_contact_policy(
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    resolved = _resolved_contact(db, contact_id)
    effective = _contact_effective(db, resolved)
    return _response(db, effective=effective, override_row=contact_override(db, resolved))


@router.put("/contacts/{contact_id}", response_model=StockVisibilityPolicyResponse)
def put_contact_policy(
    body: StockVisibilityInput,
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    """Upsert the contact override. Saving on an inheriting tier is what creates it."""
    resolved = _resolved_contact(db, contact_id)
    upsert_policy(
        db,
        mode=body.mode,
        warehouse_ids=validated_warehouse_ids(db, body.warehouse_ids),
        contact_id=resolved,
    )
    effective = _contact_effective(db, resolved)
    return _response(db, effective=effective, override_row=contact_override(db, resolved))


@router.delete("/contacts/{contact_id}", response_model=StockVisibilityPolicyResponse)
def delete_contact_policy(
    contact_id: str = Path(..., description="respond_contacts.id or the Respond.io id."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    """Hard delete of the override. The body carries the tier the contact falls
    back to, so the card re-renders the inherited policy without a refetch."""
    resolved = _resolved_contact(db, contact_id)
    delete_policy(db, contact_id=resolved)
    effective = _contact_effective(db, resolved)
    return _response(db, effective=effective, override_row=None)


# ---------------------------------------------------------- access type tier


@router.get("/access-types/{code}", response_model=StockVisibilityPolicyResponse)
def get_access_type_policy(
    code: str = Path(..., description="contact_access_types.code, e.g. `dealer`."),
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    _require_access_type(db, code)
    return _response(
        db,
        effective=effective_policy_for_access_type(db, code),
        override_row=access_type_override(db, code),
    )


@router.put("/access-types/{code}", response_model=StockVisibilityPolicyResponse)
def put_access_type_policy(
    body: StockVisibilityInput,
    code: str = Path(..., description="contact_access_types.code, e.g. `dealer`."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    """One row per access type is what makes the dealer roll-out scale: every
    contact tagged `dealer` inherits it, so no per-dealer row is ever needed."""
    _require_access_type(db, code)
    upsert_policy(
        db,
        mode=body.mode,
        warehouse_ids=validated_warehouse_ids(db, body.warehouse_ids),
        access_type_code=code,
    )
    return _response(
        db,
        effective=effective_policy_for_access_type(db, code),
        override_row=access_type_override(db, code),
    )


@router.delete("/access-types/{code}", response_model=StockVisibilityPolicyResponse)
def delete_access_type_policy(
    code: str = Path(..., description="contact_access_types.code, e.g. `dealer`."),
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_access_type(db, code)
    delete_policy(db, access_type_code=code)
    return _response(
        db,
        effective=effective_policy_for_access_type(db, code),
        override_row=None,
    )


# ------------------------------------------------------------- default tier


@router.get("/default", response_model=StockVisibilityPolicyResponse)
def get_default_policy(
    current_user: dict = Depends(require_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The floor of the chain. Its override is always present and equals the
    effective policy, and there is deliberately NO delete."""
    policy = default_policy(db)
    payload = policy_payload(db, policy)
    return {"effective": payload, "override": payload}


@router.put("/default", response_model=StockVisibilityPolicyResponse)
def put_default_policy(
    body: StockVisibilityInput,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    upsert_policy(
        db,
        mode=body.mode,
        warehouse_ids=validated_warehouse_ids(db, body.warehouse_ids),
    )
    payload = policy_payload(db, default_policy(db))
    return {"effective": payload, "override": payload}
