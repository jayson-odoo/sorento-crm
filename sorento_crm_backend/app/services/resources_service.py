"""Resources service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.resources import Attachment, AttachmentType, AttachmentDirectory
from app.schemas.resources import (
    AttachmentCreate, AttachmentUpdate, AttachmentTypeCreate, AttachmentTypeUpdate,
    AttachmentDirectoryCreate, AttachmentDirectoryUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict


class AttachmentDirectoryService:
    """Service for attachment directory (folder) operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_flat(self, parent_id: Optional[str] = None):
        """List directories directly under parent_id (None = root)."""
        q = self.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.parent_id == parent_id
        ).order_by(AttachmentDirectory.sort_order.asc().nullsfirst(), AttachmentDirectory.name.asc())
        return q.all()

    def get_tree(self, parent_id: Optional[str] = None):
        """Return directory tree rooted at parent_id (None = root)."""
        dirs = self.list_flat(parent_id)
        result = []
        for d in dirs:
            node = {
                "id": str(d.id),
                "name": d.name,
                "parent_id": str(d.parent_id) if d.parent_id else None,
                "sort_order": d.sort_order,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "children": self.get_tree(str(d.id)),
            }
            result.append(node)
        return result

    def get_directory(self, directory_id: str):
        """Get a directory by ID."""
        d = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == directory_id).first()
        if not d:
            raise handle_not_found("Attachment directory", directory_id)
        return d

    def create_directory(self, data: AttachmentDirectoryCreate):
        """Create a new directory."""
        if data.parent_id:
            self.get_directory(data.parent_id)
        d = AttachmentDirectory(**data.model_dump())
        self.db.add(d)
        self.db.commit()
        self.db.refresh(d)
        return d

    def update_directory(self, directory_id: str, data: AttachmentDirectoryUpdate):
        """Update a directory."""
        d = self.get_directory(directory_id)
        payload = data.model_dump(exclude_unset=True)
        if "parent_id" in payload and payload["parent_id"] == directory_id:
            raise handle_conflict("Directory cannot be its own parent.")
        for k, v in payload.items():
            setattr(d, k, v)
        self.db.commit()
        self.db.refresh(d)
        return d

    def delete_directory(self, directory_id: str):
        """Delete a directory (cascade to children; attachments get directory_id SET NULL)."""
        d = self.get_directory(directory_id)
        self.db.delete(d)
        self.db.commit()

    def get_directory_by_parent_and_name(self, parent_id: Optional[str], name: str):
        """Get a directory by parent_id and name, or None if not found."""
        q = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.name == name)
        if parent_id is None:
            q = q.filter(AttachmentDirectory.parent_id.is_(None))
        else:
            q = q.filter(AttachmentDirectory.parent_id == parent_id)
        return q.first()

    def get_or_create_directory(self, parent_id: Optional[str], name: str):
        """Get existing directory by parent_id and name, or create it."""
        existing = self.get_directory_by_parent_and_name(parent_id, name)
        if existing:
            return existing
        data = AttachmentDirectoryCreate(name=name, parent_id=parent_id, sort_order=None)
        return self.create_directory(data)

    def get_or_create_path(self, parent_id: Optional[str], path_parts: List[str]) -> Optional[str]:
        """Get or create a chain of directories and return the final directory id. Empty path_parts returns parent_id."""
        if not path_parts:
            return parent_id
        current_id = parent_id
        for part in path_parts:
            if not part.strip():
                continue
            d = self.get_or_create_directory(current_id, part.strip())
            current_id = str(d.id)
        return current_id


class AttachmentTypeService:
    """Service for attachment type operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_types(self, page: int = 1, limit: int = 50, query: Optional[str] = None, sort: Optional[str] = None, dir: str = "desc"):
        """List attachment types with pagination and filtering."""
        from app.schemas.common import PaginationResponse
        
        q = self.db.query(AttachmentType)
        
        # Apply search filter
        if query:
            q = q.filter(
                (AttachmentType.type_name.ilike(f"%{query}%")) |
                (AttachmentType.description.ilike(f"%{query}%"))
            )
        
        # Apply sorting
        sort_column = None
        if sort:
            if sort == "type_name":
                sort_column = AttachmentType.type_name
            elif sort == "created_at":
                sort_column = AttachmentType.created_at
            elif sort == "max_file_size_mb":
                sort_column = AttachmentType.max_file_size_mb
        
        if sort_column:
            if dir == "desc":
                q = q.order_by(sort_column.desc())
            else:
                q = q.order_by(sort_column.asc())
        else:
            # Default sorting by created_at desc
            q = q.order_by(AttachmentType.created_at.desc())
        
        total = q.count()
        offset = (page - 1) * limit
        types = q.offset(offset).limit(limit).all()
        
        return {
            "data": types,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_type(self, type_id: str):
        """Get an attachment type by ID."""
        attachment_type = self.db.query(AttachmentType).filter(AttachmentType.id == type_id).first()
        if not attachment_type:
            raise handle_not_found("Attachment Type", type_id)
        return attachment_type
    
    def create_type(self, type_data: AttachmentTypeCreate):
        """Create a new attachment type."""
        existing = self.db.query(AttachmentType).filter(
            AttachmentType.type_name == type_data.type_name
        ).first()
        if existing:
            raise handle_conflict("Attachment type name already exists.")
        
        attachment_type = AttachmentType(**type_data.model_dump())
        self.db.add(attachment_type)
        self.db.commit()
        self.db.refresh(attachment_type)
        return attachment_type
    
    def update_type(self, type_id: str, type_data: AttachmentTypeUpdate):
        """Update an attachment type."""
        attachment_type = self.get_type(type_id)
        
        update_data = type_data.model_dump(exclude_unset=True)
        
        # Check for name uniqueness if type_name is being updated
        if "type_name" in update_data and update_data["type_name"] != attachment_type.type_name:
            existing = self.db.query(AttachmentType).filter(
                AttachmentType.type_name == update_data["type_name"]
            ).first()
            if existing:
                raise handle_conflict("Attachment type name already exists.")
        
        for key, value in update_data.items():
            setattr(attachment_type, key, value)
        
        self.db.commit()
        self.db.refresh(attachment_type)
        return attachment_type
    
    def delete_type(self, type_id: str):
        """Delete an attachment type."""
        attachment_type = self.get_type(type_id)
        self.db.delete(attachment_type)
        self.db.commit()
        return attachment_type


class AttachmentService:
    """Service for attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        dir: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        directory_id: Optional[str] = None,
    ):
        """List attachments. Filter by directory_id when provided. Search by filename when query is provided."""
        from sqlalchemy.orm import joinedload
        q = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.is_deleted == False)
        
        if entity_type:
            q = q.filter(Attachment.entity_type == entity_type)
        if entity_id:
            q = q.filter(Attachment.entity_id == entity_id)
        if directory_id is not None:
            q = q.filter(Attachment.directory_id == directory_id)
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(Attachment.original_filename.ilike(term))
        
        sort_desc = (dir or "desc").lower() == "desc"
        if sort:
            sort_col = getattr(Attachment, sort, None)
            if sort_col is not None:
                q = q.order_by(sort_col.desc() if sort_desc else sort_col.asc())
            else:
                q = q.order_by(
                    Attachment.sort_order.asc().nulls_last(),
                    Attachment.uploaded_at.desc(),
                )
        else:
            q = q.order_by(
                Attachment.sort_order.asc().nulls_last(),
                Attachment.uploaded_at.desc(),
            )
        
        total = q.count()
        offset = (page - 1) * limit
        attachments = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": attachments,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_attachment(self, attachment_id: str):
        """Get an attachment by ID."""
        from sqlalchemy.orm import joinedload
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise handle_not_found("Attachment", attachment_id)
        return attachment

    def get_linked_entities(self, attachment_id: str) -> dict:
        """
        Resolve linked product(s), promotion(s), and form from product_attachments,
        promotion_attachments, and forms.attachment_id.
        Returns dict with linked_products, linked_promotions, linked_form.
        """
        from app.models.product import ProductAttachment, Product
        from app.models.marketing import PromotionAttachment, Promotion
        from app.models.forms import Form

        linked_products = []
        q = (
            self.db.query(Product.id, Product.product_name, Product.description)
            .join(ProductAttachment, ProductAttachment.product_id == Product.id)
            .filter(ProductAttachment.attachment_id == attachment_id)
        )
        for row in q.all():
            linked_products.append({
                "id": str(row.id),
                "name": row.product_name or str(row.id),
                "description": (row.description or "").strip() or None,
            })

        linked_promotions = []
        q = (
            self.db.query(Promotion.id, Promotion.name, Promotion.description)
            .join(PromotionAttachment, PromotionAttachment.promotion_id == Promotion.id)
            .filter(PromotionAttachment.attachment_id == attachment_id)
        )
        for row in q.all():
            linked_promotions.append({
                "id": str(row.id),
                "name": row.name or str(row.id),
                "description": (row.description or "").strip() or None,
            })

        linked_form = None
        form_row = (
            self.db.query(Form.id, Form.name, Form.purpose)
            .filter(Form.attachment_id == attachment_id)
            .first()
        )
        if form_row:
            linked_form = {
                "id": str(form_row.id),
                "name": form_row.name or str(form_row.id),
                "description": (form_row.purpose or "").strip() or None,
            }

        return {
            "linked_products": linked_products,
            "linked_promotions": linked_promotions,
            "linked_form": linked_form,
        }

    def get_entity_display_name(self, entity_type: Optional[str], entity_id: Optional[str]) -> Optional[str]:
        """Fallback: resolve entity_type + entity_id to a display name when not found via junction tables."""
        if not entity_type or not entity_id:
            return None
        kind = (entity_type or "").strip().lower()
        try:
            if kind == "product":
                from app.models.product import Product
                row = self.db.query(Product).filter(Product.id == entity_id).first()
                return row.product_name if row else None
            if kind == "promotion":
                from app.models.marketing import Promotion
                row = self.db.query(Promotion).filter(Promotion.id == entity_id).first()
                return row.name if row else None
            if kind == "form":
                from app.models.forms import Form
                row = self.db.query(Form).filter(Form.id == entity_id).first()
                return row.name if row else None
        except Exception:
            return None
        return None
    
    def create_attachment(self, attachment_data: AttachmentCreate, uploaded_by: str):
        """Create a new attachment."""
        from sqlalchemy.orm import joinedload
        import uuid as uuid_module
        
        attachment_dict = attachment_data.model_dump()
        # Ensure uploaded_by is a string (convert UUID if needed)
        if isinstance(uploaded_by, uuid_module.UUID):
            attachment_dict["uploaded_by"] = str(uploaded_by)
        else:
            attachment_dict["uploaded_by"] = str(uploaded_by) if uploaded_by else None
        
        attachment = Attachment(**attachment_dict)
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        
        # Reload with relationship
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment.id).first()
        
        return attachment
    
    def update_attachment(self, attachment_id: str, attachment_data: AttachmentUpdate):
        """Update an attachment."""
        attachment = self.get_attachment(attachment_id)
        
        update_data = attachment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(attachment, key, value)
        
        self.db.commit()
        self.db.refresh(attachment)
        return attachment
    
    def reorder_attachments(self, attachment_ids: list[str], directory_id: Optional[str] = None):
        """Set sort_order to index for each attachment id (within the same directory)."""
        for index, attachment_id in enumerate(attachment_ids):
            attachment = self.db.query(Attachment).filter(
                Attachment.id == attachment_id,
                Attachment.is_deleted == False,
            ).first()
            if not attachment:
                continue
            if directory_id is not None and attachment.directory_id != directory_id:
                continue
            attachment.sort_order = index
        self.db.commit()
        return {"message": "Order updated", "attachment_ids": attachment_ids}

    def delete_attachment(self, attachment_id: str, deleted_by: str):
        """Soft delete an attachment."""
        attachment = self.get_attachment(attachment_id)
        from datetime import datetime
        attachment.is_deleted = True
        attachment.deleted_at = datetime.utcnow()
        attachment.deleted_by = deleted_by
        self.db.commit()
        return {"message": "Attachment deleted successfully"}

    def delete_attachments(self, attachment_ids: list[str], deleted_by: str):
        """Soft delete multiple attachments by ID. Skips not-found and already-deleted."""
        from datetime import datetime
        count = 0
        for aid in attachment_ids:
            attachment = self.db.query(Attachment).filter(
                Attachment.id == aid,
                Attachment.is_deleted == False,
            ).first()
            if attachment:
                attachment.is_deleted = True
                attachment.deleted_at = datetime.utcnow()
                attachment.deleted_by = deleted_by
                count += 1
        self.db.commit()
        return {"message": f"{count} attachment(s) deleted successfully", "deleted_count": count}

    def delete_attachments_in_directories(self, directory_ids: list[str], deleted_by: str) -> int:
        """Soft delete all non-deleted attachments whose directory_id is in the given list. Returns count."""
        from datetime import datetime
        if not directory_ids:
            return 0
        q = self.db.query(Attachment).filter(
            Attachment.directory_id.in_(directory_ids),
            Attachment.is_deleted == False,
        )
        count = q.update(
            {
                Attachment.is_deleted: True,
                Attachment.deleted_at: datetime.utcnow(),
                Attachment.deleted_by: deleted_by,
            },
            synchronize_session=False,
        )
        self.db.commit()
        return count
    
    def get_file_content(self, attachment_id: str) -> bytes:
        """
        Retrieve file content from S3 for an attachment.
        
        Args:
            attachment_id: ID of the attachment
        
        Returns:
            File content as bytes
        
        Raises:
            Exception: If attachment not found or file retrieval fails
        """
        attachment = self.get_attachment(attachment_id)
        
        if not attachment.file_path:
            raise Exception("Attachment has no file path")
        
        from app.services.s3_service import S3Service
        from urllib.parse import urlparse
        
        s3_service = S3Service()
        
        try:
            # Extract S3 key from URL if it's a full URL
            # Format: https://bucket.s3.region.amazonaws.com/key
            # Or: https://bucket.s3.amazonaws.com/key
            file_path = attachment.file_path
            if file_path.startswith("https://"):
                # Parse URL to extract key
                parsed = urlparse(file_path)
                # Path will be like /key, so remove leading /
                s3_key = parsed.path.lstrip("/")
            else:
                # Already a key
                s3_key = file_path
            
            file_content = s3_service.download_file(s3_key)
            return file_content
        except Exception as e:
            raise Exception(f"Failed to retrieve file from S3: {str(e)}")
