"""Marketing service for business logic."""
import re
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, exists
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment, CampaignType, MarketingCampaign
from app.models.product import Product
from app.models.resources import Attachment, AttachmentType
from app.schemas.marketing import (
    PromotionCreate, PromotionUpdate, PromotionProductCreate, PromotionProductUpdate,
    PromotionAttachmentCreate, PromotionAttachmentUpdate,
    CampaignTypeCreate, CampaignTypeUpdate, MarketingCampaignCreate, MarketingCampaignUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_internal_error
from app.services.contact_access_type_service import ContactAccessTypeService


def _product_display_label(db: Session, product_id: str) -> str:
    """Human-readable product label (code and name) for error messages."""
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        return product_id
    code = (p.product_code or "").strip()
    name = (p.product_name or "").strip()
    if code and name:
        return f"{code} — {name}"
    return code or name or product_id


def raise_promotion_product_unique_violation(db: Session, exc: Exception) -> None:
    """
    Turn promotion_products unique constraint failures into 409 with product details.
    Call after session.rollback() when handling IntegrityError from commit/flush.
    """
    if not isinstance(exc, IntegrityError):
        raise exc
    orig = str(getattr(exc, "orig", exc) or exc)
    if "uq_promotion" not in orig.lower() and "promotion_products" not in orig.lower():
        raise handle_internal_error(
            "Could not save promotion product due to a database constraint."
        )
    m = re.search(r"Key \(promotion_id, product_id\)=\([^,]+,\s*([^)]+)\)", orig)
    if not m:
        raise handle_conflict(
            "This product is already linked to this promotion, or the request contains duplicate products."
        )
    product_id = m.group(1).strip()
    label = _product_display_label(db, product_id)
    raise handle_conflict(
        f"Product already on this promotion: {label}. Remove duplicate rows or use one line per product."
    )


class PromotionService:
    """Service for promotion operations."""
    
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _canonical_access_levels(access_levels: Optional[list[str]]) -> tuple[str, ...]:
        """Canonicalize access levels for uniqueness checks (order-insensitive, deduplicated)."""
        if not access_levels:
            return tuple()
        return tuple(sorted({(a or "").strip() for a in access_levels if (a or "").strip()}))

    def _ensure_promo_code_access_levels_unique(
        self,
        promo_code: str,
        access_levels: list[str],
        exclude_id: Optional[str] = None,
    ) -> None:
        """
        Enforce uniqueness on (promo_code + access level set).
        Same promo_code is allowed only when access level set is different.
        """
        target = self._canonical_access_levels(access_levels)
        q = self.db.query(Promotion).filter(Promotion.promo_code == promo_code)
        if exclude_id:
            q = q.filter(Promotion.id != exclude_id)
        for existing in q.all():
            if self._canonical_access_levels(existing.access_levels) == target:
                raise handle_conflict(
                    "Promo code already exists for the same access types. "
                    "Use a different promo code or change access types."
                )
    
    def list_promotions(
        self,
        page: int = 1,
        limit: int = 50,
        user_type: Optional[str] = None,
        query: Optional[str] = None,
        status: Optional[str] = None,
        promo_type: Optional[str] = None,
    ):
        """List promotions. When query is set, filter by promo_code, name, or product code of linked products."""
        q = self.db.query(Promotion)

        if query and (query := (query or "").strip()):
            search_term = f"%{query}%"
            # Correlated exists: promotions that have at least one product whose product_code matches
            has_product_match = exists().where(
                PromotionProduct.promotion_id == Promotion.id
            ).where(
                PromotionProduct.product_id == Product.id
            ).where(
                Product.product_code.ilike(search_term)
            )
            q = q.filter(
                or_(
                    Promotion.promo_code.ilike(search_term),
                    Promotion.name.ilike(search_term),
                    has_product_match,
                )
            )

        if status and status != "all":
            if status == "active":
                q = q.filter(Promotion.is_active.is_(True))
            elif status == "inactive":
                q = q.filter(Promotion.is_active.is_(False))

        if promo_type and (promo_type := (promo_type or "").strip()):
            q = q.filter(Promotion.promo_type == promo_type)

        q = q.order_by(Promotion.created_at.desc())

        if user_type:
            q = q.filter(Promotion.access_levels.contains([user_type]))

        total = q.count()
        offset = (page - 1) * limit
        promotions = q.offset(offset).limit(limit).all()
        
        # Add product counts to each promotion object
        for promotion in promotions:
            products_count = self.db.query(func.count(PromotionProduct.id)).filter(
                PromotionProduct.promotion_id == promotion.id
            ).scalar() or 0
            # Set products_count as an attribute on the promotion object
            promotion.products_count = products_count
        
        return {
            "data": promotions,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_promotion(self, promotion_id: str):
        """Get a promotion by ID."""
        from sqlalchemy.orm import joinedload
        
        promotion = self.db.query(Promotion).filter(Promotion.id == promotion_id).first()
        if not promotion:
            raise handle_not_found("Promotion", promotion_id)
        
        # Add product count
        products_count = self.db.query(func.count(PromotionProduct.id)).filter(
            PromotionProduct.promotion_id == promotion.id
        ).scalar() or 0
        promotion.products_count = products_count
        
        # Load products with relationships
        products = self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(
            PromotionProduct.promotion_id == promotion_id
        ).order_by(PromotionProduct.created_at.asc()).all()
        
        # Set products on promotion object
        promotion.products = products
        
        return promotion
    
    def create_promotion(self, promotion_data: PromotionCreate, created_by: str):
        """Create a new promotion. Validates access_levels against catalog; defaults to all active types if missing."""
        access_svc = ContactAccessTypeService(self.db)
        promotion_dict = promotion_data.model_dump()
        promotion_dict["promo_code"] = (promotion_dict.get("promo_code") or "").strip()
        if not promotion_dict["promo_code"]:
            raise handle_conflict("Promo code cannot be empty.")
        promotion_dict["created_by"] = created_by
        if promotion_dict.get("access_levels"):
            promotion_dict["access_levels"] = access_svc.validate_access_levels(
                promotion_dict["access_levels"], field_name="access_levels"
            )
        else:
            promotion_dict["access_levels"] = access_svc.get_default_access_levels()
        self._ensure_promo_code_access_levels_unique(
            promo_code=promotion_dict["promo_code"],
            access_levels=promotion_dict["access_levels"],
        )
        promotion = Promotion(**promotion_dict)
        self.db.add(promotion)
        self.db.commit()
        self.db.refresh(promotion)
        return promotion
    
    def update_promotion(self, promotion_id: str, promotion_data: PromotionUpdate):
        """Update a promotion. Enforces uniqueness on promo_code + access level set."""
        promotion = self.get_promotion(promotion_id)

        update_data = promotion_data.model_dump(exclude_unset=True)
        access_svc = ContactAccessTypeService(self.db)
        if "access_levels" in update_data and update_data["access_levels"]:
            update_data["access_levels"] = access_svc.validate_access_levels(
                update_data["access_levels"], field_name="access_levels"
            )

        if "promo_code" in update_data:
            new_code = (update_data["promo_code"] or "").strip()
            if not new_code:
                raise handle_conflict("Promo code cannot be empty.")
            update_data["promo_code"] = new_code

        final_code = update_data.get("promo_code", promotion.promo_code)
        final_access_levels = update_data.get("access_levels", promotion.access_levels)
        self._ensure_promo_code_access_levels_unique(
            promo_code=final_code,
            access_levels=final_access_levels or [],
            exclude_id=promotion_id,
        )

        for key, value in update_data.items():
            setattr(promotion, key, value)

        self.db.commit()
        self.db.refresh(promotion)
        return promotion

    def delete_promotion(self, promotion_id: str):
        """Delete a promotion (cascade deletes promotion_products and promotion_attachments)."""
        promotion = self.get_promotion(promotion_id)
        self.db.delete(promotion)
        self.db.commit()

    def bulk_delete_promotions(self, promotion_ids: list[str]):
        """Delete multiple promotions. Returns count deleted."""
        if not promotion_ids:
            return {"message": "No promotions to delete", "deleted_count": 0}
        deleted = self.db.query(Promotion).filter(Promotion.id.in_(promotion_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"message": f"{deleted} promotion(s) deleted", "deleted_count": deleted}

    def bulk_update_access_levels(self, promotion_ids: list[str], access_levels: list[str]):
        """Set access_levels on multiple promotions. Returns count updated. Validates against contact access type catalog."""
        if not promotion_ids:
            return {"message": "No promotions selected", "updated_count": 0}
        access_svc = ContactAccessTypeService(self.db)
        normalized = access_svc.validate_access_levels(access_levels, field_name="access_levels")
        target_canonical = self._canonical_access_levels(normalized)

        selected_promotions = self.db.query(Promotion).filter(Promotion.id.in_(promotion_ids)).all()
        selected_ids = {p.id for p in selected_promotions}
        selected_codes = {p.promo_code for p in selected_promotions}

        if selected_codes:
            code_conflict_scope = self.db.query(Promotion).filter(Promotion.promo_code.in_(selected_codes)).all()
            by_code: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
            for p in code_conflict_scope:
                canonical = target_canonical if p.id in selected_ids else self._canonical_access_levels(p.access_levels)
                by_code.setdefault(p.promo_code, []).append((p.id, canonical))

            for code, rows in by_code.items():
                seen: dict[tuple[str, ...], str] = {}
                for row_id, canonical in rows:
                    existing_id = seen.get(canonical)
                    if existing_id and existing_id != row_id:
                        raise handle_conflict(
                            f"Bulk update would create duplicate promo code/access types for code '{code}'. "
                            "Adjust selection or access types."
                        )
                    seen[canonical] = row_id

        updated = (
            self.db.query(Promotion)
            .filter(Promotion.id.in_(promotion_ids))
            .update({"access_levels": normalized}, synchronize_session=False)
        )
        self.db.commit()
        return {"message": f"Access levels set for {updated} promotion(s).", "updated_count": updated}


class PromotionProductService:
    """Service for promotion product operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def _compute_discount_values(self, list_price: float, promo_price: float) -> tuple[float, float]:
        """Compute discount amount/percent and guard DB precision for discount_percent NUMERIC(5,2)."""
        discount_amount = list_price - promo_price
        discount_percent = (discount_amount / list_price * 100) if list_price > 0 else 0
        # DB column is NUMERIC(5,2) -> absolute value must be < 1000
        if abs(discount_percent) >= 1000:
            raise handle_conflict(
                "Promotion price causes discount percent overflow. Please use a price that results in discount percentage between -999.99% and 999.99%."
            )
        return discount_amount, discount_percent
    
    def list_promotion_products(self, promotion_id: Optional[str] = None, page: int = 1, limit: int = 50, sort_field: str = "created_at", sort_dir: str = "asc", query: Optional[str] = None):
        """List products for a promotion or all promotion products."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_
        import logging
        logger = logging.getLogger(__name__)
        
        q = self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        )
        
        if promotion_id:
            logger.debug(f"Filtering by promotion_id: {promotion_id} (type: {type(promotion_id)})")
            # Ensure UUID comparison works correctly
            q = q.filter(PromotionProduct.promotion_id == promotion_id)
            # Debug: check how many match
            count_before = q.count()
            logger.debug(f"Found {count_before} promotion products matching promotion_id {promotion_id}")
        
        if query:
            # Search in product code, product name, or promotion code
            # Need to join with Product and Promotion for search
            q = q.join(Product, PromotionProduct.product_id == Product.id).join(
                Promotion, PromotionProduct.promotion_id == Promotion.id
            ).filter(
                or_(
                    Product.product_code.ilike(f"%{query}%"),
                    Product.product_name.ilike(f"%{query}%"),
                    Promotion.promo_code.ilike(f"%{query}%")
                )
            )
        
        # Sorting
        sort_map = {
            "created_at": PromotionProduct.created_at,
        }
        sort_column = sort_map.get(sort_field, PromotionProduct.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        products = q.offset(offset).limit(limit).all()
        
        return {
            "data": products,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_promotion_product(self, promotion_id: str, product_id: str):
        """Get a promotion product."""
        from sqlalchemy.orm import joinedload
        product = self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(
            PromotionProduct.promotion_id == promotion_id,
            PromotionProduct.product_id == product_id
        ).first()
        if not product:
            raise handle_not_found("Promotion Product", f"{promotion_id}/{product_id}")
        return product
    
    def create_promotion_product(self, product_data: PromotionProductCreate):
        """Add a product to a promotion."""
        from sqlalchemy.orm import joinedload
        from app.models.product import Product
        
        existing = self.db.query(PromotionProduct).filter(
            PromotionProduct.promotion_id == product_data.promotion_id,
            PromotionProduct.product_id == product_data.product_id
        ).first()
        if existing:
            label = _product_display_label(self.db, product_data.product_id)
            raise handle_conflict(f"Product already on this promotion: {label}.")
        
        # Get the product to calculate discount
        product = self.db.query(Product).filter(Product.id == product_data.product_id).first()
        if not product:
            raise handle_not_found("Product", product_data.product_id)
        
        # Calculate discount if promotion_price is provided
        promo_selling_price = product_data.promo_selling_price
        discount_amount = None
        discount_percent = None
        
        if promo_selling_price and product.list_price:
            list_price = float(product.list_price)
            promo_price = float(promo_selling_price)
            discount_amount, discount_percent = self._compute_discount_values(list_price, promo_price)
        
        promotion_product = PromotionProduct(
            promotion_id=product_data.promotion_id,
            product_id=product_data.product_id,
            promo_selling_price=promo_selling_price,
            discount_amount=discount_amount,
            discount_percent=discount_percent
        )
        self.db.add(promotion_product)
        try:
            self.db.commit()
            self.db.refresh(promotion_product)
        except IntegrityError as e:
            self.db.rollback()
            raise_promotion_product_unique_violation(self.db, e)

        # Reload with product and promotion relationships
        return self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(PromotionProduct.id == promotion_product.id).first()
    
    def update_promotion_product(self, promotion_id: str, product_id: str, product_data: PromotionProductUpdate):
        """Update a promotion product."""
        from sqlalchemy.orm import joinedload
        from app.models.product import Product
        
        promotion_product = self.get_promotion_product(promotion_id, product_id)
        
        # Get the product to recalculate discount if price changed
        product = self.db.query(Product).filter(Product.id == product_id).first()
        
        update_data = product_data.model_dump(exclude_unset=True)
        
        # Recalculate discount if promo_selling_price is being updated
        if 'promo_selling_price' in update_data and product and product.list_price:
            promo_price = float(update_data['promo_selling_price'])
            list_price = float(product.list_price)
            discount_amount, discount_percent = self._compute_discount_values(list_price, promo_price)
            update_data['discount_amount'] = discount_amount
            update_data['discount_percent'] = discount_percent
        
        for key, value in update_data.items():
            setattr(promotion_product, key, value)
        
        self.db.commit()
        self.db.refresh(promotion_product)
        
        # Reload with product and promotion relationships
        return self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(PromotionProduct.id == promotion_product.id).first()
    
    def delete_promotion_product(self, promotion_id: str, product_id: str):
        """Remove a product from a promotion."""
        product = self.get_promotion_product(promotion_id, product_id)
        self.db.delete(product)
        self.db.commit()
        return {"message": "Product removed from promotion"}


class CampaignTypeService:
    """Service for campaign type operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_campaign_types(self):
        """List all campaign types."""
        types = self.db.query(CampaignType).all()
        return types
    
    def get_campaign_type(self, type_id: str):
        """Get a campaign type by ID."""
        campaign_type = self.db.query(CampaignType).filter(CampaignType.id == type_id).first()
        if not campaign_type:
            raise handle_not_found("Campaign Type", type_id)
        return campaign_type
    
    def create_campaign_type(self, type_data: CampaignTypeCreate):
        """Create a new campaign type."""
        existing = self.db.query(CampaignType).filter(
            CampaignType.type_code == type_data.type_code
        ).first()
        if existing:
            raise handle_conflict("Campaign type code already exists.")
        
        campaign_type = CampaignType(**type_data.model_dump())
        self.db.add(campaign_type)
        self.db.commit()
        self.db.refresh(campaign_type)
        return campaign_type
    
    def update_campaign_type(self, type_id: str, type_data: CampaignTypeUpdate):
        """Update a campaign type."""
        campaign_type = self.get_campaign_type(type_id)
        
        update_data = type_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(campaign_type, key, value)
        
        self.db.commit()
        self.db.refresh(campaign_type)
        return campaign_type


class MarketingCampaignService:
    """Service for marketing campaign operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_campaigns(self, page: int = 1, limit: int = 50):
        """List marketing campaigns."""
        q = self.db.query(MarketingCampaign).order_by(MarketingCampaign.created_at.desc())
        
        total = q.count()
        offset = (page - 1) * limit
        campaigns = q.offset(offset).limit(limit).all()
        
        return {
            "data": campaigns,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_campaign(self, campaign_id: str):
        """Get a campaign by ID."""
        campaign = self.db.query(MarketingCampaign).filter(MarketingCampaign.id == campaign_id).first()
        if not campaign:
            raise handle_not_found("Marketing Campaign", campaign_id)
        return campaign
    
    def create_campaign(self, campaign_data: MarketingCampaignCreate, created_by: str):
        """Create a new marketing campaign."""
        existing = self.db.query(MarketingCampaign).filter(
            MarketingCampaign.campaign_code == campaign_data.campaign_code
        ).first()
        if existing:
            raise handle_conflict("Campaign code already exists.")
        
        campaign_dict = campaign_data.model_dump()
        campaign_dict["created_by"] = created_by
        campaign = MarketingCampaign(**campaign_dict)
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign
    
    def update_campaign(self, campaign_id: str, campaign_data: MarketingCampaignUpdate):
        """Update a marketing campaign."""
        campaign = self.get_campaign(campaign_id)
        
        update_data = campaign_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(campaign, key, value)
        
        self.db.commit()
        self.db.refresh(campaign)
        return campaign


class PromotionAttachmentService:
    """Service for promotion attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_promotion_attachments(self, page: int = 1, limit: int = 50, sort_field: str = "created_at", sort_dir: str = "asc", promotion_id: Optional[str] = None, attachment_id: Optional[str] = None):
        """List promotion attachments with pagination and filtering."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_
        
        q = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        )
        
        if promotion_id:
            q = q.filter(PromotionAttachment.promotion_id == promotion_id)
        if attachment_id:
            q = q.filter(PromotionAttachment.attachment_id == attachment_id)
        
        # Sorting
        sort_map = {
            "created_at": PromotionAttachment.created_at,
            "sort_order": PromotionAttachment.sort_order,
        }
        sort_column = sort_map.get(sort_field, PromotionAttachment.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        promotion_attachments = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": promotion_attachments,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_promotion_attachment(self, promotion_attachment_id: str):
        """Get a promotion attachment by ID."""
        from sqlalchemy.orm import joinedload
        promotion_attachment = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment_id).first()
        if not promotion_attachment:
            raise handle_not_found("Promotion Attachment", promotion_attachment_id)
        return promotion_attachment
    
    def create_promotion_attachment(self, promotion_attachment_data: PromotionAttachmentCreate, created_by: Optional[str] = None):
        """Create a new promotion attachment relationship."""
        # Check if relationship already exists
        existing = self.db.query(PromotionAttachment).filter(
            PromotionAttachment.promotion_id == promotion_attachment_data.promotion_id,
            PromotionAttachment.attachment_id == promotion_attachment_data.attachment_id
        ).first()
        if existing:
            raise handle_conflict("Promotion attachment relationship already exists.")
        
        attachment_dict = promotion_attachment_data.model_dump()
        if created_by:
            attachment_dict["created_by"] = created_by
        
        promotion_attachment = PromotionAttachment(**attachment_dict)
        self.db.add(promotion_attachment)
        self.db.commit()
        self.db.refresh(promotion_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment.id).first()
    
    def update_promotion_attachment(self, promotion_attachment_id: str, promotion_attachment_data: PromotionAttachmentUpdate):
        """Update a promotion attachment relationship."""
        promotion_attachment = self.get_promotion_attachment(promotion_attachment_id)
        
        update_data = promotion_attachment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(promotion_attachment, key, value)
        
        from datetime import datetime
        promotion_attachment.updated_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(promotion_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment.id).first()
    
    def delete_promotion_attachment(self, promotion_attachment_id: str):
        """Delete a promotion attachment relationship."""
        promotion_attachment = self.get_promotion_attachment(promotion_attachment_id)
        self.db.delete(promotion_attachment)
        self.db.commit()
        return {"message": "Promotion attachment deleted successfully"}
    
    def get_promotion_attachments_by_promotion(self, promotion_id: str):
        """Get all attachments for a specific promotion."""
        from sqlalchemy.orm import joinedload
        promotion_attachments = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.promotion_id == promotion_id).order_by(
            PromotionAttachment.sort_order.asc().nulls_last(),
            PromotionAttachment.created_at.asc()
        ).all()
        return promotion_attachments
