"""System settings API routes."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.orm import Session
from typing import Literal, Optional
from pydantic import BaseModel, Field
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.product import UnitOfMeasure
from app.models.user import SystemSetting, User, UserRole
from app.services.error_handler import handle_internal_error
from app.services.signin_background import resolve_signin_background_url

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
    import_job_rows_retention_days: Optional[int] = Field(None, ge=1, le=3650)
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_secure: Optional[bool] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None  # update-only; never returned in GET
    smtp_from: Optional[str] = None
    default_product_supplier_id: Optional[str] = None
    default_product_standard_lead_time_days: Optional[int] = Field(None, ge=0, le=10950)
    #: The unit a product gets when the source states none. `null` clears it back to the
    #: built-in `EA` fallback; an unknown id is a 400 rather than a silent fallback the
    #: operator would only discover through an import that quietly did something else.
    default_uom_id: Optional[str] = None
    # Takeover cooldown window in seconds (0 = instant). Cap at 1 hour.
    takeover_cooldown_seconds: Optional[int] = Field(None, ge=0, le=3600)
    # Project registration clash bars (AC-C5). Bounded to (0, 1] because a trigram
    # score is a ratio, and 0 would make every project clash with every other.
    project_clash_surface_threshold: Optional[float] = Field(None, gt=0, le=1)
    project_clash_block_threshold: Optional[float] = Field(None, gt=0, le=1)
    # Global default grace window for form-SLA actions. 0 = nothing defers, which is
    # what ships; a stage may override it (form_sla_configs.grace_seconds).
    form_sla_grace_seconds: Optional[int] = Field(None, ge=0, le=600)
    # The two deferred-action windows (D16). `ge=1`, not `ge=0`: zero would apply a
    # delete with no way back, which is the confirmation dialog's failure mode wearing
    # the new model's clothes. Both must appear here AND in the GET dict below.
    deferred_delete_seconds: Optional[int] = Field(None, ge=1, le=600)
    deferred_action_seconds: Optional[int] = Field(None, ge=1, le=600)
    n8n_attachment_webhook_url: Optional[str] = None
    n8n_crm_chat_outbound_webhook_url: Optional[str] = None
    n8n_stock_inquiry_revise_webhook_url: Optional[str] = None
    n8n_close_convo_webhook_url: Optional[str] = None
    purchase_request_default_approver_user_id: Optional[str] = None
    sponsorship_form_default_approver_user_id: Optional[str] = None
    # AI assistant trace (M2) retention + payload caps.
    ai_trace_ttl_days: Optional[int] = Field(None, ge=1, le=3650)
    ai_trace_error_ttl_days: Optional[int] = Field(None, ge=1, le=3650)
    ai_trace_max_payload_bytes: Optional[int] = Field(None, ge=512, le=1048576)
    ai_assistant_role_split_enabled: Optional[bool] = None
    # Form handling-lock (PLAN-form-handling-lock): the source_entity_types the lock is
    # enabled for. Stored as CSV; accepted/returned as a list. Empty = off everywhere.
    handling_lock_enabled_types: Optional[list[str]] = None
    # System-health observability (digest + watchdog alerts).
    health_digest_enabled: Optional[bool] = None
    health_alerts_enabled: Optional[bool] = None
    health_notify_role_ids: Optional[list[str]] = None
    health_notify_user_ids: Optional[list[str]] = None
    health_integration_fail_threshold: Optional[int] = Field(None, ge=1, le=100000)
    health_audit_volume_floor: Optional[int] = Field(None, ge=0, le=1000000)
    # WhatsApp round-trip latency SLA (S4). Must appear in BOTH this schema and
    # the GET dict below - inheriting the column is not enough, the GET builds a
    # manual dict and silently drops anything not listed there.
    chat_latency_p99_target_seconds: Optional[int] = Field(None, ge=1, le=3600)
    chat_latency_percentile: Optional[int] = Field(None, ge=1, le=99)
    chat_latency_ceiling_multiplier: Optional[int] = Field(None, ge=1, le=100)
    chat_latency_no_reply_minutes: Optional[int] = Field(None, ge=1, le=1440)
    chat_latency_min_sample: Optional[int] = Field(None, ge=1, le=100000)
    # Portal submission revisions: global kill switch + fallback cap. Per-type
    # overrides live in portal_revision_configs. Same rule as the latency block above -
    # must appear here AND in the GET dict.
    portal_revisions_enabled: Optional[bool] = None
    portal_max_revisions: Optional[int] = Field(None, ge=0, le=50)
    # SCM front planning: the admin plan-grain policy (plan 5.1, AC-F01). A Literal, so
    # anything but the two grains is a 422 before it can reach the column. Same rule as
    # the blocks above - it must appear HERE and in the GET dict, because both are manual.
    plan_grain: Optional[Literal["product", "location"]] = None
    # Chatbot media endpoint (PLAN-chatbot-media-endpoint section 2.4). Same rule
    # again - every one of these must ALSO appear in the GET dict below.
    #
    # The two wait bounds are enforced HERE, not only in the settings form: a
    # number that only the UI refuses is not a constraint. The 110 ceiling exists
    # so even a maximally misconfigured pair cannot exceed the dispatcher's 120
    # second lock TTL, and the >= relationship between them is checked below so a
    # job that outlives the sync wait still finishes rather than being killed
    # mid-flight.
    media_image_monthly_limit: Optional[int] = Field(None, ge=0, le=100000)
    media_voice_monthly_limit: Optional[int] = Field(None, ge=0, le=100000)
    media_voice_max_seconds: Optional[int] = Field(None, ge=1, le=3600)
    media_burst_limit: Optional[int] = Field(None, ge=1, le=1000)
    media_burst_window_seconds: Optional[int] = Field(None, ge=1, le=3600)
    media_warn_threshold_percent: Optional[int] = Field(None, ge=1, le=100)
    media_image_provider: Optional[str] = None
    media_image_model: Optional[str] = None
    media_image_degraded_model: Optional[str] = None
    media_transcribe_model: Optional[str] = None
    # Voice's own degraded tier. NULL means the voice quota is a hard refusal
    # rather than a degrade - image was measured and is seeded, voice was not.
    media_voice_degraded_model: Optional[str] = None
    # Three modes and no others: `language_strategy()` builds a different request
    # shape per mode and silently treats anything unrecognised as `pinned`, so a
    # typo would look like the setting had been ignored rather than refused.
    media_language_mode: Optional[str] = Field(None, pattern="^(pinned|hints|auto)$")
    media_language_pinned: Optional[str] = None
    media_language_hints: Optional[str] = None
    media_sync_wait_seconds: Optional[int] = Field(None, ge=5, le=90)
    media_extraction_timeout_seconds: Optional[int] = Field(None, ge=5, le=110)
    media_max_entities: Optional[int] = Field(None, ge=1, le=100)
    chatbot_stock_denial_enabled: Optional[bool] = None
    # Which chatbot lanes the CRM may FINISH, by `branch_kind`. `[]` (the default) means
    # none, and every turn delegates to n8n exactly as today. Validated as a list of
    # strings only: an unknown branch kind is the ENGINE's problem to ignore-and-warn, not
    # this endpoint's to reject, because the vocabulary grows slice by slice and a settings
    # form that rejects tomorrow's lane name is a support ticket.
    chatbot_completed_lanes: Optional[list[str]] = None


class SmtpTestResult(BaseModel):
    success: bool
    message: str


class AppConfigResponse(BaseModel):
    """The non-sensitive slice of the system settings singleton.

    Six fields, and the model is what makes "and nothing else" enforceable:
    anything not declared here is dropped on serialization rather than leaking
    because a dict builder grew a line. Do NOT extend it - see the route below.
    """

    currency: Optional[str] = None
    currency_format: Optional[str] = None
    purchase_request_default_approver_user_id: Optional[str] = None
    purchase_request_default_approver_email: Optional[str] = None
    sponsorship_form_default_approver_user_id: Optional[str] = None
    sponsorship_form_default_approver_email: Optional[str] = None


@router.get("/")
async def get_settings(
    current_user: dict = Depends(require_permission("user_management.settings.view")),
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
        # The default unit's CODE as well as its id: the settings screen may not render a
        # bare UUID, and the id alone would leave it with nothing to show until the units
        # master happens to be loaded beside it.
        default_uom_id = getattr(settings, "default_uom_id", None) if settings else None
        default_uom = (
            db.query(UnitOfMeasure).filter(UnitOfMeasure.id == default_uom_id).first()
            if default_uom_id
            else None
        )
        return {
            "settings": {
                "id": settings.id if settings else None,
                "name": settings.name if settings else None,
                "logo": settings.logo if settings else None,
                # A new settings column reaches the FE only if it is on this manual dict.
                # Signed here, not raw: the stored value is a non-signed CDN URL and the
                # settings screen renders it straight into an <img>.
                "signin_background": resolve_signin_background_url(settings),
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
                # A new settings column reaches the FE only if it is on this manual dict
                # AND on `SystemSettingUpdate` above.
                "default_uom_id": default_uom_id,
                "default_uom_code": default_uom.uom_code if default_uom else None,
                "form_sla_grace_seconds": (
                    getattr(settings, "form_sla_grace_seconds", 0) if settings else 0
                ),
                # The two deferred-action windows (D16). Defaults stated here as well as
                # on the column, so a settings row that predates the migration still
                # renders 10 and 5 rather than an empty field.
                "deferred_delete_seconds": (
                    getattr(settings, "deferred_delete_seconds", 10) or 10
                    if settings
                    else 10
                ),
                "deferred_action_seconds": (
                    getattr(settings, "deferred_action_seconds", 5) or 5
                    if settings
                    else 5
                ),
                "takeover_cooldown_seconds": (
                    getattr(settings, "takeover_cooldown_seconds", 60) if settings else None
                ),
                # float() because the column is NUMERIC, which psycopg2 hands back as
                # Decimal -- and Decimal is not JSON-serialisable.
                "project_clash_surface_threshold": (
                    float(getattr(settings, "project_clash_surface_threshold", 0.55) or 0.55)
                    if settings
                    else None
                ),
                "project_clash_block_threshold": (
                    float(getattr(settings, "project_clash_block_threshold", 0.70) or 0.70)
                    if settings
                    else None
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
                "n8n_close_convo_webhook_url": getattr(
                    settings, "n8n_close_convo_webhook_url", None
                )
                if settings
                else None,
                "complaint_do_delivered_notify_tiers": getattr(
                    settings, "complaint_do_delivered_notify_tiers", "1,2"
                )
                if settings
                else None,
                "import_job_rows_retention_days": getattr(
                    settings, "import_job_rows_retention_days", 90
                )
                if settings
                else None,
                "ai_trace_ttl_days": getattr(settings, "ai_trace_ttl_days", 30) if settings else None,
                "ai_trace_error_ttl_days": getattr(settings, "ai_trace_error_ttl_days", 90) if settings else None,
                "ai_trace_max_payload_bytes": getattr(settings, "ai_trace_max_payload_bytes", 16384) if settings else None,
                "ai_assistant_role_split_enabled": getattr(settings, "ai_assistant_role_split_enabled", False) if settings else None,
                "handling_lock_enabled_types": (
                    [
                        t.strip()
                        for t in str(getattr(settings, "handling_lock_enabled_types", "") or "").split(",")
                        if t.strip()
                    ]
                    if settings
                    else []
                ),
                "health_digest_enabled": getattr(settings, "health_digest_enabled", True) if settings else None,
                "health_alerts_enabled": getattr(settings, "health_alerts_enabled", True) if settings else None,
                "health_notify_role_ids": getattr(settings, "health_notify_role_ids", None) if settings else None,
                "health_notify_user_ids": getattr(settings, "health_notify_user_ids", None) if settings else None,
                "health_integration_fail_threshold": getattr(settings, "health_integration_fail_threshold", 10) if settings else None,
                "health_audit_volume_floor": getattr(settings, "health_audit_volume_floor", 0) if settings else None,
                "chat_latency_p99_target_seconds": getattr(settings, "chat_latency_p99_target_seconds", 10) if settings else None,
                "chat_latency_percentile": getattr(settings, "chat_latency_percentile", 99) if settings else None,
                "chat_latency_ceiling_multiplier": getattr(settings, "chat_latency_ceiling_multiplier", 3) if settings else None,
                "chat_latency_no_reply_minutes": getattr(settings, "chat_latency_no_reply_minutes", 5) if settings else None,
                "chat_latency_min_sample": getattr(settings, "chat_latency_min_sample", 30) if settings else None,
                "portal_revisions_enabled": getattr(settings, "portal_revisions_enabled", True) if settings else None,
                "portal_max_revisions": getattr(settings, "portal_max_revisions", 2) if settings else None,
                # Rollout default (plan 5.1): a row saved before the column existed reads
                # as Product rather than as "no policy", which has no meaning here.
                "plan_grain": (getattr(settings, "plan_grain", None) or "product") if settings else None,
                # Chatbot media. NULL is meaningful for the three model columns:
                # provider/model inherit the AIAssistantConfig row, and a NULL
                # degraded model means the monthly quota is a hard stop rather
                # than an accepted-but-degraded read.
                "media_image_monthly_limit": getattr(settings, "media_image_monthly_limit", 50) if settings else None,
                "media_voice_monthly_limit": getattr(settings, "media_voice_monthly_limit", 100) if settings else None,
                "media_voice_max_seconds": getattr(settings, "media_voice_max_seconds", 120) if settings else None,
                "media_burst_limit": getattr(settings, "media_burst_limit", 5) if settings else None,
                "media_burst_window_seconds": getattr(settings, "media_burst_window_seconds", 60) if settings else None,
                "media_warn_threshold_percent": getattr(settings, "media_warn_threshold_percent", 80) if settings else None,
                "media_image_provider": getattr(settings, "media_image_provider", None) if settings else None,
                "media_image_model": getattr(settings, "media_image_model", None) if settings else None,
                "media_image_degraded_model": getattr(settings, "media_image_degraded_model", None) if settings else None,
                "media_transcribe_model": getattr(settings, "media_transcribe_model", "whisper-1") if settings else None,
                "media_voice_degraded_model": getattr(settings, "media_voice_degraded_model", None) if settings else None,
                "media_language_mode": getattr(settings, "media_language_mode", "pinned") if settings else None,
                "media_language_pinned": getattr(settings, "media_language_pinned", "en") if settings else None,
                "media_language_hints": getattr(settings, "media_language_hints", "en,ms,zh") if settings else None,
                "media_sync_wait_seconds": getattr(settings, "media_sync_wait_seconds", 30) if settings else None,
                "media_extraction_timeout_seconds": getattr(settings, "media_extraction_timeout_seconds", 45) if settings else None,
                "media_max_entities": getattr(settings, "media_max_entities", 10) if settings else None,
                "chatbot_stock_denial_enabled": getattr(settings, "chatbot_stock_denial_enabled", False) if settings else None,
                "chatbot_completed_lanes": getattr(settings, "chatbot_completed_lanes", None) or [] if settings else None,
                "smtp": smtp_response,
            } if settings else None,
            "roles": [{"id": r.id, "name": r.name} for r in roles]
        }
    except Exception as e:
        raise handle_internal_error(str(e))


# Declared immediately after `GET /` and ahead of every other GET in this file so a
# path-parameter route added later (e.g. `/{section}`) cannot shadow this static path.
@router.get("/app-config", response_model=AppConfigResponse)
async def get_app_config(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The narrow, non-sensitive projection of system settings that any authenticated
    user may read.

    It exists because `GET /settings/` is gated on `user_management.settings.view` -
    that is where the full blob lives, and it stays there - while three consumers on
    screens outside user-management legitimately need a handful of harmless fields:
    `useCurrencyFormat` (currency format string), `use-excel-accept`, and
    `PurchaseRequestDetail` (the configured default approver it falls back to when
    sending an approval link, which is why the two approver EMAILS are here).

    NOTHING SENSITIVE MAY EVER BE ADDED TO THIS ROUTE. Not SMTP config, not the n8n
    webhook URLs (they are bearer-capability URLs), not the tenant roles list, not
    `health_notify_role_ids` / `health_notify_user_ids`, not the AI trace config. If a
    caller needs any of those, it needs `user_management.settings.view` and the full
    blob - do not widen this projection. The approver NAMES are deliberately absent
    too: nothing reads them.
    """
    try:
        settings = db.query(SystemSetting).first()
        pr_uid = getattr(settings, "purchase_request_default_approver_user_id", None) if settings else None
        sf_uid = getattr(settings, "sponsorship_form_default_approver_user_id", None) if settings else None
        user_pr = db.query(User).filter(User.id == pr_uid).first() if pr_uid else None
        user_sf = db.query(User).filter(User.id == sf_uid).first() if sf_uid else None
        return AppConfigResponse(
            currency=settings.currency if settings else None,
            currency_format=settings.currency_format if settings else None,
            purchase_request_default_approver_user_id=pr_uid,
            purchase_request_default_approver_email=user_pr.email if user_pr else None,
            sponsorship_form_default_approver_user_id=sf_uid,
            sponsorship_form_default_approver_email=user_sf.email if user_sf else None,
        )
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

    # The default unit a UOM-less product takes. Validated where it is WRITTEN, the same as
    # the default supplier above: an id that resolves to nothing would otherwise be
    # discovered by an import quietly falling back to `EA` on nine thousand rows.
    if "default_uom_id" in update_data:
        uid = update_data["default_uom_id"]
        if uid is not None and str(uid).strip():
            uid_clean = str(uid).strip()
            if db.query(UnitOfMeasure.id).filter(UnitOfMeasure.id == uid_clean).first() is None:
                raise HTTPException(status_code=400, detail="Default unit of measure not found")
            update_data["default_uom_id"] = uid_clean
        else:
            update_data["default_uom_id"] = None

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

    # Handling-lock enabled types: accept a list, persist as a de-duped CSV of valid
    # form types (mirrors the singleton gotcha - the generic setattr loop below would
    # otherwise write a Python list into a Text column).
    if "handling_lock_enabled_types" in update_data:
        from app.services.form_sla_service import FORM_SLA_TYPES

        raw = update_data["handling_lock_enabled_types"] or []
        seen: list[str] = []
        for t in raw:
            t = str(t).strip()
            if t in FORM_SLA_TYPES and t not in seen:
                seen.append(t)
        update_data["handling_lock_enabled_types"] = ",".join(seen)

    # A block bar below the surface bar means every surfaced candidate also blocks,
    # which silently turns the two-bar design back into one aggressive bar. Reject it
    # here rather than let an admin discover it through false blocks in the field.
    if "project_clash_surface_threshold" in update_data or (
        "project_clash_block_threshold" in update_data
    ):
        effective_surface = float(
            update_data.get(
                "project_clash_surface_threshold",
                getattr(settings, "project_clash_surface_threshold", 0.55) or 0.55,
            )
        )
        effective_block = float(
            update_data.get(
                "project_clash_block_threshold",
                getattr(settings, "project_clash_block_threshold", 0.70) or 0.70,
            )
        )
        if effective_block < effective_surface:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The project clash blocking threshold must be at or above the "
                    "surfacing threshold."
                ),
            )

    # Chatbot media: a model id belongs to the provider it was picked from, so a
    # provider change that does not also name the models clears them rather than
    # sending the previous provider's ids to the new provider. The FE does the
    # same clear-on-change; this is the backstop for a direct PUT, where a kept
    # stale degraded model would fail only for over-quota contacts - the hardest
    # failure to attribute.
    if "media_image_provider" in update_data:
        new_provider = (update_data["media_image_provider"] or "").strip() or None
        update_data["media_image_provider"] = new_provider
        old_provider = (
            getattr(settings, "media_image_provider", None) or ""
        ).strip() or None
        if new_provider != old_provider:
            for model_col in ("media_image_model", "media_image_degraded_model"):
                if model_col not in update_data:
                    update_data[model_col] = None

    # Chatbot media: the pair has to hold together, and the per-field ge/le on
    # SystemSettingUpdate cannot express a relationship between two fields. An
    # extraction ceiling below the synchronous wait would kill a job mid-flight at
    # exactly the moment the endpoint degrades to `pending` - the result would be
    # neither returned inline nor retrievable afterwards (PLAN 2.4 / UAC S3-01d).
    if "media_sync_wait_seconds" in update_data or "media_extraction_timeout_seconds" in update_data:
        wait = update_data.get(
            "media_sync_wait_seconds", getattr(settings, "media_sync_wait_seconds", 30)
        )
        ceiling = update_data.get(
            "media_extraction_timeout_seconds",
            getattr(settings, "media_extraction_timeout_seconds", 45),
        )
        if wait is not None and ceiling is not None and int(ceiling) < int(wait):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Extraction timeout must be at least the synchronous wait, "
                    "or a job that outlives the wait is killed instead of degrading."
                ),
            )

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


# ---------------------------------------------------------------------------
# Sign-in background
# ---------------------------------------------------------------------------
#
# Its own multipart endpoint rather than a field on `PUT /general`, for two reasons:
# the general update is a JSON body and threading a file through it would turn every
# save of an unrelated field into a multipart request, and the write path here has to
# be the ONLY way this column is set. `signin_background` is deliberately absent from
# `SystemSettingUpdate` above: it holds a URL that the sign-in page loads for anonymous
# visitors, so letting a client PUT an arbitrary string into it would let an admin point
# the login screen at somebody else's server. The bytes come to us or they do not go in.
#
# Read side: the column is on the GET dict (resolved to a signed URL, see above) and on
# `GET /api/v1/public/branding` for the unauthenticated sign-in page.

SIGNIN_BACKGROUND_MAX_BYTES = 5 * 1024 * 1024
SIGNIN_BACKGROUND_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
SIGNIN_BACKGROUND_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class SigninBackgroundResponse(BaseModel):
    """The URL the settings screen previews, or null once it has been removed."""

    signin_background_url: Optional[str] = None


@router.post(
    "/signin-background",
    status_code=status.HTTP_200_OK,
    response_model=SigninBackgroundResponse,
)
async def update_signin_background(
    request: Request,
    current_user: dict = Depends(require_permission("user_management.settings.edit")),
    db: Session = Depends(get_db),
):
    """Upload or clear the photograph behind the sign-in card.

    Multipart form:
      backgroundAction = "save" | "remove"
      backgroundFile   = the image, required when saving

    Removing clears the columns and the sign-in page falls back to its designed default
    wash, which is why there is no confirmation of a "nothing set" state to worry about:
    the screen it returns to is a finished one.
    """
    import re
    import uuid as _uuid
    from pathlib import Path

    settings = db.query(SystemSetting).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    form = await request.form()
    raw_action = form.get("backgroundAction")
    action = (raw_action if isinstance(raw_action, str) else str(raw_action or "")).strip()

    if action == "remove":
        # Shared with the deferred `signin_background.remove` record action, so the two
        # paths cannot drift about which columns "removed" means.
        from app.services.signin_background import clear_signin_background

        clear_signin_background(db)
        return SigninBackgroundResponse(signin_background_url=None)

    if action != "save":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="backgroundAction must be 'save' or 'remove'",
        )

    upload = form.get("backgroundFile")
    # A multipart field can arrive as a plain string, so narrow before reading it rather
    # than trusting that a field named `backgroundFile` carried a file.
    # request.form() hands back starlette's UploadFile, of which fastapi's is a
    # subclass - so the check must be against the starlette class or it never passes.
    filename = upload.filename if isinstance(upload, StarletteUploadFile) else None
    if not isinstance(upload, StarletteUploadFile) or not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An image is required when saving a sign-in background",
        )

    content = await upload.read()
    if len(content) > SIGNIN_BACKGROUND_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The sign-in background must be 5MB or smaller",
        )

    content_type = getattr(upload, "content_type", None) or "application/octet-stream"
    if content_type not in SIGNIN_BACKGROUND_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPG, PNG or WebP images are allowed",
        )

    original = Path(filename).name or "signin-background.jpg"
    stem = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(original).stem)[:80] or "signin-background"
    ext = (Path(original).suffix[:10] or ".jpg").lower()
    if ext not in SIGNIN_BACKGROUND_EXTENSIONS:
        ext = ".jpg"
    storage_path = f"branding/signin-background/{_uuid.uuid4().hex}_{stem}{ext}"

    try:
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
        )

        provider = default_provider()
        key, _ = get_backend(provider).upload_file(content, storage_path, content_type=content_type)
        setattr(settings, "signin_background", cdn_base_url(provider, key))
        setattr(settings, "signin_background_storage_provider", provider)
    except ValueError as cfg_err:
        logger.error("Sign-in background upload configuration error: %s", cfg_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured. Contact an administrator.",
        )
    except Exception as upload_err:  # noqa: BLE001
        logger.exception("Sign-in background upload failed: %s", upload_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload the sign-in background. Please try again.",
        )

    db.commit()
    return SigninBackgroundResponse(
        signin_background_url=resolve_signin_background_url(settings)
    )
