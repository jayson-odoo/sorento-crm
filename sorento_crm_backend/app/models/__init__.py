"""SQLAlchemy models."""
# Import all models here so Alembic can discover them
# Import order matters for relationships - import base models first
from app.models.user import User, UserRole, UserRoleAssignment, UserPermission, UserRolePermission, SystemLog, SystemSetting, UserQuickAccess
from app.models.auth import VerificationToken
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure
from app.models.order import Order, OrderStatus, Customer, OrderLine
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.procurement import Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine, StockInquiry, PurchaseRequestHeader, PurchaseRequestLine
from app.models.marketing import Promotion, PromotionProduct, CampaignType, MarketingCampaign
from app.models.forms import Form, FormSection, FormField, FormVersion, FormSubmission
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.models.complaints import Complaint, ComplaintAttachment, ComplaintManualAttachment
from app.models.entity_attachment import EntityAttachmentLink
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEventLog
from app.models.resources import Attachment, AttachmentType
from app.models.access import AccessAgent, ContactAgentAccess, ContactAccessType, RespondAccessTypeMapping, RespondContact
from app.models.integration import IntegrationLog
from app.models.import_log import ImportLog
from app.models.calendar import PublicHoliday, WorkCalendarConfig
from app.models.job import ImportJob
from app.models.audit import AuditLog
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun
from app.models.numbering import DocumentNumberingRule
from app.models.app_modules import AppModuleCatalog, AppModuleBundle, TenantModule, ModuleInstallEvent
from app.models.list_query_metadata import ListQueryResource, ListQueryField

__all__ = [
    "User",
    "UserRole",
    "UserRoleAssignment",
    "UserPermission",
    "UserRolePermission",
    "SystemLog",
    "SystemSetting",
    "UserQuickAccess",
    "Product",
    "ProductCategory",
    "Brand",
    "UnitOfMeasure",
    "Order",
    "OrderStatus",
    "Customer",
    "OrderLine",
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
    "Promotion",
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
    "EntityAttachmentLink",
    "SLAPolicy",
    "SLAPolicyTier",
    "ConversationSLATracking",
    "ConversationSLAEventLog",
    "Attachment",
    "AttachmentType",
    "AccessAgent",
    "ContactAgentAccess",
    "ContactAccessType",
    "RespondAccessTypeMapping",
    "RespondContact",
    "IntegrationLog",
    "ImportLog",
    "ImportJob",
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
]
