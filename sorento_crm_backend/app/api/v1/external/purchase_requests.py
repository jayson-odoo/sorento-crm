"""External API for purchase requests / sponsorship forms."""
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PurchaseRequestExternalCreate, PurchaseRequestExternalResponse
from app.services.procurement_service import PurchaseRequestService

router = APIRouter()


@router.post("/", response_model=PurchaseRequestExternalResponse)
def create_purchase_request(
    payload: Union[PurchaseRequestExternalCreate, List[PurchaseRequestExternalCreate]] = Body(...),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Create a purchase request or sponsorship form from external payload.
    Accepts either a single object or an array (e.g. from Respond/webhook); the first item is processed.
    respond_inbox_url is built from contact_id and space_id (same as stock inquiry and complaint).
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
        return PurchaseRequestExternalResponse(
            id=header.id,
            request_type=header.request_type,
            date=header.request_date,
            customer_name=header.customer_name,
            project_title=header.project_title,
            purpose=header.purpose,
            expected_delivery_date=header.expected_delivery_date,
            expected_po_date=expected_po_value,
            products=first.products,
            requested_by=header.requested_by,
            requested_at=header.requested_at,
            already_existed=False,
            message=None,
            respond_inbox_url=getattr(header, "respond_inbox_url", None),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
