"""System settings API routes."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import SystemSetting, User, UserRole
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

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
    complaint_do_delivered_notify_tiers: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_secure: Optional[bool] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None  # update-only; never returned in GET
    smtp_from: Optional[str] = None
    default_product_supplier_id: Optional[str] = None
    default_product_standard_lead_time_days: Optional[int] = Field(None, ge=0, le=10950)
    # Takeover cooldown window in seconds (0 = instant). Cap at 1 hour.
    takeover_cooldown_seconds: Optional[int] = Field(None, ge=0, le=3600)
    n8n_attachment_webhook_url: Optional[str] = None
    n8n_crm_chat_outbound_webhook_url: Optional[str] = None
    n8n_stock_inquiry_revise_webhook_url: Optional[str] = None
    purchase_request_default_approver_user_id: Optional[str] = None
    sponsorship_form_default_approver_user_id: Optional[str] = None
    # AI assistant trace (M2) retention + payload caps.
    ai_trace_ttl_days: Optional[int] = Field(None, ge=1, le=3650)
    ai_trace_error_ttl_days: Optional[int] = Field(None, ge=1, le=3650)
    ai_trace_max_payload_bytes: Optional[int] = Field(None, ge=512, le=1048576)
    ai_assistant_role_split_enabled: Optional[bool] = None


class SmtpTestResult(BaseModel):
    success: bool
    message: str


@router.get("/")
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system settings and roles."""
    try:
        settings = db.query(SystemSetting).first()
        roles = db.query(UserRole).order_by(UserRole.name.asc()).all()
        
        smtp_response = None
        if settings:
            smtp_response = {
                "smtp_host": settings.smtp_host,
                "smtp_port": settings.smtp_port,
                "smtp_secure": settings.smtp_secure,
                "smtp_username": settings.smtp_username,
                "smtp_from": settings.smtp_from,
                "smtp_password": None,  # never return raw password
            }
        pr_uid = getattr(settings, "purchase_request_default_approver_user_id", None) if settings else None
        sf_uid = getattr(settings, "sponsorship_form_default_approver_user_id", None) if settings else None
        user_pr = db.query(User).filter(User.id == pr_uid).first() if pr_uid else None
        user_sf = db.query(User).filter(User.id == sf_uid).first() if sf_uid else None
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
                "default_product_supplier_id": settings.default_product_supplier_id if settings else None,
                "default_product_standard_lead_time_days": (
                    settings.default_product_standard_lead_time_days if settings else None
                ),
                "takeover_cooldown_seconds": (
                    getattr(settings, "takeover_cooldown_seconds", 60) if settings else None
                ),
                "purchase_request_default_approver_user_id": pr_uid,
                "purchase_request_default_approver_name": user_pr.name if user_pr else None,
                "purchase_request_default_approver_email": user_pr.email if user_pr else None,
                "sponsorship_form_default_approver_user_id": sf_uid,
                "sponsorship_form_default_approver_name": user_sf.name if user_sf else None,
                "sponsorship_form_default_approver_email": user_sf.email if user_sf else None,
                "n8n_attachment_webhook_url": getattr(settings, "n8n_attachment_webhook_url", None)
                if settings
                else None,
                "n8n_crm_chat_outbound_webhook_url": getattr(
                    settings, "n8n_crm_chat_outbound_webhook_url", None
                )
                if settings
                else None,
                "n8n_stock_inquiry_revise_webhook_url": getattr(
                    settings, "n8n_stock_inquiry_revise_webhook_url", None
                )
                if settings
                else None,
                "complaint_do_delivered_notify_tiers": getattr(
                    settings, "complaint_do_delivered_notify_tiers", "1,2"
                )
                if settings
                else None,
                "ai_trace_ttl_days": getattr(settings, "ai_trace_ttl_days", 30) if settings else None,
                "ai_trace_error_ttl_days": getattr(settings, "ai_trace_error_ttl_days", 90) if settings else None,
                "ai_trace_max_payload_bytes": getattr(settings, "ai_trace_max_payload_bytes", 16384) if settings else None,
                "ai_assistant_role_split_enabled": getattr(settings, "ai_assistant_role_split_enabled", False) if settings else None,
                "smtp": smtp_response,
            } if settings else None,
            "roles": [{"id": r.id, "name": r.name} for r in roles]
        }
    except Exception as e:
        raise handle_internal_error(str(e))


def _update_general_settings_impl(settings_data: SystemSettingUpdate, db: Session):
    """Shared implementation for PUT/POST general settings."""
    from app.models.procurement import Supplier

    settings = db.query(SystemSetting).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    update_data = settings_data.model_dump(exclude_unset=True)

    if "default_product_supplier_id" in update_data:
        sid = update_data["default_product_supplier_id"]
        if sid is not None and str(sid).strip():
            sid_clean = str(sid).strip()
            found = db.query(Supplier.id).filter(Supplier.id == sid_clean).first()
            if not found:
                raise HTTPException(status_code=400, detail="Default product supplier not found")
            update_data["default_product_supplier_id"] = sid_clean
        else:
            update_data["default_product_supplier_id"] = None

    for col in (
        "purchase_request_default_approver_user_id",
        "sponsorship_form_default_approver_user_id",
    ):
        if col in update_data:
            uid = update_data[col]
            if uid is not None and str(uid).strip():
                uid_clean = str(uid).strip()
                if db.query(User.id).filter(User.id == uid_clean).first() is None:
                    raise HTTPException(status_code=400, detail="Default approver user not found")
                update_data[col] = uid_clean
            else:
                update_data[col] = None

    for key, value in update_data.items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return {"message": "General settings updated successfully", "data": settings}


@router.put("/general", status_code=status.HTTP_200_OK)
async def update_general_settings(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update general system settings."""
    try:
        return _update_general_settings_impl(settings_data, db)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/general", status_code=status.HTTP_200_OK)
async def update_general_settings_post(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update general system settings (POST allowed for frontend form submit)."""
    try:
        return _update_general_settings_impl(settings_data, db)
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


@router.put("/smtp", status_code=status.HTTP_200_OK)
async def update_smtp_settings(
    settings_data: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update SMTP settings. Password is update-only (omit to keep existing)."""
    try:
        settings = db.query(SystemSetting).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        smtp_fields = ["smtp_host", "smtp_port", "smtp_secure", "smtp_username", "smtp_password", "smtp_from"]
        update_data = {k: v for k, v in settings_data.model_dump(exclude_unset=True).items() if k in smtp_fields}
        for key, value in update_data.items():
            if key == "smtp_secure":
                setattr(settings, key, bool(value) if value is not None else True)
            elif key in ("smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_from"):
                setattr(settings, key, value if value and str(value).strip() else None)
            else:
                setattr(settings, key, value)
        db.commit()
        db.refresh(settings)
        return {"message": "SMTP settings updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to save SMTP settings: %s", e)
        raise handle_internal_error(str(e))


@router.post("/smtp/test", status_code=status.HTTP_200_OK, response_model=SmtpTestResult)
async def test_smtp_connection(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test SMTP connection using current system settings (or env fallback)."""
    try:
        from app.services.notification_email import test_smtp_connection as do_test
        settings = db.query(SystemSetting).first()
        success, message = do_test(settings)
        return SmtpTestResult(success=success, message=message)
    except Exception as e:
        raise handle_internal_error(str(e))
