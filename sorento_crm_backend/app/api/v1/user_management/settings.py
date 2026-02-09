"""System settings API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import SystemSetting, UserRole
from app.services.error_handler import handle_internal_error

router = APIRouter()


class SystemSettingUpdate(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    active: Optional[bool] = None
    address: Optional[str] = None
    website_url: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    currency_format: Optional[str] = None
    social_facebook: Optional[str] = None
    social_twitter: Optional[str] = None
    social_instagram: Optional[str] = None
    social_linkedin: Optional[str] = None
    social_pinterest: Optional[str] = None
    social_youtube: Optional[str] = None
    notify_stock_email: Optional[bool] = None
    notify_stock_web: Optional[bool] = None
    notify_stock_threshold: Optional[str] = None
    notify_stock_role_ids: Optional[list[str]] = None
    notify_new_order_email: Optional[bool] = None
    notify_new_order_web: Optional[bool] = None
    notify_new_order_role_ids: Optional[list[str]] = None
    notify_order_status_update_email: Optional[bool] = None
    notify_order_status_update_web: Optional[bool] = None
    notify_order_status_update_role_ids: Optional[list[str]] = None
    notify_payment_failure_email: Optional[bool] = None
    notify_payment_failure_web: Optional[bool] = None
    notify_payment_failure_role_ids: Optional[list[str]] = None
    notify_system_error_failure_email: Optional[bool] = None
    notify_system_error_web: Optional[bool] = None
    notify_system_error_role_ids: Optional[list[str]] = None


@router.get("/")
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system settings and roles."""
    try:
        settings = db.query(SystemSetting).first()
        roles = db.query(UserRole).order_by(UserRole.name.asc()).all()
        
        return {
            "settings": {
                "id": settings.id if settings else None,
                "name": settings.name if settings else None,
                "logo": settings.logo if settings else None,
                "active": settings.active if settings else None,
                "address": settings.address if settings else None,
                "website_url": settings.website_url if settings else None,
                "support_email": settings.support_email if settings else None,
                "support_phone": settings.support_phone if settings else None,
                "language": settings.language if settings else None,
                "timezone": settings.timezone if settings else None,
                "currency": settings.currency if settings else None,
                "currency_format": settings.currency_format if settings else None,
            } if settings else None,
            "roles": [{"id": r.id, "name": r.name} for r in roles]
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/general", status_code=status.HTTP_200_OK)
async def update_general_settings(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update general system settings."""
    try:
        settings = db.query(SystemSetting).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        update_data = settings_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(settings, key, value)
        
        db.commit()
        db.refresh(settings)
        return {"message": "General settings updated successfully", "data": settings}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/social", status_code=status.HTTP_200_OK)
async def update_social_settings(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update social media settings."""
    try:
        settings = db.query(SystemSetting).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        social_fields = [
            "social_facebook", "social_twitter", "social_instagram",
            "social_linkedin", "social_pinterest", "social_youtube"
        ]
        update_data = {k: v for k, v in settings_data.model_dump(exclude_unset=True).items() if k in social_fields}
        
        for key, value in update_data.items():
            setattr(settings, key, value)
        
        db.commit()
        db.refresh(settings)
        return {"message": "Social settings updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/notifications", status_code=status.HTTP_200_OK)
async def update_notification_settings(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update notification settings."""
    try:
        settings = db.query(SystemSetting).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        notification_fields = [
            "notify_stock_email", "notify_stock_web", "notify_stock_threshold", "notify_stock_role_ids",
            "notify_new_order_email", "notify_new_order_web", "notify_new_order_role_ids",
            "notify_order_status_update_email", "notify_order_status_update_web", "notify_order_status_update_role_ids",
            "notify_payment_failure_email", "notify_payment_failure_web", "notify_payment_failure_role_ids",
            "notify_system_error_failure_email", "notify_system_error_web", "notify_system_error_role_ids"
        ]
        update_data = {k: v for k, v in settings_data.model_dump(exclude_unset=True).items() if k in notification_fields}
        
        for key, value in update_data.items():
            setattr(settings, key, value)
        
        db.commit()
        db.refresh(settings)
        return {"message": "Notification settings updated successfully", "data": settings}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
