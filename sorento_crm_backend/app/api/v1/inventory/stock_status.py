"""GET /api/v1/inventory/stock-status - AutoCount's Available Stock Status for one item.

Read-only. Served to every screen that embeds the panel, so any one of their read permissions
opens it: order inquiries and the fulfilment board (`projects.projects.view`), the loading plan
(`scm.reorder.run`) and the SCM dashboard (`scm.dashboard.view`); the stand-alone Inventory page
is shown to the same three.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission_with_api_key
from app.services.field_access import CLEARANCE_PERMISSION
from app.services.stock_status_service import stock_status
from app.services.user_service import UserPermissionService

router = APIRouter()

#: Security review S1: NOT `inventory.stock.view`. That slug opens stock balances only, and
#: this read returns SO customers and PO/SPO suppliers, which it never granted (an integration
#: holding only the stock-balance read could otherwise collect every open order's customer).
#: These three already open those documents on their own screens.
READ_PERMISSIONS = [
    "projects.projects.view",
    "scm.reorder.run",
    "scm.dashboard.view",
]


def _may_see_eta_delay(db: Session, user: dict) -> bool:
    """Owner ruling 17 Oct (security S-C): the delayed ETA is a clearance field, shown only to
    holders of `procurement.packing_lists.view_clearance`. Fails closed."""
    user_id = (user or {}).get("id")
    if not user_id:
        return False
    try:
        return bool(UserPermissionService(db).check_user_has_permission(str(user_id), CLEARANCE_PERMISSION))
    except Exception:  # noqa: BLE001 - fail closed, as field_access does
        return False


@router.get("")
def get_stock_status(
    product_id: str = Query(..., description="The product (uuid)."),
    so_due_by: Optional[date] = Query(
        None,
        description="Count SO due on or before this date only; undated SO always counts.",
    ),
    _user: dict = Depends(require_any_permission_with_api_key(READ_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    """Every location holding the item, its SO / PO / SPO documents and incoming packing lists."""
    return stock_status(db, product_id, so_due_by, eta_delay_visible=_may_see_eta_delay(db, _user))
