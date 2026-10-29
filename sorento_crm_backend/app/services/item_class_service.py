"""Item Class reference service (ITEM-CLASS): the `CountryService` CRUD shape, company scoped
like brands. AutoCount back-creates rows through the products ingest; this is the hand path."""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.product import ItemClass, Product
from app.schemas.item_class import ItemClassCreate, ItemClassUpdate
from app.services.error_handler import handle_conflict, handle_not_found


class ItemClassService:
    def __init__(self, db: Session):
        self.db = db

    def list_item_classes(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        sort_dir: Optional[str] = None,
    ):
        q = self.db.query(ItemClass)
        if query:
            q = q.filter(
                or_(
                    ItemClass.item_class_code.ilike(f"%{query}%"),
                    ItemClass.item_class_name.ilike(f"%{query}%"),
                )
            )
        sort_map = {
            "item_class_code": ItemClass.item_class_code,
            "item_class_name": ItemClass.item_class_name,
            "is_active": ItemClass.is_active,
            "created_at": ItemClass.created_at,
        }
        sort_column = sort_map.get(sort, ItemClass.item_class_name)
        q = q.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc(), ItemClass.id)

        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        counts = dict(
            self.db.query(Product.item_class_id, func.count(Product.id))
            .filter(Product.item_class_id.in_([r.id for r in rows]))
            .group_by(Product.item_class_id)
            .all()
        ) if rows else {}
        data = [
            {
                "id": r.id,
                "item_class_code": r.item_class_code,
                "item_class_name": r.item_class_name,
                "description": r.description,
                "is_active": r.is_active,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "product_count": counts.get(r.id, 0),
            }
            for r in rows
        ]
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def select(self, query: Optional[str] = None, brand_id: Optional[str] = None):
        """Active classes for a dropdown. `brand_id` keeps the classes some product of that
        brand carries (the contact card offers only classes that can narrow the brand)."""
        q = self.db.query(ItemClass).filter(ItemClass.is_active.is_(True))
        if query:
            q = q.filter(
                or_(
                    ItemClass.item_class_code.ilike(f"%{query}%"),
                    ItemClass.item_class_name.ilike(f"%{query}%"),
                )
            )
        if brand_id:
            used = (
                self.db.query(Product.item_class_id)
                .filter(Product.brand_id == brand_id, Product.item_class_id.isnot(None))
                .distinct()
            )
            q = q.filter(ItemClass.id.in_(used))
        return q.order_by(ItemClass.item_class_name.asc()).limit(200).all()

    def get(self, item_class_id: str) -> ItemClass:
        row = self.db.query(ItemClass).filter(ItemClass.id == item_class_id).first()
        if not row:
            raise handle_not_found("Item Class", item_class_id)
        return row

    def get_detail(self, item_class_id: str) -> dict:
        row = self.get(item_class_id)
        count = self.db.query(func.count(Product.id)).filter(Product.item_class_id == row.id).scalar() or 0
        return {
            "id": row.id,
            "item_class_code": row.item_class_code,
            "item_class_name": row.item_class_name,
            "description": row.description,
            "is_active": row.is_active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "product_count": count,
        }

    def _duplicate_code(self, code: str, company_id: Optional[str], *, exclude_id: Optional[str] = None) -> bool:
        """Codes are unique per company, so only the target company's rows count (review S4)."""
        q = self.db.query(ItemClass.id).filter(
            func.lower(func.trim(ItemClass.item_class_code)) == code.strip().lower()
        )
        if company_id:
            q = q.filter(ItemClass.company_id == str(company_id))
        if exclude_id:
            q = q.filter(ItemClass.id != exclude_id)
        return q.first() is not None

    def create(self, data: ItemClassCreate) -> ItemClass:
        from app.models.base import get_company_scope
        from app.services.company_scope import resolve_write_company_id

        target = resolve_write_company_id(get_company_scope(self.db), ambiguous=None)
        if self._duplicate_code(data.item_class_code, target):
            raise handle_conflict("An item class with this code already exists.")
        payload = data.model_dump()
        payload["item_class_code"] = payload["item_class_code"].strip()
        row = ItemClass(**payload)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, item_class_id: str, data: ItemClassUpdate) -> ItemClass:
        row = self.get(item_class_id)
        update_data = data.model_dump(exclude_unset=True)
        if "item_class_code" in update_data and update_data["item_class_code"] is not None:
            if self._duplicate_code(update_data["item_class_code"], row.company_id, exclude_id=item_class_id):
                raise handle_conflict("An item class with this code already exists.")
            update_data["item_class_code"] = update_data["item_class_code"].strip()
        for key, value in update_data.items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, item_class_id: str) -> dict:
        """Hard delete; products keep existing with no class (FK SET NULL). Refused while a
        contact's access is narrowed to this class: dropping it would leave that brand
        narrowed to nothing, and the contact's card would read as "every class"."""
        from sqlalchemy import text

        row = self.get(item_class_id)
        with company_scope(self.db, None):
            contacts = self.db.execute(
                text(
                    "SELECT count(*) FROM respond_contacts rc, jsonb_each(rc.brand_class_ids) e "
                    "WHERE rc.brand_class_ids IS NOT NULL AND jsonb_typeof(rc.brand_class_ids) = 'object' "
                    "AND jsonb_typeof(e.value) = 'array' AND e.value ? :cid "
                    # A list for a brand no longer in brand_ids narrows nothing (review S2).
                    "AND e.key = ANY(rc.brand_ids::text[])"
                ),
                {"cid": str(row.id)},
            ).scalar() or 0
        if contacts:
            raise handle_conflict(
                f"Cannot delete this item class: {contacts} contact{'s' if contacts != 1 else ''} "
                "limit access to it."
            )
        self.db.delete(row)
        self.db.commit()
        return {"success": True}
