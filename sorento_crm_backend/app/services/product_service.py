"""Product service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List
from decimal import Decimal
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure, ProductAttachment
from app.models.resources import Attachment, AttachmentType
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductCategoryCreate, ProductCategoryUpdate,
    BrandCreate, BrandUpdate, UnitOfMeasureCreate, UnitOfMeasureUpdate,
    ProductAttachmentCreate, ProductAttachmentUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.schemas.common import PaginationResponse


class ProductService:
    """Service for product operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_products(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        category_id: Optional[str] = None,
        brand_id: Optional[str] = None,
        status: Optional[str] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        item_type: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List products with filtering and pagination."""
        # Build query
        q = self.db.query(Product)
        
        # Apply filters
        filters = []
        
        if category_id and category_id != "all":
            filters.append(Product.category_id == category_id)
        
        if brand_id and brand_id != "all":
            filters.append(Product.brand_id == brand_id)
        
        if status and status != "all":
            filters.append(Product.is_active == (status == "active"))
        
        if item_type:
            filters.append(Product.item_type == item_type)
        
        if price_min or price_max:
            price_filters = []
            if price_min:
                price_filters.append(Product.list_price >= Decimal(str(price_min)))
            if price_max:
                price_filters.append(Product.list_price <= Decimal(str(price_max)))
            filters.append(and_(*price_filters))
        
        if query:
            filters.append(
                or_(
                    Product.product_code.ilike(f"%{query}%"),
                    Product.product_name.ilike(f"%{query}%")
                )
            )
        
        if filters:
            q = q.filter(and_(*filters))
        
        # Get total count
        total = q.count()
        
        # Apply sorting
        sort_map = {
            "created_at": Product.created_at,
            "product_code": Product.product_code,
            "product_name": Product.product_name,
            "list_price": Product.list_price,
            "is_active": Product.is_active,
        }
        sort_column = sort_map.get(sort_field, Product.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        # Apply pagination
        offset = (page - 1) * limit
        products = q.offset(offset).limit(limit).all()
        
        return {
            "data": products,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit
            },
            "empty": total == 0
        }
    
    def get_product(self, product_id: str):
        """Get a single product by ID."""
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise handle_not_found("Product", product_id)
        return product
    
    def create_product(self, product_data: ProductCreate, created_by: str):
        """Create a new product."""
        # Check if product_code already exists
        existing = self.db.query(Product).filter(Product.product_code == product_data.product_code).first()
        if existing:
            raise handle_conflict("Product code already exists. Please use a different code.")
        
        product = Product(**product_data.model_dump(), created_by=created_by)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product
    
    def update_product(self, product_id: str, product_data: ProductUpdate, updated_by: str):
        """Update a product."""
        product = self.get_product(product_id)
        
        update_data = product_data.model_dump(exclude_unset=True)
        if update_data:
            update_data["updated_by"] = updated_by
            for key, value in update_data.items():
                setattr(product, key, value)
            
            self.db.commit()
            self.db.refresh(product)
        
        return product
    
    def delete_product(self, product_id: str):
        """Delete a product."""
        product = self.get_product(product_id)
        self.db.delete(product)
        self.db.commit()
        return {"message": "Product deleted successfully"}


class ProductCategoryService:
    """Service for product category operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_categories(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List product categories."""
        q = self.db.query(ProductCategory)
        
        if query:
            q = q.filter(
                or_(
                    ProductCategory.category_code.ilike(f"%{query}%"),
                    ProductCategory.category_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        categories = q.offset(offset).limit(limit).all()
        
        return {
            "data": categories,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_category(self, category_id: str):
        """Get a category by ID."""
        category = self.db.query(ProductCategory).filter(ProductCategory.id == category_id).first()
        if not category:
            raise handle_not_found("Category", category_id)
        return category
    
    def get_categories_tree(self):
        """Get product categories as a tree structure."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import func
        
        # Get all active categories
        categories = self.db.query(ProductCategory).filter(
            ProductCategory.is_active == True
        ).order_by(ProductCategory.display_order.asc()).all()
        
        # Count products per category
        category_product_counts = {}
        for category in categories:
            count = self.db.query(func.count(Product.id)).filter(
                Product.category_id == category.id
            ).scalar()
            category_product_counts[category.id] = count or 0
        
        # Build tree structure
        category_dict = {}
        root_categories = []
        
        # First pass: create dictionary of all categories
        for category in categories:
            category_dict[category.id] = {
                "id": category.id,
                "category_code": category.category_code,
                "category_name": category.category_name,
                "description": category.description,
                "parent_category_id": str(category.parent_category_id) if category.parent_category_id else None,
                "is_active": category.is_active,
                "display_order": category.display_order or 0,
                "created_by": str(category.created_by) if category.created_by else None,
                "created_at": category.created_at,
                "updated_at": category.updated_at,
                "children": [],
                "product_count": category_product_counts.get(category.id, 0),
            }
        
        # Second pass: build tree structure
        for category in categories:
            cat_data = category_dict[category.id]
            if category.parent_category_id:
                # Has parent - add to parent's children
                parent_id = str(category.parent_category_id)
                if parent_id in category_dict:
                    category_dict[parent_id]["children"].append(cat_data)
            else:
                # Root category
                root_categories.append(cat_data)
        
        # Sort children by display_order
        def sort_children(cat):
            if cat["children"]:
                cat["children"].sort(key=lambda x: x.get("display_order", 0))
                for child in cat["children"]:
                    sort_children(child)
        
        for root in root_categories:
            sort_children(root)
        
        return root_categories
    
    def create_category(self, category_data: ProductCategoryCreate):
        """Create a new category."""
        existing = self.db.query(ProductCategory).filter(
            ProductCategory.category_code == category_data.category_code
        ).first()
        if existing:
            raise handle_conflict("Category code already exists.")
        
        category = ProductCategory(**category_data.model_dump())
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
    
    def update_category(self, category_id: str, category_data: ProductCategoryUpdate):
        """Update a category."""
        category = self.get_category(category_id)
        
        update_data = category_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(category, key, value)
        
        self.db.commit()
        self.db.refresh(category)
        return category


class BrandService:
    """Service for brand operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_brands(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List brands."""
        q = self.db.query(Brand)
        
        if query:
            q = q.filter(
                or_(
                    Brand.brand_code.ilike(f"%{query}%"),
                    Brand.brand_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        brands = q.offset(offset).limit(limit).all()
        
        return {
            "data": brands,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_brand(self, brand_id: str):
        """Get a brand by ID."""
        brand = self.db.query(Brand).filter(Brand.id == brand_id).first()
        if not brand:
            raise handle_not_found("Brand", brand_id)
        return brand
    
    def create_brand(self, brand_data: BrandCreate):
        """Create a new brand."""
        existing = self.db.query(Brand).filter(Brand.brand_code == brand_data.brand_code).first()
        if existing:
            raise handle_conflict("Brand code already exists.")
        
        brand = Brand(**brand_data.model_dump())
        self.db.add(brand)
        self.db.commit()
        self.db.refresh(brand)
        return brand
    
    def update_brand(self, brand_id: str, brand_data: BrandUpdate):
        """Update a brand."""
        brand = self.get_brand(brand_id)
        
        update_data = brand_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(brand, key, value)
        
        self.db.commit()
        self.db.refresh(brand)
        return brand


class UnitOfMeasureService:
    """Service for unit of measure operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_uoms(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List units of measure."""
        q = self.db.query(UnitOfMeasure)
        
        if query:
            q = q.filter(
                or_(
                    UnitOfMeasure.uom_code.ilike(f"%{query}%"),
                    UnitOfMeasure.uom_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        uoms = q.offset(offset).limit(limit).all()
        
        return {
            "data": uoms,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_uom(self, uom_id: str):
        """Get a UOM by ID."""
        uom = self.db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).first()
        if not uom:
            raise handle_not_found("Unit of Measure", uom_id)
        return uom
    
    def create_uom(self, uom_data: UnitOfMeasureCreate):
        """Create a new UOM."""
        existing = self.db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == uom_data.uom_code).first()
        if existing:
            raise handle_conflict("UOM code already exists.")
        
        uom = UnitOfMeasure(**uom_data.model_dump())
        self.db.add(uom)
        self.db.commit()
        self.db.refresh(uom)
        return uom
    
    def update_uom(self, uom_id: str, uom_data: UnitOfMeasureUpdate):
        """Update a UOM."""
        uom = self.get_uom(uom_id)
        
        update_data = uom_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(uom, key, value)
        
        self.db.commit()
        self.db.refresh(uom)
        return uom


class ProductAttachmentService:
    """Service for product attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_product_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        product_id: Optional[str] = None,
        attachment_id: Optional[str] = None
    ):
        """List product attachments with filtering and pagination."""
        from sqlalchemy.orm import joinedload
        
        q = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        )
        
        if product_id:
            q = q.filter(ProductAttachment.product_id == product_id)
        
        if attachment_id:
            q = q.filter(ProductAttachment.attachment_id == attachment_id)
        
        sort_map = {
            "created_at": ProductAttachment.created_at,
            "sort_order": ProductAttachment.sort_order,
            "is_primary": ProductAttachment.is_primary,
        }
        sort_column = sort_map.get(sort_field, ProductAttachment.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        product_attachments = q.offset(offset).limit(limit).all()
        
        return {
            "data": product_attachments,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_product_attachment(self, product_attachment_id: str):
        """Get a product attachment by ID."""
        from sqlalchemy.orm import joinedload
        product_attachment = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(ProductAttachment.id == product_attachment_id).first()
        if not product_attachment:
            raise handle_not_found("Product Attachment", product_attachment_id)
        return product_attachment
    
    def create_product_attachment(self, product_attachment_data: ProductAttachmentCreate, created_by: Optional[str] = None):
        """Create a new product attachment relationship."""
        # Check if relationship already exists
        existing = self.db.query(ProductAttachment).filter(
            ProductAttachment.product_id == product_attachment_data.product_id,
            ProductAttachment.attachment_id == product_attachment_data.attachment_id
        ).first()
        if existing:
            raise handle_conflict("Product attachment relationship already exists.")
        
        attachment_dict = product_attachment_data.model_dump()
        if created_by:
            attachment_dict["created_by"] = created_by
        
        product_attachment = ProductAttachment(**attachment_dict)
        self.db.add(product_attachment)
        self.db.commit()
        self.db.refresh(product_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(ProductAttachment.id == product_attachment.id).first()
    
    def update_product_attachment(self, product_attachment_id: str, product_attachment_data: ProductAttachmentUpdate):
        """Update a product attachment relationship."""
        product_attachment = self.get_product_attachment(product_attachment_id)
        
        update_data = product_attachment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(product_attachment, key, value)
        
        from datetime import datetime
        product_attachment.updated_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(product_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(ProductAttachment.id == product_attachment.id).first()
    
    def delete_product_attachment(self, product_attachment_id: str):
        """Delete a product attachment relationship."""
        product_attachment = self.get_product_attachment(product_attachment_id)
        self.db.delete(product_attachment)
        self.db.commit()
        return {"message": "Product attachment deleted successfully"}
    
    def get_product_attachments_by_product(self, product_id: str):
        """Get all attachments for a specific product."""
        from sqlalchemy.orm import joinedload
        product_attachments = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(ProductAttachment.product_id == product_id).order_by(
            ProductAttachment.sort_order.asc().nulls_last(),
            ProductAttachment.created_at.asc()
        ).all()
        return product_attachments
