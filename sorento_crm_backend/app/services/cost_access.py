"""Who may see product cost: `products.cost.view` (SUPPLIER-COST-ACCESS, owner + management 9 Nov 2026).

Cost price, supplier unit costs and last purchase / PO costs are for purchasing and management.
Plan: `documentation/plans/products/PLAN-supplier-cost-access-10nov.md`.

Two ways it is enforced:

- A route that is ONLY cost (purchase history, product-supplier links, PO last cost) requires the
  permission outright (`require_cost_view`).
- A payload that carries cost next to other fields (a product) keeps its shape and returns
  `cost_price` as null. The staff auth dependencies (`get_current_user`,
  `get_current_user_or_api_key`, both `async def`, so the value lands on the request's own
  context the way the audit actor stamp does) call `stamp_cost_visibility`, and
  `ProductResponse` reads `cost_hidden()` when it serializes. Outside a staff request (worker,
  scheduler, a contact portal route) nothing is stamped and cost stays visible: those paths
  either never serve a person or strip cost themselves (portal: `_PORTAL_HIDDEN_COST`).
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

COST_VIEW_PERM = "products.cost.view"

#: Value written over a masked History value (old and new), so the entry still says which field
#: changed and who changed it, never to what.
HIDDEN = "hidden"

#: Audit `old_values` / `new_values` keys that carry cost, supplier price, the supplier behind a
#: cost, or margin. Masked at every depth for a reader without the permission.
COST_AUDIT_KEYS: tuple[str, ...] = (
    "cost_price",
    "unit_cost",
    "last_purchase_cost",
    "last_cost",
    "supplier_price",
    "supplier_name",
    "margin",
    "margin_percent",
    "markup_pct",
)

_COST_HIDDEN: ContextVar[bool] = ContextVar("cost_hidden", default=False)


def can_view_cost(db: Session, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    from app.services.user_service import UserPermissionService

    return UserPermissionService(db).check_user_has_permission(str(user_id), COST_VIEW_PERM)


def holds_cost_view(db: Session, current_user: Optional[dict]) -> bool:
    """For a request's `current_user`: on an identity read (a key naming a staff member) BOTH the
    staff member and the key's act-as user must hold it (`user_service.gate_user_ids`), so naming
    a stronger user gains nothing."""
    if not current_user or not current_user.get("id"):
        return False
    from app.services.user_service import holds_permission

    return holds_permission(db, current_user, COST_VIEW_PERM)


def stamp_cost_visibility(db: Session, user: Optional[dict]) -> None:
    """Called by the staff auth dependencies with the EFFECTIVE user (after impersonation)."""
    _COST_HIDDEN.set(not holds_cost_view(db, user))


def cost_hidden() -> bool:
    return _COST_HIDDEN.get()


def cost_for_reader(value: Any) -> Any:
    """A response schema's `field_serializer` body for a cost field: null unless this request's
    user holds the permission."""
    return None if cost_hidden() else value


def require_cost_view(user_dep):
    """Route dependency: the caller (resolved by `user_dep`) must hold `products.cost.view`."""
    from app.database import get_db

    def _require(current_user: dict = Depends(user_dep), db: Session = Depends(get_db)) -> dict:
        if not holds_cost_view(db, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {COST_VIEW_PERM}",
            )
        return current_user

    return _require


def _mask(values: Any, masked: set[str]) -> Any:
    if isinstance(values, dict):
        out = {}
        for key, val in values.items():
            if key in COST_AUDIT_KEYS:
                out[key] = HIDDEN
                masked.add(key)
            else:
                out[key] = _mask(val, masked)
        return out
    if isinstance(values, list):
        return [_mask(v, masked) for v in values]
    return values


def mask_audit_values(old: Any, new: Any) -> tuple[Any, Any, list[str]]:
    """`old_values` / `new_values` with every cost key's value replaced by `HIDDEN`, plus the
    sorted names of the keys that were masked (so the reader can say "Cost price changed")."""
    masked: set[str] = set()
    m_old = _mask(old, masked)
    m_new = _mask(new, masked)
    return m_old, m_new, sorted(masked)
