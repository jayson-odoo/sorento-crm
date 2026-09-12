"""Purchase orders placed but not yet received (A5, chatbot-growth-r1)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.api.v1.order_management.orders import _parse_flex_date  # shared flexible date parser
from app.services.error_handler import AppException, handle_internal_error
from app.services.purchase_order_service import (
    PO_GROUP_BY_AXES,
    group_rows,
    purchase_orders_placed_rows,
    purchase_orders_placed_summary,
)
from app.services.uuid_list_param import parse_uuid_list

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/placed")
def get_purchase_orders_placed(
    limit: int = Query(50, ge=1, le=500),
    product_ids: Optional[list[str]] = Query(
        None,
        description="Filter by canonical product UUIDs (csv / JSON / repeated).",
    ),
    expected_date_from: Optional[str] = Query(
        None, description="Filter by expected date from (inclusive). Line expected_date, else header's."
    ),
    expected_date_to: Optional[str] = Query(
        None, description="Filter by expected date to (inclusive)."
    ),
    group_by: Optional[str] = Query(
        None, description="Group rows into headed sections: product | supplier | date."
    ),
    include_summary: bool = Query(
        False,
        description="true = also return `summary`: po_placed_qty/po_placed_count over the filtered lines.",
    ),
    sort: Optional[str] = Query("expected_date"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Open purchase-order lines: `qty_ordered - qty_received > 0`, `line_status='open'`.

    Never nets against incoming SPO receipts (`spo_allocations.po_line_id` is
    NULL on every row) - "PO placed, not yet shipped" is the whole answer this
    route gives; A6 answers "last in" separately.
    """
    if group_by is not None and group_by not in PO_GROUP_BY_AXES:
        raise AppException(
            422,
            f"Unknown group_by value '{group_by}'",
            detail=f"allowed: {', '.join(sorted(PO_GROUP_BY_AXES))}",
            code="invalid_group_by",
        )
    try:
        resolved_product_ids = parse_uuid_list(product_ids, param_name="product_ids")
        _from = _parse_flex_date(expected_date_from)
        _to = _parse_flex_date(expected_date_to, end_of_day=True)
        rows = purchase_orders_placed_rows(
            db,
            product_ids=resolved_product_ids,
            expected_date_from=_from.date() if _from else None,
            expected_date_to=_to.date() if _to else None,
            sort=sort or "expected_date",
            dir=dir or "asc",
            limit=limit,
        )
        payload: dict = {
            "data": rows,
            "pagination": {"total": len(rows), "page": 1, "limit": len(rows)},
            "empty": not rows,
        }
        if group_by:
            payload["groups"] = group_rows(rows, group_by=group_by)
        if include_summary:
            payload["summary"] = {
                "scope": "filter",
                "row_count": len(rows),
                # The SAME filters the rows took, the date window included (review,
                # should-fix 6): a summary that counts more than the list under it is
                # worse than no summary.
                **purchase_orders_placed_summary(
                    db,
                    product_ids=resolved_product_ids,
                    expected_date_from=expected_date_from,
                    expected_date_to=expected_date_to,
                ),
            }
        return JSONResponse(content=jsonable_encoder(payload))
    except AppException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))
