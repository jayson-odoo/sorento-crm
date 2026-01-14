"""SQLAlchemy models."""
# Import all models here so Alembic can discover them
# Import order matters for relationships - import base models first
from app.models.user import User, UserRole, UserPermission, UserRolePermission, SystemLog, SystemSetting
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure
from app.models.order import Order, OrderStatus, Customer
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch
from app.models.procurement import Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine, StockInquiry
from app.models.marketing import Promotion, PromotionProduct, CampaignType, MarketingCampaign
from app.models.forms import Form, FormSection, FormField, FormVersion
from app.models.complaints import Complaint, ComplaintAttachment
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEscalationLog
from app.models.resources import Attachment, AttachmentType
from app.models.access import AccessAgent, ContactAgentAccess

__all__ = [
    "User",
    "UserRole",
    "UserPermission",
    "UserRolePermission",
    "SystemLog",
    "SystemSetting",
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
    "Supplier",
    "ProductSupplier",
    "InboundShipment",
    "InboundShipmentLine",
    "SPOAllocation",
    "PickingHeader",
    "PickingLine",
    "StockInquiry",
    "Promotion",
    "PromotionProduct",
    "CampaignType",
    "MarketingCampaign",
    "Form",
    "FormSection",
    "FormField",
    "FormVersion",
    "Complaint",
    "ComplaintAttachment",
    "SLAPolicy",
    "SLAPolicyTier",
    "ConversationSLATracking",
    "ConversationSLAEscalationLog",
    "Attachment",
    "AttachmentType",
    "AccessAgent",
    "ContactAgentAccess",
]
