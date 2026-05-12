"""Resources service for business logic."""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List

logger = logging.getLogger(__name__)
from app.models.resources import Attachment, AttachmentType, AttachmentDirectory
from app.schemas.resources import (
    AttachmentCreate, AttachmentUpdate, AttachmentTypeCreate, AttachmentTypeUpdate,
    AttachmentDirectoryCreate, AttachmentDirectoryUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error
from app.services.embedding_events import publish_embedding_event


class AttachmentDirectoryService:
    """Service for attachment directory (folder) operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_flat(self, parent_id: Optional[str] = None, include_deleted: bool = False):
        """List directories directly under parent_id (None = root). Excludes deleted unless include_deleted=True."""
        q = self.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.parent_id == parent_id
        )
        if not include_deleted:
            q = q.filter(AttachmentDirectory.is_deleted == False)
        q = q.order_by(AttachmentDirectory.sort_order.asc().nullsfirst(), AttachmentDirectory.name.asc())
        return q.all()

    def get_tree(self, parent_id: Optional[str] = None, include_deleted: bool = False):
        """Return directory tree rooted at parent_id (None = root)."""
        dirs = self.list_flat(parent_id, include_deleted=include_deleted)
        result = []
        for d in dirs:
            node = {
                "id": str(d.id),
                "name": d.name,
                "parent_id": str(d.parent_id) if d.parent_id else None,
                "sort_order": d.sort_order,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "children": self.get_tree(str(d.id), include_deleted=include_deleted),
            }
            result.append(node)
        return result

    def get_directory(self, directory_id: str, include_deleted: bool = False):
        """Get a directory by ID."""
        q = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == directory_id)
        if not include_deleted:
            q = q.filter(AttachmentDirectory.is_deleted == False)
        d = q.first()
        if not d:
            raise handle_not_found("Attachment directory", directory_id)
        return d

    def create_directory(self, data: AttachmentDirectoryCreate):
        """Create a new directory."""
        if data.parent_id:
            self.get_directory(data.parent_id, include_deleted=False)
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

    def delete_directory(self, directory_id: str, deleted_by: str):
        """Soft-delete a directory and all descendants; archive attachments in them. Uses bulk update for speed."""
        from datetime import datetime

        self.get_directory(directory_id)  # validate exists
        dir_ids = self.get_descendant_directory_ids(directory_id)
        if not dir_ids:
            self.db.commit()
            return
        now = datetime.utcnow()
        self.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.id.in_(dir_ids)
        ).update(
            {
                AttachmentDirectory.is_deleted: True,
                AttachmentDirectory.deleted_at: now,
                AttachmentDirectory.deleted_by: deleted_by,
            },
            synchronize_session=False,
        )
        self.db.commit()

    def get_directory_by_parent_and_name(self, parent_id: Optional[str], name: str, include_deleted: bool = False):
        """Get a directory by parent_id and name, or None if not found."""
        q = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.name == name)
        if parent_id is None:
            q = q.filter(AttachmentDirectory.parent_id.is_(None))
        else:
            q = q.filter(AttachmentDirectory.parent_id == parent_id)
        if not include_deleted:
            q = q.filter(AttachmentDirectory.is_deleted == False)
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

    def get_full_directory_path(self, directory_id: Optional[str]) -> Optional[str]:
        """Compute full path from root to directory, e.g. 'SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve'."""
        if not directory_id:
            return None
        parts: List[str] = []
        d = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == directory_id).first()
        while d:
            parts.append(d.name)
            d = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == d.parent_id).first() if d.parent_id else None
        parts.reverse()
        return " --> ".join(parts) if parts else None

    def get_descendant_directory_ids(self, directory_id: str, include_deleted: bool = True) -> List[str]:
        """Return all directory IDs in the subtree rooted at directory_id (including the directory itself). Uses recursive CTE for speed."""
        from sqlalchemy import text

        if include_deleted:
            stmt = text("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM attachment_directories WHERE id = :root_id
                    UNION ALL
                    SELECT d.id FROM attachment_directories d
                    INNER JOIN descendants p ON d.parent_id = p.id
                )
                SELECT id::text FROM descendants
            """)
        else:
            stmt = text("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM attachment_directories WHERE id = :root_id AND is_deleted = false
                    UNION ALL
                    SELECT d.id FROM attachment_directories d
                    INNER JOIN descendants p ON d.parent_id = p.id
                    WHERE d.is_deleted = false
                )
                SELECT id::text FROM descendants
            """)

        result = self.db.execute(stmt, {"root_id": directory_id})
        return [row[0] for row in result]

    def get_deleted_tree(self) -> list:
        """Return tree of deleted directories only (for trash view). Roots are deleted dirs whose parent is not deleted (or has no parent)."""
        all_deleted = self.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.is_deleted == True
        ).all()
        deleted_ids = {str(d.id) for d in all_deleted}
        deleted_by_parent: dict = {}
        for d in all_deleted:
            pid = str(d.parent_id) if d.parent_id else None
            deleted_by_parent.setdefault(pid, []).append(d)
        for pid, dirs in deleted_by_parent.items():
            dirs.sort(key=lambda x: (x.sort_order or 0, x.name or ""))

        def build_node(parent_key: Optional[str]) -> list:
            dirs = deleted_by_parent.get(parent_key, [])
            return [
                {
                    "id": str(d.id),
                    "name": d.name,
                    "parent_id": str(d.parent_id) if d.parent_id else None,
                    "sort_order": d.sort_order,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "children": build_node(str(d.id)),
                }
                for d in dirs
            ]

        # Roots: deleted folders whose parent is None OR not in deleted set (parent not deleted)
        roots = [
            d for d in all_deleted
            if d.parent_id is None or str(d.parent_id) not in deleted_ids
        ]
        roots.sort(key=lambda x: (x.sort_order or 0, x.name or ""))
        return [
            {
                "id": str(d.id),
                "name": d.name,
                "parent_id": str(d.parent_id) if d.parent_id else None,
                "sort_order": d.sort_order,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "children": build_node(str(d.id)),
            }
            for d in roots
        ]

    def restore_directory(self, directory_id: str) -> dict:
        """Restore a directory, its descendants, and all attachments in them. Uses bulk updates for speed."""
        d = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == directory_id).first()
        if not d:
            raise handle_not_found("Attachment directory", directory_id)
        if not d.is_deleted:
            raise handle_conflict("Directory is not deleted.")
        dir_ids = self.get_descendant_directory_ids(directory_id, include_deleted=True)
        # Bulk update directories
        self.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.id.in_(dir_ids),
            AttachmentDirectory.is_deleted == True,
        ).update(
            {
                AttachmentDirectory.is_deleted: False,
                AttachmentDirectory.deleted_at: None,
                AttachmentDirectory.deleted_by: None,
            },
            synchronize_session=False,
        )
        attachment_service = AttachmentService(self.db)
        restored = attachment_service.restore_attachments_in_directories(dir_ids)
        self.db.commit()
        return {"directories_restored": len(dir_ids), "attachments_restored": restored}

    def permanent_delete_directory(self, directory_id: str, deleted_by: str) -> dict:
        """Permanently delete a deleted directory, its descendants, and all attachments in them. Cannot be undone."""
        d = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == directory_id).first()
        if not d:
            raise handle_not_found("Attachment directory", directory_id)
        if not d.is_deleted:
            raise handle_conflict("Directory must be in Trash before permanent delete. Move to Trash first.")
        dir_ids = self.get_descendant_directory_ids(directory_id, include_deleted=True)
        attachment_service = AttachmentService(self.db)
        attachments = self.db.query(Attachment).filter(
            Attachment.directory_id.in_(dir_ids),
        ).all()
        attachment_ids = [str(a.id) for a in attachments]
        if attachment_ids:
            attachment_service.delete_attachments(attachment_ids, deleted_by)
        # Delete directories (leaf-first for parent_id FK)
        for did in reversed(dir_ids):
            child = self.db.query(AttachmentDirectory).filter(AttachmentDirectory.id == did).first()
            if child:
                self.db.delete(child)
        self.db.commit()
        return {"directories_deleted": len(dir_ids), "attachments_deleted": len(attachment_ids)}


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

    def get_type_by_code(self, code: str):
        """Get an attachment type by code, or None if not found."""
        if not (code or "").strip():
            return None
        return self.db.query(AttachmentType).filter(AttachmentType.code == code.strip()).first()
    
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
        is_deleted: Optional[bool] = None,
        access_levels: Optional[List[str]] = None,
        access_levels_match: Optional[str] = "any",
    ):
        """List attachments. Filter by directory_id when provided. Search by filename when query is provided. is_deleted=True returns trash.

        ``access_levels_match`` controls how multi-code filters combine:
        - ``any`` (default): row's access_levels overlap any selected code.
        - ``all``: row's access_levels contain every selected code (extras allowed).
        - ``exact``: row's access_levels equal the selected set.
        """
        from sqlalchemy.orm import joinedload
        from sqlalchemy import cast, String
        from sqlalchemy.dialects.postgresql import JSONB, ARRAY
        q = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        )
        if is_deleted is not None:
            q = q.filter(Attachment.is_deleted == is_deleted)
        else:
            q = q.filter(Attachment.is_deleted == False)

        if entity_type:
            q = q.filter(Attachment.entity_type == entity_type)
        if entity_id:
            q = q.filter(Attachment.entity_id == entity_id)
        if directory_id is not None:
            q = q.filter(Attachment.directory_id == directory_id)
        if access_levels:
            cleaned = sorted({lvl for lvl in access_levels if lvl and lvl.strip()})
            if cleaned:
                mode = (access_levels_match or "any").strip().lower()
                if mode == "exact":
                    payload = cast(cleaned, JSONB)
                    q = q.filter(
                        Attachment.access_levels.op('@>')(payload),
                        payload.op('@>')(Attachment.access_levels),
                    )
                elif mode == "all":
                    payload = cast(cleaned, JSONB)
                    q = q.filter(Attachment.access_levels.op('@>')(payload))
                else:
                    q = q.filter(
                        Attachment.access_levels.op('?|')(
                            cast(cleaned, ARRAY(String))
                        )
                    )
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Attachment.original_filename.ilike(term),
                    Attachment.description.ilike(term),
                )
            )
        
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
    
    def _get_attachment_any(self, attachment_id: str):
        """Get attachment by ID (active or archived)."""
        from sqlalchemy.orm import joinedload
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise handle_not_found("Attachment", attachment_id)
        return attachment

    def get_attachment(self, attachment_id: str):
        """Get an attachment by ID (active or archived)."""
        return self._get_attachment_any(attachment_id)

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
            self.db.query(
                Product.id,
                Product.product_name,
                Product.description,
                ProductAttachment.id.label("link_id"),
            )
            .join(ProductAttachment, ProductAttachment.product_id == Product.id)
            .filter(ProductAttachment.attachment_id == attachment_id)
        )
        for row in q.all():
            linked_products.append({
                "id": str(row.id),
                "name": row.product_name or str(row.id),
                "description": (row.description or "").strip() or None,
                "link_id": str(row.link_id),
            })

        linked_promotions = []
        q = (
            self.db.query(
                Promotion.id,
                Promotion.name,
                Promotion.description,
                PromotionAttachment.id.label("link_id"),
            )
            .join(PromotionAttachment, PromotionAttachment.promotion_id == Promotion.id)
            .filter(PromotionAttachment.attachment_id == attachment_id)
        )
        for row in q.all():
            linked_promotions.append({
                "id": str(row.id),
                "name": row.name or str(row.id),
                "description": (row.description or "").strip() or None,
                "link_id": str(row.link_id),
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

        linked_packing_lists = []
        from sqlalchemy import cast, String
        from app.models.entity_attachment import EntityAttachmentLink
        from app.models.procurement import InboundShipment
        # 1) Packing lists linked via entity_attachment_links (e.g. from "Link" in attachment modal)
        q = (
            self.db.query(
                InboundShipment.id,
                InboundShipment.shipment_number,
                InboundShipment.notes,
                EntityAttachmentLink.id.label("link_id"),
            )
            .join(
                InboundShipment,
                EntityAttachmentLink.entity_id == cast(InboundShipment.id, String),
            )
            .filter(
                EntityAttachmentLink.attachment_id == attachment_id,
                EntityAttachmentLink.entity_type == "inbound_shipment",
            )
        )
        seen_pl_ids = set()
        for row in q.all():
            seen_pl_ids.add(str(row.id))
            linked_packing_lists.append({
                "id": str(row.id),
                "name": (row.shipment_number or str(row.id)).strip(),
                "description": (row.notes or "").strip() or None,
                "link_id": str(row.link_id),
            })
        # 2) Packing lists that reference this attachment via InboundShipment.attachment_id (e.g. from external API)
        #    so attachment detail shows the same linkage the packing list detail shows
        direct = (
            self.db.query(
                InboundShipment.id,
                InboundShipment.shipment_number,
                InboundShipment.notes,
            )
            .filter(InboundShipment.attachment_id == attachment_id)
        )
        for row in direct.all():
            pl_id = str(row.id)
            if pl_id in seen_pl_ids:
                continue
            seen_pl_ids.add(pl_id)
            linked_packing_lists.append({
                "id": pl_id,
                "name": (row.shipment_number or pl_id).strip(),
                "description": (row.notes or "").strip() or None,
                "link_id": None,
            })

        return {
            "linked_products": linked_products,
            "linked_promotions": linked_promotions,
            "linked_form": linked_form,
            "linked_packing_lists": linked_packing_lists,
        }

    def list_attachment_ids_in_directory_subtree(self, root_directory_id: str) -> List[str]:
        """Non-deleted attachments in root folder and all non-deleted descendant folders."""
        dir_service = AttachmentDirectoryService(self.db)
        dir_ids = dir_service.get_descendant_directory_ids(root_directory_id, include_deleted=False)
        if not dir_ids:
            return []
        rows = (
            self.db.query(Attachment.id)
            .filter(
                Attachment.directory_id.in_(dir_ids),
                Attachment.is_deleted == False,
            )
            .all()
        )
        return [str(r.id) for r in rows]

    def resolve_bulk_attachment_ids(
        self,
        attachment_ids: Optional[List[str]],
        directory_id: Optional[str],
    ) -> List[str]:
        """Normalize scope to a unique list of attachment UUID strings."""
        if directory_id and str(directory_id).strip():
            did = str(directory_id).strip()
            AttachmentDirectoryService(self.db).get_directory(did, include_deleted=False)
            return self.list_attachment_ids_in_directory_subtree(did)
        ids = [str(a) for a in (attachment_ids or []) if a]
        return list(dict.fromkeys(ids))

    def preview_access_propagation(self, attachment_ids: List[str]) -> dict:
        """Deduplicated linked entities (product / promotion / form / packing list) that have propagatable access_levels."""
        unique_aids = list(dict.fromkeys([a for a in (attachment_ids or []) if a]))
        if not unique_aids:
            return {"attachment_count": 0, "targets": []}

        from sqlalchemy import cast as sql_cast, String
        from app.models.product import Product, ProductAttachment
        from app.models.marketing import Promotion, PromotionAttachment
        from app.models.forms import Form
        from app.models.procurement import InboundShipment
        from app.models.entity_attachment import EntityAttachmentLink

        targets: List[dict] = []
        seen = set()

        q = (
            self.db.query(Product.id, Product.product_code, Product.product_name)
            .join(ProductAttachment, ProductAttachment.product_id == Product.id)
            .filter(ProductAttachment.attachment_id.in_(unique_aids))
            .distinct()
        )
        for row in q.all():
            key = ("product", str(row.id))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "kind": "product",
                "entity_id": str(row.id),
                "code": row.product_code,
                "name": row.product_name or None,
            })

        q = (
            self.db.query(Promotion.id, Promotion.promo_code, Promotion.name)
            .join(PromotionAttachment, PromotionAttachment.promotion_id == Promotion.id)
            .filter(PromotionAttachment.attachment_id.in_(unique_aids))
            .distinct()
        )
        for row in q.all():
            key = ("promotion", str(row.id))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "kind": "promotion",
                "entity_id": str(row.id),
                "code": row.promo_code,
                "name": row.name or None,
            })

        q = self.db.query(Form.id, Form.code, Form.name).filter(Form.attachment_id.in_(unique_aids))
        for row in q.all():
            key = ("form", str(row.id))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "kind": "form",
                "entity_id": str(row.id),
                "code": row.code,
                "name": row.name or None,
            })

        q = (
            self.db.query(InboundShipment.id, InboundShipment.shipment_number)
            .join(
                EntityAttachmentLink,
                EntityAttachmentLink.entity_id == sql_cast(InboundShipment.id, String),
            )
            .filter(
                EntityAttachmentLink.attachment_id.in_(unique_aids),
                EntityAttachmentLink.entity_type == "inbound_shipment",
            )
            .distinct()
        )
        for row in q.all():
            key = ("packing_list", str(row.id))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "kind": "packing_list",
                "entity_id": str(row.id),
                "code": row.shipment_number,
                "name": None,
            })

        direct = self.db.query(InboundShipment.id, InboundShipment.shipment_number).filter(
            InboundShipment.attachment_id.in_(unique_aids)
        )
        for row in direct.all():
            key = ("packing_list", str(row.id))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "kind": "packing_list",
                "entity_id": str(row.id),
                "code": row.shipment_number,
                "name": None,
            })

        kind_order = {"product": 0, "promotion": 1, "form": 2, "packing_list": 3}
        targets.sort(key=lambda t: (kind_order.get(t["kind"], 9), t["code"] or ""))

        return {"attachment_count": len(unique_aids), "targets": targets}

    def bulk_set_attachment_type(
        self,
        attachment_ids: List[str],
        attachment_type_id: str,
    ) -> dict:
        """Set attachment_type_id on N attachments. No webhook side-effect.

        Used by single-edit (one ID in the list) and bulk-edit toolbar.
        """
        unique_aids = list(dict.fromkeys([a for a in attachment_ids if a]))
        if not unique_aids:
            raise handle_validation_error("No attachments in scope.")

        # Validate the type exists.
        type_id = (attachment_type_id or "").strip()
        if not type_id:
            raise handle_validation_error("attachment_type_id is required.")
        type_row = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.id == type_id)
            .first()
        )
        if not type_row:
            raise handle_validation_error("Invalid attachment_type_id.")

        count = (
            self.db.query(Attachment)
            .filter(Attachment.id.in_(unique_aids), Attachment.is_deleted == False)
            .update({"attachment_type_id": type_id}, synchronize_session=False)
        )
        self.db.commit()
        return {
            "updated_attachments": int(count or 0),
            "attachment_type_id": type_id,
        }

    def apply_bulk_access_levels(
        self,
        attachment_ids: List[str],
        access_levels: List[str],
        propagate_to_linked: bool,
    ) -> dict:
        """Set access_levels on attachments; optionally cascade to linked product links, promotions, forms, packing lists."""
        from sqlalchemy import update
        from app.services.contact_access_type_service import ContactAccessTypeService
        from app.models.product import ProductAttachment
        from app.models.marketing import Promotion, PromotionAttachment
        from app.models.forms import Form
        from app.models.procurement import InboundShipment
        from app.models.entity_attachment import EntityAttachmentLink

        access_svc = ContactAccessTypeService(self.db)
        validated = access_svc.validate_access_levels(access_levels, field_name="access_levels")

        unique_aids = list(dict.fromkeys([a for a in attachment_ids if a]))
        if not unique_aids:
            raise handle_validation_error("No attachments in scope.")

        count_att = (
            self.db.query(Attachment)
            .filter(Attachment.id.in_(unique_aids), Attachment.is_deleted == False)
            .update({"access_levels": validated}, synchronize_session=False)
        )

        propagated: dict = {
            "product_links": 0,
            "promotions": 0,
            "forms": 0,
            "packing_lists": 0,
        }

        if propagate_to_linked:
            r1 = self.db.execute(
                update(ProductAttachment)
                .where(ProductAttachment.attachment_id.in_(unique_aids))
                .values(access_levels=validated)
            )
            propagated["product_links"] = r1.rowcount or 0

            promo_ids = [
                str(x[0])
                for x in self.db.query(PromotionAttachment.promotion_id)
                .filter(PromotionAttachment.attachment_id.in_(unique_aids))
                .distinct()
                .all()
            ]
            if promo_ids:
                r2 = self.db.execute(
                    update(Promotion).where(Promotion.id.in_(promo_ids)).values(access_levels=validated)
                )
                propagated["promotions"] = r2.rowcount or 0

            r3 = self.db.execute(
                update(Form).where(Form.attachment_id.in_(unique_aids)).values(access_levels=validated)
            )
            propagated["forms"] = r3.rowcount or 0

            link_ids = [
                str(x[0])
                for x in self.db.query(EntityAttachmentLink.entity_id)
                .filter(
                    EntityAttachmentLink.attachment_id.in_(unique_aids),
                    EntityAttachmentLink.entity_type == "inbound_shipment",
                )
                .distinct()
                .all()
            ]
            direct_ids = [
                str(x[0])
                for x in self.db.query(InboundShipment.id)
                .filter(InboundShipment.attachment_id.in_(unique_aids))
                .all()
            ]
            ship_ids = list(dict.fromkeys(link_ids + direct_ids))
            if ship_ids:
                r4 = self.db.execute(
                    update(InboundShipment)
                    .where(InboundShipment.id.in_(ship_ids))
                    .values(access_levels=validated)
                )
                propagated["packing_lists"] = r4.rowcount or 0

        self.db.commit()
        return {"updated_attachments": count_att, "propagated": propagated if propagate_to_linked else None}

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
            if kind == "inbound_shipment":
                from app.models.procurement import InboundShipment
                row = self.db.query(InboundShipment).filter(InboundShipment.id == entity_id).first()
                return row.shipment_number if row else None
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
        # Validate access_levels against catalog or use default
        from app.services.contact_access_type_service import ContactAccessTypeService
        access_svc = ContactAccessTypeService(self.db)
        if attachment_dict.get("access_levels"):
            attachment_dict["access_levels"] = access_svc.validate_access_levels(
                attachment_dict["access_levels"], field_name="access_levels"
            )
        else:
            attachment_dict["access_levels"] = access_svc.get_default_access_levels()

        # Compute and set full_directory_path when directory_id is provided
        directory_id = attachment_dict.get("directory_id")
        if directory_id:
            dir_service = AttachmentDirectoryService(self.db)
            attachment_dict["full_directory_path"] = dir_service.get_full_directory_path(directory_id)
        else:
            attachment_dict["full_directory_path"] = None
        
        attachment = Attachment(**attachment_dict)
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        
        # Reload with relationship
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment.id).first()
        publish_embedding_event(
            self.db,
            source_type="attachment",
            source_id=attachment.id,
            source_key=attachment.original_filename,
            source_updated_at=attachment.created_at,
            event_type="attachment.created",
            changed_fields=["original_filename", "description", "entity_type", "entity_id", "access_levels"],
            triggered_by=str(uploaded_by) if uploaded_by else None,
        )
        return attachment
    
    def update_attachment(self, attachment_id: str, attachment_data: AttachmentUpdate):
        """Update an attachment. Recalculates full_directory_path when directory_id changes."""
        attachment = self.get_attachment(attachment_id)
        
        update_data = attachment_data.model_dump(exclude_unset=True)
        if "access_levels" in update_data and update_data["access_levels"]:
            from app.services.contact_access_type_service import ContactAccessTypeService
            access_svc = ContactAccessTypeService(self.db)
            update_data["access_levels"] = access_svc.validate_access_levels(
                update_data["access_levels"], field_name="access_levels"
            )

        # Recalculate full_directory_path when directory_id is updated
        if "directory_id" in update_data:
            new_directory_id = update_data["directory_id"]
            dir_service = AttachmentDirectoryService(self.db)
            update_data["full_directory_path"] = dir_service.get_full_directory_path(new_directory_id)
        
        for key, value in update_data.items():
            setattr(attachment, key, value)
        
        self.db.commit()
        self.db.refresh(attachment)
        publish_embedding_event(
            self.db,
            source_type="attachment",
            source_id=attachment.id,
            source_key=attachment.original_filename,
            source_updated_at=attachment.created_at,
            event_type="attachment.updated",
            changed_fields=list(update_data.keys()),
        )
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

    def archive_attachment(self, attachment_id: str, archived_by: str):
        """Archive an attachment (soft delete). Data remains for retention."""
        attachment = self.get_attachment(attachment_id)
        from datetime import datetime
        attachment.is_deleted = True
        attachment.deleted_at = datetime.utcnow()
        attachment.deleted_by = archived_by
        self.db.commit()
        return {"message": "Attachment archived successfully"}

    def archive_attachments(self, attachment_ids: list[str], archived_by: str):
        """Archive multiple attachments by ID. Skips not-found and already-archived."""
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
                attachment.deleted_by = archived_by
                count += 1
        self.db.commit()
        return {"message": f"{count} attachment(s) archived successfully", "archived_count": count}

    def restore_attachment(self, attachment_id: str):
        """Restore an archived attachment."""
        attachment = self.get_attachment(attachment_id)
        attachment.is_deleted = False
        attachment.deleted_at = None
        attachment.deleted_by = None
        self.db.commit()
        return {"message": "Attachment restored successfully"}

    def restore_attachments_in_directories(self, directory_ids: list[str]) -> int:
        """Restore all archived attachments whose directory_id is in the given list. Returns count."""
        if not directory_ids:
            return 0
        q = self.db.query(Attachment).filter(
            Attachment.directory_id.in_(directory_ids),
            Attachment.is_deleted == True,
        )
        count = q.update(
            {
                Attachment.is_deleted: False,
                Attachment.deleted_at: None,
                Attachment.deleted_by: None,
            },
            synchronize_session=False,
        )
        return count

    def _s3_key_from_file_path(self, file_path: str) -> str:
        """Extract S3 key from file_path (URL or raw key)."""
        from urllib.parse import urlparse
        if file_path.startswith("https://"):
            parsed = urlparse(file_path)
            return parsed.path.lstrip("/")
        return file_path

    def delete_attachment(self, attachment_id: str, deleted_by: str):
        """Hard delete an attachment (permanent). Removes DB record; storage delete runs in background."""
        attachment = self.get_attachment(attachment_id)
        file_path = attachment.file_path
        provider = getattr(attachment, "storage_provider", None) or "s3"
        keys = [self._s3_key_from_file_path(file_path)] if file_path else []
        self.db.delete(attachment)
        self.db.commit()
        if keys:
            try:
                from app.tasks.s3_tasks import delete_storage_files
                from app.services.queue_service import enqueue_job
                enqueue_job(
                    delete_storage_files,
                    [(provider, k) for k in keys],
                    queue_name="imports",
                    job_timeout=300,
                )
            except Exception as e:
                logger.warning("Failed to enqueue storage delete for %s: %s", attachment_id, e)
        return {"message": "Attachment deleted successfully"}

    def delete_attachments(self, attachment_ids: list[str], deleted_by: str):
        """Hard delete multiple attachments by ID. Skips not-found. Storage deletes run in background."""
        items: list[tuple[str, str]] = []  # (provider, key)
        count = 0
        for aid in attachment_ids:
            attachment = self.db.query(Attachment).filter(Attachment.id == aid).first()
            if attachment:
                if attachment.file_path:
                    items.append(
                        (
                            getattr(attachment, "storage_provider", None) or "s3",
                            self._s3_key_from_file_path(attachment.file_path),
                        )
                    )
                self.db.delete(attachment)
                count += 1
        self.db.commit()
        if items:
            try:
                from app.tasks.s3_tasks import delete_storage_files
                from app.services.queue_service import enqueue_job
                enqueue_job(delete_storage_files, items, queue_name="imports", job_timeout=600)
            except Exception as e:
                logger.warning("Failed to enqueue storage deletes for %s keys: %s", len(items), e)
        return {"message": f"{count} attachment(s) deleted successfully", "deleted_count": count}

    def archive_attachments_in_directories(self, directory_ids: list[str], archived_by: str) -> int:
        """Archive all non-archived attachments whose directory_id is in the given list. Returns count."""
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
                Attachment.deleted_by: archived_by,
            },
            synchronize_session=False,
        )
        self.db.commit()
        return count
    
    def get_file_content(self, attachment_id: str) -> bytes:
        """Retrieve file bytes from whichever storage provider hosts this attachment."""
        attachment = self.get_attachment(attachment_id)
        if not attachment.file_path:
            raise Exception("Attachment has no file path")

        from app.services.storage_router import extract_key, get_backend

        provider = getattr(attachment, "storage_provider", None)
        key = extract_key(attachment.file_path)
        if not key:
            raise Exception("Could not extract storage key from file_path")
        try:
            return get_backend(provider).download_file(key)
        except Exception as e:
            raise Exception(f"Failed to retrieve file from storage: {str(e)}")
