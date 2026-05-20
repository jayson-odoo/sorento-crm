"""Promotion attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Path
from sqlalchemy.orm import Session
from typing import Any, Optional

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.marketing_service import PromotionAttachmentService
from app.services.uuid_list_param import parse_uuid_list
from app.schemas.marketing import PromotionAttachmentCreate, PromotionAttachmentUpdate, PromotionAttachmentResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


def _promotion_attachment_to_response(pa: Any) -> dict:
    """Serialize promotion attachment without mutating stored attachment file_path."""
    data = PromotionAttachmentResponse.model_validate(pa).model_dump()
    return data


@router.get("/", response_model=ListResponse[PromotionAttachmentResponse])
async def get_promotion_attachments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    entities: Optional[list[str]] = Query(
        None,
        description="DEPRECATED — free-text entity bag. Prefer `promotion_ids` / `attachment_ids`.",
    ),
    promotion_ids: Optional[list[str]] = Query(
        None,
        description="Canonical promotion UUIDs (csv/JSON/repeated).",
    ),
    attachment_ids: Optional[list[str]] = Query(
        None,
        description="Canonical attachment UUIDs (csv/JSON/repeated).",
    ),
    promotion_id: Optional[str] = Query(
        None,
        description="Legacy: promotion UUID.",
    ),
    query: Optional[str] = Query(
        None,
        description="Free-text search across promotion header, product code/name, promotion group name, and attachment metadata.",
    ),
    attachment_id: Optional[str] = Query(None),
    access_levels: Optional[list[str]] = Query(
        None,
        description="Optional access-level codes filter (intersection with parent promotion.access_levels).",
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get promotion attachments with pagination and filtering. Optional access_levels intersection filter."""
    try:
        from app.services.entity_filter_helpers import normalize_list_query_param
        access_levels = normalize_list_query_param(access_levels)
        contact_codes = list(access_levels) if access_levels else None
        service = PromotionAttachmentService(db)
        from app.services.entity_filter_helpers import normalize_entities_query_param
        result = service.list_promotion_attachments(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            promotion_id=promotion_id,
            attachment_id=attachment_id,
            promotion_ids=parse_uuid_list(promotion_ids, param_name="promotion_ids"),
            attachment_ids=parse_uuid_list(attachment_ids, param_name="attachment_ids"),
            query=query,
            contact_access_codes=contact_codes,
            entities=normalize_entities_query_param(entities),
        )
        result["data"] = [_promotion_attachment_to_response(pa) for pa in result["data"]]
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{promotion_attachment_id}", response_model=PromotionAttachmentResponse)
async def get_promotion_attachment(
    promotion_attachment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single promotion attachment by ID."""
    try:
        service = PromotionAttachmentService(db)
        promotion_attachment = service.get_promotion_attachment(promotion_attachment_id)
        return _promotion_attachment_to_response(promotion_attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=PromotionAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_promotion_attachment(
    promotion_attachment_data: PromotionAttachmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new promotion attachment relationship."""
    try:
        service = PromotionAttachmentService(db)
        created_by = str(current_user.get("id", "")) if current_user else None
        promotion_attachment = service.create_promotion_attachment(promotion_attachment_data, created_by=created_by)
        return _promotion_attachment_to_response(promotion_attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{promotion_attachment_id}", response_model=PromotionAttachmentResponse)
async def update_promotion_attachment(
    promotion_attachment_id: str,
    promotion_attachment_data: PromotionAttachmentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a promotion attachment relationship."""
    try:
        service = PromotionAttachmentService(db)
        promotion_attachment = service.update_promotion_attachment(promotion_attachment_id, promotion_attachment_data)
        return _promotion_attachment_to_response(promotion_attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{promotion_attachment_id}", status_code=status.HTTP_200_OK)
async def delete_promotion_attachment(
    promotion_attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a promotion attachment relationship."""
    try:
        service = PromotionAttachmentService(db)
        service.delete_promotion_attachment(promotion_attachment_id)
        return {"message": "Promotion attachment deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/promotion/{promotion_id}")
async def get_promotion_attachments_by_promotion(
    promotion_id: str = Path(
        ...,
        description="Promotion UUID.",
    ),
    access_levels: Optional[list[str]] = Query(
        None,
        description="Optional access-level codes filter (intersection with parent promotion.access_levels).",
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get all attachments for a specific promotion. Optional access_levels intersection filter."""
    try:
        from app.services.entity_filter_helpers import normalize_list_query_param
        access_levels = normalize_list_query_param(access_levels)
        contact_codes = list(access_levels) if access_levels else None
        service = PromotionAttachmentService(db)
        promotion_attachments = service.get_promotion_attachments_by_promotion(
            promotion_id,
            contact_access_codes=contact_codes,
        )
        return [_promotion_attachment_to_response(pa) for pa in promotion_attachments]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
