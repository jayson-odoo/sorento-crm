"""SQLAlchemy models."""
# Import all models here so Alembic can discover them
# Import order matters for relationships - import base models first
from app.models.user import User, UserRole, UserRoleAssignment, UserPermission, UserRolePermission, SystemLog, SystemSetting, UserQuickAccess, UserListColumnConfig
from app.models.auth import VerificationToken
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure
from app.models.order import Order, OrderStatus, Customer, CustomerContact, OrderLine, SalesOrder, SalesOrderLine
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.procurement import Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine, StockInquiry, PurchaseRequestHeader, PurchaseRequestLine, PurchaseOrder, PurchaseOrderLine
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct, CampaignType, MarketingCampaign
from app.models.forms import Form, FormSection, FormField, FormVersion, FormSubmission
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.models.complaints import Complaint, ComplaintAttachment, ComplaintManualAttachment, ComplaintFulfilmentOrder
from app.models.complaint_master_data import ComplaintRootCause, ComplaintResolution
from app.models.entity_attachment import EntityAttachmentLink
from app.models.attachment_field_link import AttachmentFieldLink
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEventLog, FormSLAConfig
from app.models.resources import Attachment, AttachmentType
from app.models.access import AccessAgent, ContactAgentAccess, ContactAccessType, RespondContact, respond_contact_access_types, MarketSegment, respond_contact_market_segments, team_member_market_segments
from app.models.respond_workspace import RespondWorkspace
from app.models.respond_template import (
    RespondChannel,
    RespondMessageTemplate,
    RespondTemplateDefault,
)
from app.models.workflow_stage import WorkflowStage
from app.models.entity_conversation import EntityConversationMessage
from app.models.integration import Integration, IntegrationApiKey, IntegrationLog
from app.models.integration_reference import IntegrationReference
from app.models.import_log import ImportLog
from app.models.calendar import PublicHoliday, WorkCalendarConfig
from app.models.job import ImportJob, ImportJobRow
from app.models.download import UserDownload, DownloadStatus
from app.models.audit import AuditLog
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun
from app.models.health_alert_state import HealthAlertState
from app.models.numbering import DocumentNumberingRule
from app.models.app_modules import AppModuleCatalog, AppModuleBundle, TenantModule, ModuleInstallEvent
from app.models.list_query_metadata import ListQueryResource, ListQueryField
from app.models.embeddings import EmbeddingQueue, EmbeddingDocument, EmbeddingChunk
from app.models.ai_assistant import (
    AIAssistantConfig,
    AIAssistantConversation,
    AIAssistantMessage,
    AIAssistantGovernanceEvent,
    AIAssistantUsageLog,
    AIAssistantWishlistCluster,
    AIAssistantUnansweredQuery,
)
from app.models.ai_prompt import AIPromptVersion, AIPromptLabel
from app.models.chat_history import ChatHistory
from app.models.conversation_frame import ConversationFrame
from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding
from app.models.portal import PortalToken, PortalOtpCode
from app.models.user_session import UserSession
from app.models.activities import ActivityEvent, InternalNote, ActivityMention
from app.models.tickets import Ticket, TicketWatcher, TicketRespondContactLink
from app.models.email_template import EmailTemplate
from app.models.automation import Automation, AutomationRun
from app.models.impersonation import ImpersonationSession, ContactImpersonationSession
from app.models.email_outbox import EmailOutbox, EmailEventConfig
from app.models.scm import (
    ReorderPolicy,
    ItemClassification,
    AbcXyzPolicy,
    SupplierScoringPolicy,
    SupplierPerformance,
    PurchasingBudget,
    ReorderRun,
    ReorderRecommendation,
    RecommendationOverride,
    OverrideReason,
    ReasonActionMap,
    CashRankingPolicy,
    DemandNatureMap,
    DemandStat,
    MarketResearchTopic,
    MarketSignal,
    ScmAnalyticsRun,
    MarketResearchRun,
)

__all__ = [
    "User",
    "UserRole",
    "UserRoleAssignment",
    "UserPermission",
    "UserRolePermission",
    "SystemLog",
    "SystemSetting",
    "UserQuickAccess",
    "UserListColumnConfig",
    "Product",
    "ProductCategory",
    "Brand",
    "UnitOfMeasure",
    "Order",
    "OrderStatus",
    "Customer",
    "CustomerContact",
    "OrderLine",
    "SalesOrder",
    "SalesOrderLine",
    "Warehouse",
    "StorageZone",
    "Stock",
    "StockBatch",
    "StockLedger",
    "Supplier",
    "ProductSupplier",
    "InboundShipment",
    "InboundShipmentLine",
    "SPOAllocation",
    "PickingHeader",
    "PickingLine",
    "StockInquiry",
    "PurchaseRequestHeader",
    "PurchaseRequestLine",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "Promotion",
    "PromotionGroup",
    "PromotionProduct",
    "CampaignType",
    "MarketingCampaign",
    "Form",
    "FormSection",
    "FormField",
    "FormVersion",
    "FormSubmission",
    "WorkflowFormDefinition",
    "WorkflowFormVersion",
    "WorkflowSubmission",
    "WorkflowSubmissionLine",
    "WorkflowSubmissionTransitionLog",
    "Complaint",
    "ComplaintAttachment",
    "ComplaintManualAttachment",
    "ComplaintFulfilmentOrder",
    "EntityAttachmentLink",
    "AttachmentFieldLink",
    "SLAPolicy",
    "SLAPolicyTier",
    "ConversationSLATracking",
    "ConversationSLAEventLog",
    "FormSLAConfig",
    "Attachment",
    "AttachmentType",
    "AccessAgent",
    "ContactAgentAccess",
    "ContactAccessType",
    "RespondContact",
    "respond_contact_access_types",
    "RespondWorkspace",
    "RespondChannel",
    "RespondMessageTemplate",
    "RespondTemplateDefault",
    "WorkflowStage",
    "EntityConversationMessage",
    "IntegrationLog",
    "ImportLog",
    "ImportJob",
    "ImportJobRow",
    "UserDownload",
    "DownloadStatus",
    "VerificationToken",
    "PublicHoliday",
    "WorkCalendarConfig",
    "AuditLog",
    "Notification",
    "NotificationDelivery",
    "PushSubscription",
    "ScheduledTask",
    "ScheduledTaskRun",
    "DocumentNumberingRule",
    "AppModuleCatalog",
    "AppModuleBundle",
    "TenantModule",
    "ModuleInstallEvent",
    "ListQueryResource",
    "ListQueryField",
    "EmbeddingQueue",
    "EmbeddingDocument",
    "EmbeddingChunk",
    "AIAssistantConfig",
    "AIAssistantConversation",
    "AIAssistantMessage",
    "AIAssistantGovernanceEvent",
    "AIAssistantUsageLog",
    "AIAssistantWishlistCluster",
    "AIAssistantUnansweredQuery",
    "AIPromptVersion",
    "AIPromptLabel",
    "ChatHistory",
    "ConversationFrame",
    "LookupSet",
    "LookupOption",
    "LookupOptionKeyword",
    "LookupBinding",
    "PortalToken",
    "PortalOtpCode",
    "UserSession",
    "ActivityEvent",
    "InternalNote",
    "ActivityMention",
    "Ticket",
    "TicketWatcher",
    "TicketRespondContactLink",
    "EmailTemplate",
    "Automation",
    "AutomationRun",
    "ImpersonationSession",
    "ContactImpersonationSession",
    "EmailOutbox",
    "EmailEventConfig",
    "ReorderPolicy",
    "ItemClassification",
    "AbcXyzPolicy",
    "SupplierScoringPolicy",
    "SupplierPerformance",
    "PurchasingBudget",
    "ReorderRun",
    "ReorderRecommendation",
    "RecommendationOverride",
    "OverrideReason",
    "ReasonActionMap",
    "CashRankingPolicy",
    "DemandNatureMap",
    "DemandStat",
    "MarketResearchTopic",
    "MarketSignal",
    "ScmAnalyticsRun",
    "MarketResearchRun",
]

# Auto-discovery: import models.py from each app/modules/<key>/ so Alembic + SQLAlchemy
# see them. Safe with shimmed legacy paths above (re-imports are no-ops).
from app.modules.runtime.discovery import discover_module_models  # noqa: E402
discover_module_models()
