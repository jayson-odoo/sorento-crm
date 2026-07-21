"""Marketing management models."""
import enum
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

# Forward references for relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.resources import Attachment


class CampaignStatus(str, enum.Enum):
    # Values are LOWERCASE to match the DB CHECK constraint
    # `marketing_campaigns_status_check` (planning/active/completed/cancelled).
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Promotion(Base):
    __tablename__ = "promotions"
    __audit_track__ = True  # who changed what (Sub-plan D Tier-2)

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    access_levels = Column(JSONB, nullable=False, server_default='["dealer","end_user"]')
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    promotion_groups = relationship(
        "PromotionGroup",
        back_populates="promotion",
        cascade="all, delete-orphan",
    )
    promotion_products = relationship(
        "PromotionProduct",
        back_populates="promotion",
        cascade="all, delete-orphan",
    )
    promotion_attachments = relationship(
        "PromotionAttachment",
        back_populates="promotion",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        Index("ix_promotions_is_active", "is_active"),
        Index("ix_promotions_start_date", "start_date"),
        Index("ix_promotions_end_date", "end_date"),
        Index("ix_promotions_access_levels", "access_levels", postgresql_using="gin"),
    )


class PromotionGroup(Base):
    """Bundle / FOC group: optional multiple buy-N-get-M free tier combinations (foc_tiers)."""

    __tablename__ = "promotion_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id = Column(UUID(as_uuid=False), ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    foc_tiers = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    promotion = relationship("Promotion", back_populates="promotion_groups")
    promotion_products = relationship(
        "PromotionProduct",
        back_populates="promotion_group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_promotion_groups_promotion_id", "promotion_id"),
    )


class PromotionProduct(Base):
    __tablename__ = "promotion_products"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    promotion_id = Column(UUID(as_uuid=False), ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)
    promotion_group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("promotion_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    promo_selling_price = Column(Numeric(12, 2), nullable=True)
    discount_amount = Column(Numeric(12, 2), nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    dealer_discount_percent = Column(Numeric(8, 6), nullable=True)
    dealer_cost = Column(Numeric(12, 2), nullable=True)
    list_to_dealer_margin_amount = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    promotion = relationship("Promotion", back_populates="promotion_products")
    promotion_group = relationship("PromotionGroup", back_populates="promotion_products")
    product = relationship("Product", back_populates="promotion_products")
    
    __table_args__ = (
        Index("ix_promotion_products_promotion_id", "promotion_id"),
        Index("ix_promotion_products_product_id", "product_id"),
        Index("ix_promotion_products_promotion_group_id", "promotion_group_id"),
        Index("uq_promotion_products_group_product", "promotion_group_id", "product_id", unique=True),
    )


class PromotionAttachment(Base):
    __tablename__ = "promotion_attachments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    promotion_id = Column(UUID(as_uuid=False), ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    promotion = relationship("Promotion", back_populates="promotion_attachments")
    attachment = relationship("Attachment", foreign_keys=[attachment_id])
    
    __table_args__ = (
        Index("ix_promotion_attachments_promotion_id", "promotion_id"),
        Index("ix_promotion_attachments_attachment_id", "attachment_id"),
        Index("uq_promotion_attachment", "promotion_id", "attachment_id", unique=True),
    )


class CampaignType(Base):
    __tablename__ = "campaign_types"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    type_code = Column(String(50), unique=True, nullable=False)
    type_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    campaigns = relationship("MarketingCampaign", back_populates="campaign_type")


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_code = Column(String(50), unique=True, nullable=False)
    campaign_name = Column(String(255), nullable=False)
    campaign_type_id = Column(UUID(as_uuid=False), ForeignKey("campaign_types.id"), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    budget = Column(Numeric(15, 2), nullable=True)
    target_audience = Column(Text, nullable=True)
    status = Column(String, default=CampaignStatus.PLANNING.value, nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    campaign_type = relationship("CampaignType", back_populates="campaigns")
    
    __table_args__ = (
        Index("ix_marketing_campaigns_campaign_type_id", "campaign_type_id"),
        Index("ix_marketing_campaigns_status", "status"),
        Index("ix_marketing_campaigns_start_date", "start_date"),
    )
