"""External API for purchase requests / sponsorship forms."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PurchaseRequestExternalCreate, PurchaseRequestExternalResponse
from app.services.procurement_service import PurchaseRequestService

router = APIRouter()


@router.post("/", response_model=PurchaseRequestExternalResponse)
def create_purchase_request(
    payload: PurchaseRequestExternalCreate,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Create a purchase request or sponsorship form from external payload."""
    try:
        service = PurchaseRequestService(db)
        header = service.create_external_request(payload)
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
            products=payload.products,
            requested_by=header.requested_by,
            requested_at=header.requested_at,
            already_existed=False,
            message=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
