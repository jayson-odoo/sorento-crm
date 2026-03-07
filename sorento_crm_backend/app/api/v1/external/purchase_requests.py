"""External API for purchase requests / sponsorship forms.

Agent prompt: Ask the user for request_type first (purchase_request or sponsorship_form).
Then ask for the relevant fields:
- Purchase request: date, customer_name, project_title, purpose (showroom/mock up/others:__),
  expected_delivery_date, expected_po_date, line items (item_code, quantity, remark),
  requested_by, requested_at.
- Sponsorship form: date, customer_name, delivery_address, project_title, total_project_value,
  sponsor_subject (showroom/mockup/others:__), expected_delivery_date (date of delivery),
  line items (item_code, quantity, unit_price, total), requested_by, requested_at.
"""
from decimal import Decimal
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PurchaseRequestExternalCreate, PurchaseRequestExternalResponse, PurchaseRequestExternalLine
from app.services.procurement_service import PurchaseRequestService

router = APIRouter()


def _line_to_external(line) -> PurchaseRequestExternalLine:
    return PurchaseRequestExternalLine(
        item_code=getattr(line, "item_code", None),
        quantity=getattr(line, "quantity", None),
        remark=getattr(line, "remark", None),
        unit_price=getattr(line, "unit_price", None),
        total=getattr(line, "total", None),
    )


def _grand_total(header) -> Optional[Decimal]:
    if getattr(header, "request_type", None) != "sponsorship_form" or not header.lines:
        return None
    total = Decimal("0")
    for line in header.lines:
        t = getattr(line, "total", None)
        if t is not None:
            total += Decimal(str(t))
        else:
            q, u = getattr(line, "quantity", None), getattr(line, "unit_price", None)
            if q is not None and u is not None:
                total += Decimal(str(q)) * Decimal(str(u))
    return total


@router.post("/", response_model=PurchaseRequestExternalResponse)
def create_purchase_request(
    payload: Union[PurchaseRequestExternalCreate, List[PurchaseRequestExternalCreate]] = Body(...),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Create a purchase request or sponsorship form from external payload.
    Get request_type from the user first, then the fields relevant to that type.
    Accepts either a single object or an array (e.g. from Respond/webhook); the first item is processed.
    """
    try:
        if isinstance(payload, list):
            if not payload:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payload must be a non-empty list or a single object")
            first = payload[0]
        else:
            first = payload
        service = PurchaseRequestService(db)
        header = service.create_external_request(first)
        expected_po_value = header.expected_po_date_text or header.expected_po_date
        products = [_line_to_external(line) for line in (header.lines or [])]
        return PurchaseRequestExternalResponse(
            id=header.id,
            request_type=header.request_type,
            date=header.request_date,
            customer_name=header.customer_name,
            project_title=header.project_title,
            purpose=header.purpose,
            delivery_address=getattr(header, "delivery_address", None),
            total_project_value=getattr(header, "total_project_value", None),
            sponsor_subject=getattr(header, "sponsor_subject", None),
            expected_delivery_date=header.expected_delivery_date,
            expected_po_date=expected_po_value,
            products=products,
            requested_by=header.requested_by,
            requested_at=header.requested_at,
            grand_total=_grand_total(header),
            already_existed=False,
            message=None,
            respond_inbox_url=getattr(header, "respond_inbox_url", None),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
