"""Stock transfers (`PLAN-scm-cs-planning-uat.md` section E, AC-E1 to AC-E6).

Reads on `inventory.stock_transfers.view`, every transition on
`inventory.stock_transfers.edit`. Under the inventory router, so the module guard the
captain asked the page to live behind (`Inventory management -> Stock transfers`) is the
one it already has.

**Nothing here creates or deletes a transfer.** A transfer exists because a supply
confirmation implied it (`project_supply_service._write_transfers`), and it leaves by
being moved or cancelled - which is why there is no POST and no DELETE.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.stock_transfer import (
    BulkApproveRequest,
    BulkApproveResult,
    CancelTransferRequest,
    MarkMovedRequest,
    StockTransferOut,
)
from app.services.error_handler import handle_internal_error
from app.services.stock_transfer_service import StockTransferService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "inventory.stock_transfers.view"
EDIT = "inventory.stock_transfers.edit"

#: A closed set for the same reason the order-inquiry worklist's is: a filter nothing can
#: equal reads on screen as "no work to do" when the truth is "that is not a state".
TransferSort = Literal[
    "transfer_no",
    "state",
    "kind",
    "qty",
    "item_code",
    "from_location",
    "to_location",
    "so_number",
    "proposed_at",
]


@router.get("", response_model=ListResponse[StockTransferOut])
@router.get("/", response_model=ListResponse[StockTransferOut], include_in_schema=False)
def list_stock_transfers(
    query: Optional[str] = Query(
        None,
        description=(
            "One box. Matches the transfer number, the AutoCount reference, the item code "
            "or product name, the sales-order number, either warehouse code and the "
            "customer."
        ),
    ),
    state: Optional[Literal["proposed", "approved", "moved", "cancelled"]] = Query(None),
    kind: Optional[Literal["own_group", "pool", "borrow"]] = Query(None),
    from_warehouse_id: Optional[str] = Query(None),
    to_warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    sales_order_id: Optional[str] = Query(
        None, description="The CORE sales order, for the SO detail page's Transfers tab."
    ),
    project_sales_order_id: Optional[str] = Query(None),
    sales_agent_id: Optional[str] = Query(
        None, description="For the sales-agent detail page's Transfers tab."
    ),
    sort: Optional[TransferSort] = Query(None, description="Defaults to proposed_at."),
    direction: Optional[Literal["asc", "desc"]] = Query("desc", alias="dir"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Every movement a supply decision has asked for, newest proposal first."""
    try:
        for value, resource in (
            (from_warehouse_id, "Warehouse"),
            (to_warehouse_id, "Warehouse"),
            (product_id, "Product"),
            (sales_order_id, "Sales order"),
            (project_sales_order_id, "Sales order"),
            (sales_agent_id, "Sales agent"),
        ):
            if value:
                validate_uuid_path(value, resource=resource)
        rows, total = StockTransferService(db).list_transfers(
            page=page,
            limit=limit,
            sort=sort,
            direction=direction or "desc",
            query=query,
            state=state,
            kind=kind,
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            product_id=product_id,
            sales_order_id=sales_order_id,
            project_sales_order_id=project_sales_order_id,
            sales_agent_id=sales_agent_id,
        )
        return {
            "data": rows,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/bulk-approve", response_model=BulkApproveResult)
def bulk_approve_stock_transfers(
    body: BulkApproveRequest,
    user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    """Approve everything ticked. Declared BEFORE `/{transfer_id}` so the static path is
    not swallowed by the parameterised one (the SLA route-shadowing lesson)."""
    try:
        result = StockTransferService(db).bulk_approve(
            body.ids, actor_user_id=user["id"]
        )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{transfer_id}", response_model=StockTransferOut)
def get_stock_transfer(
    transfer_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(transfer_id, resource="Stock transfer")
        return StockTransferService(db).get(transfer_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{transfer_id}/approve", response_model=StockTransferOut)
def approve_stock_transfer(
    transfer_id: str,
    user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    """A person says move this. Nothing has physically moved yet."""
    try:
        validate_uuid_path(transfer_id, resource="Stock transfer")
        result = StockTransferService(db).approve(transfer_id, actor_user_id=user["id"])
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{transfer_id}/mark-moved", response_model=StockTransferOut)
def mark_stock_transfer_moved(
    transfer_id: str,
    body: MarkMovedRequest,
    user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    """A person keyed the movement into AutoCount and wrote its document number here.

    Terminal: our stock figures follow on the next stock upload, and nothing closes this
    row on their behalf (the ruling).
    """
    try:
        validate_uuid_path(transfer_id, resource="Stock transfer")
        result = StockTransferService(db).mark_moved(
            transfer_id, autocount_ref=body.autocount_ref, actor_user_id=user["id"]
        )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{transfer_id}/cancel", response_model=StockTransferOut)
def cancel_stock_transfer(
    transfer_id: str,
    body: CancelTransferRequest,
    user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    """Called off, with the reason on the row. A moved transfer cannot be cancelled."""
    try:
        validate_uuid_path(transfer_id, resource="Stock transfer")
        result = StockTransferService(db).cancel(
            transfer_id, reason=body.reason, actor_user_id=user["id"]
        )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
