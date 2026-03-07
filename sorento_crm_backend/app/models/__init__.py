"""SQLAlchemy models."""
# Import all models here so Alembic can discover them
# Import order matters for relationships - import base models first
from app.models.user import User, UserRole, UserRoleAssignment, UserPermission, UserRolePermission, SystemLog, SystemSetting, UserQuickAccess
from app.models.auth import VerificationToken
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure
from app.models.order import Order, OrderStatus, Customer
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.procurement import Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine, StockInquiry, PurchaseRequestHeader, PurchaseRequestLine
from app.models.marketing import Promotion, PromotionProduct, CampaignType, MarketingCampaign
from app.models.forms import Form, FormSection, FormField, FormVersion, FormSubmission
from app.models.complaints import Complaint, ComplaintAttachment, ComplaintManualAttachment
from app.models.entity_attachment import EntityAttachmentLink
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEventLog
from app.models.resources import Attachment, AttachmentType
from app.models.access import AccessAgent, ContactAgentAccess
from app.models.integration import IntegrationLog
from app.models.import_log import ImportLog
from app.models.calendar import PublicHoliday, WorkCalendarConfig
from app.models.job import ImportJob
from app.models.audit import AuditLog
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun

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
]
