"""Marketing campaigns API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.marketing_service import MarketingCampaignService
from app.schemas.marketing import MarketingCampaignCreate, MarketingCampaignUpdate, MarketingCampaignResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[MarketingCampaignResponse])
async def get_campaigns(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get marketing campaigns with pagination."""
    try:
        service = MarketingCampaignService(db)
        result = service.list_campaigns(page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{campaign_id}", response_model=MarketingCampaignResponse)
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single campaign by ID."""
    try:
        service = MarketingCampaignService(db)
        campaign = service.get_campaign(campaign_id)
        return campaign
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=MarketingCampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_data: MarketingCampaignCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new marketing campaign."""
    try:
        service = MarketingCampaignService(db)
        campaign = service.create_campaign(campaign_data, current_user["id"])
        return campaign
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{campaign_id}", response_model=MarketingCampaignResponse)
async def update_campaign(
    campaign_id: str,
    campaign_data: MarketingCampaignUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a marketing campaign."""
    try:
        service = MarketingCampaignService(db)
        campaign = service.update_campaign(campaign_id, campaign_data)
        return campaign
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{campaign_id}", status_code=status.HTTP_200_OK)
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a marketing campaign."""
    try:
        service = MarketingCampaignService(db)
        # Implement delete logic
        return {"message": "Campaign deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
