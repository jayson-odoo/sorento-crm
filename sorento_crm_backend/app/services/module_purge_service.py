"""
Delete domain data when uninstalling a module with purge_data=true.

Only modules with an explicit handler are supported. Others raise a clear error so
operators can uninstall without purge (removes tenant binding only) or clean up manually.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.complaints import Complaint, ComplaintAttachment, ComplaintManualAttachment
from app.models.forms import Form, FormField, FormSection, FormSubmission, FormVersion
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.models.marketing import CampaignType, MarketingCampaign, Promotion, PromotionAttachment, PromotionProduct
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.procurement import ViewToken
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking, SLAPolicy, SLAPolicyTier

logger = logging.getLogger(__name__)

PurgeFn = Callable[[Session], Dict[str, int]]


def _count_deleted(db: Session, model, label: str) -> int:
    n = db.query(model).delete(synchronize_session=False)
    logger.info("Purge %s: deleted %s rows", label, n)
    return n


def purge_notifications(db: Session) -> Dict[str, int]:
    """In-app notifications and push subscriptions."""
    out: Dict[str, int] = {}
    out["notification_deliveries"] = _count_deleted(db, NotificationDelivery, "notification_deliveries")
    out["notifications"] = _count_deleted(db, Notification, "notifications")
    out["push_subscriptions"] = _count_deleted(db, PushSubscription, "push_subscriptions")
    return out


def purge_audit(db: Session) -> Dict[str, int]:
    return {"audit_logs": _count_deleted(db, AuditLog, "audit_logs")}


def purge_sla(db: Session) -> Dict[str, int]:
    """SLA policies, tracking, and event logs."""
    out: Dict[str, int] = {}
    out["conversation_sla_event_log"] = _count_deleted(db, ConversationSLAEventLog, "conversation_sla_event_log")
    out["conversation_sla_tracking"] = _count_deleted(db, ConversationSLATracking, "conversation_sla_tracking")
    out["sla_policy_tiers"] = _count_deleted(db, SLAPolicyTier, "sla_policy_tiers")
    out["sla_policies"] = _count_deleted(db, SLAPolicy, "sla_policies")
    return out


def purge_forms(db: Session) -> Dict[str, int]:
    """Forms and submissions (does not delete attachment files in storage)."""
    out: Dict[str, int] = {}
    out["form_submissions"] = _count_deleted(db, FormSubmission, "form_submissions")
    out["form_versions"] = _count_deleted(db, FormVersion, "form_versions")
    out["form_fields"] = _count_deleted(db, FormField, "form_fields")
    out["form_sections"] = _count_deleted(db, FormSection, "form_sections")
    out["forms"] = _count_deleted(db, Form, "forms")
    return out


def purge_marketing(db: Session) -> Dict[str, int]:
    out: Dict[str, int] = {}
    out["marketing_campaigns"] = _count_deleted(db, MarketingCampaign, "marketing_campaigns")
    out["promotion_attachments"] = _count_deleted(db, PromotionAttachment, "promotion_attachments")
    out["promotion_products"] = _count_deleted(db, PromotionProduct, "promotion_products")
    out["promotions"] = _count_deleted(db, Promotion, "promotions")
    out["campaign_types"] = _count_deleted(db, CampaignType, "campaign_types")
    return out


def purge_complaints(db: Session) -> Dict[str, int]:
    out: Dict[str, int] = {}
    out["complaint_manual_attachments"] = _count_deleted(db, ComplaintManualAttachment, "complaint_manual_attachments")
    out["complaint_attachments"] = _count_deleted(db, ComplaintAttachment, "complaint_attachments")
    out["complaints"] = _count_deleted(db, Complaint, "complaints")
    return out


def purge_public_view_links(db: Session) -> Dict[str, int]:
    return {"view_tokens": _count_deleted(db, ViewToken, "view_tokens")}


def purge_workflow_forms(db: Session) -> Dict[str, int]:
    """Workflow form definitions, versions, submissions, lines, transition logs."""
    out: Dict[str, int] = {}
    out["workflow_submission_transition_logs"] = _count_deleted(
        db, WorkflowSubmissionTransitionLog, "workflow_submission_transition_logs"
    )
    out["workflow_submission_lines"] = _count_deleted(db, WorkflowSubmissionLine, "workflow_submission_lines")
    out["workflow_submissions"] = _count_deleted(db, WorkflowSubmission, "workflow_submissions")
    db.query(WorkflowFormDefinition).update({WorkflowFormDefinition.published_version_id: None}, synchronize_session=False)
    db.commit()
    out["workflow_form_versions"] = _count_deleted(db, WorkflowFormVersion, "workflow_form_versions")
    out["workflow_form_definitions"] = _count_deleted(db, WorkflowFormDefinition, "workflow_form_definitions")
    return out


# Module key -> purge function (must match app_modules_catalog.module_key).
# Table lists shown in App Store uninstall UI: MODULE_PURGE_TABLES in
# sorento_crm_frontend/.../app-store/services/appModulesService.ts — keep in sync.
MODULE_PURGE_HANDLERS: Dict[str, PurgeFn] = {
    "notifications": purge_notifications,
    "audit": purge_audit,
    "sla": purge_sla,
    "forms": purge_forms,
    "marketing": purge_marketing,
    "complaints": purge_complaints,
    "public_view_links": purge_public_view_links,
    "workflow_forms": purge_workflow_forms,
}


def _merge_discovered_handlers() -> None:
    """Merge handlers from app/modules/<key>/purge.py if present (additive)."""
    try:
        from app.modules.runtime.discovery import discover_module_purge_handlers
    except Exception:  # noqa: BLE001
        return
    found = discover_module_purge_handlers()
    for k, fn in found.items():
        MODULE_PURGE_HANDLERS[k] = fn


_merge_discovered_handlers()


def purge_module_data(db: Session, module_key: str) -> Dict[str, int]:
    """
    Delete business data for this module. Caller must enforce dependency / tenant rules.
    Raises ValueError if no handler is registered.
    """
    # Re-merge each call so modules dropped at runtime (Phase 8 upload) are picked up.
    _merge_discovered_handlers()
    fn = MODULE_PURGE_HANDLERS.get(module_key)
    if not fn:
        raise ValueError(
            f"No automated data purge is implemented for module '{module_key}'. "
            "Uninstall without 'Delete data' to remove the module from your tenant only, "
            "or perform a manual database cleanup after export."
        )
    return fn(db)
