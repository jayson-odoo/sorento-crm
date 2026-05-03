"""Product service for business logic."""
from datetime import datetime
import re
import uuid
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from typing import Any, Optional, List, Callable, Tuple
from decimal import Decimal
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure, ProductAttachment


# Match three numbers separated by 'x' / 'X' / '×' (with optional spaces) and optional unit (mm/cm/m).
# Examples matched: '650x450x210MM', '650 x 450 x 210mm', '(650X450X210)', '12.5x10x5 cm'.
# The negative-lookahead (?<!\d) avoids stitching onto a longer numeric run from a product code.
_DIMENSION_LXWXH_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)"
    r"(?:\s*(mm|cm|m|MM|CM|M)\b|(?![0-9]))",
)
_UNIT_TO_MM: dict[str, Decimal] = {
    "": Decimal("1"),
    "mm": Decimal("1"),
    "cm": Decimal("10"),
    "m": Decimal("1000"),
}


def parse_dimensions_from_description(
    description: Optional[str],
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Extract LxWxH (in mm) from a product description.

    Returns (length_mm, width_mm, height_mm). All None if no LxWxH triplet is found.
    Unit is normalized to mm: 'cm' -> x10, 'm' -> x1000, otherwise mm assumed.
    Convention: dimensions are written length × width × height in the source description.
    """
    if not description:
        return (None, None, None)
    m = _DIMENSION_LXWXH_PATTERN.search(description)
    if not m:
        return (None, None, None)
    raw_l, raw_w, raw_h, unit = m.groups()
    factor = _UNIT_TO_MM.get((unit or "").lower(), Decimal("1"))
    try:
        q = Decimal("0.01")
        return (
            (Decimal(raw_l) * factor).quantize(q),
            (Decimal(raw_w) * factor).quantize(q),
            (Decimal(raw_h) * factor).quantize(q),
        )
    except Exception:
        return (None, None, None)
from app.models.procurement import ProductSupplier, Supplier
from app.models.resources import Attachment, AttachmentType
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductCategoryCreate, ProductCategoryUpdate,
    BrandCreate, BrandUpdate, UnitOfMeasureCreate, UnitOfMeasureUpdate,
    ProductAttachmentCreate, ProductAttachmentUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.schemas.common import PaginationResponse
from app.models.user import SystemSetting
from app.services.embedding_events import publish_embedding_event
from app.services.identifier_resolver import resolve_identifier


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
        length_min: Optional[float] = None,
        length_max: Optional[float] = None,
        width_min: Optional[float] = None,
        width_max: Optional[float] = None,
        height_min: Optional[float] = None,
        height_max: Optional[float] = None,
        any_dimension_min: Optional[float] = None,
        any_dimension_max: Optional[float] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        advanced_filter_clause: Optional[Any] = None,
    ):
        """List products with filtering and pagination."""
        # Build query
        q = self.db.query(Product)
        
        # Apply filters
        filters = []

        category_ids = resolve_identifier(
            self.db,
            category_id,
            ProductCategory,
            code_fields=("category_code", "category_name"),
        )
        if category_ids is not None:
            if not category_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            filters.append(Product.category_id.in_(category_ids))

        brand_ids = resolve_identifier(
            self.db,
            brand_id,
            Brand,
            code_fields=("brand_code", "brand_name"),
        )
        if brand_ids is not None:
            if not brand_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            filters.append(Product.brand_id.in_(brand_ids))
        
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

        # Per-axis dimension filters (mm). Length/width/height map to dimensions_length/width/height.
        if length_min is not None:
            filters.append(Product.dimensions_length >= Decimal(str(length_min)))
        if length_max is not None:
            filters.append(Product.dimensions_length <= Decimal(str(length_max)))
        if width_min is not None:
            filters.append(Product.dimensions_width >= Decimal(str(width_min)))
        if width_max is not None:
            filters.append(Product.dimensions_width <= Decimal(str(width_max)))
        if height_min is not None:
            filters.append(Product.dimensions_height >= Decimal(str(height_min)))
        if height_max is not None:
            filters.append(Product.dimensions_height <= Decimal(str(height_max)))

        # Generic "any dimension" filter: matches when ANY of L/W/H is in the range.
        # Use this when the user does not care which axis (e.g. 'dimensions > 300mm').
        if any_dimension_min is not None:
            v = Decimal(str(any_dimension_min))
            filters.append(
                or_(
                    Product.dimensions_length >= v,
                    Product.dimensions_width >= v,
                    Product.dimensions_height >= v,
                )
            )
        if any_dimension_max is not None:
            v = Decimal(str(any_dimension_max))
            filters.append(
                or_(
                    Product.dimensions_length <= v,
                    Product.dimensions_width <= v,
                    Product.dimensions_height <= v,
                )
            )
        
        if query:
            term = f"%{query.strip()}%"
            filters.append(
                or_(
                    Product.product_code.ilike(term),
                    Product.product_name.ilike(term),
                    Product.description.ilike(term),
                )
            )

        if advanced_filter_clause is not None:
            filters.append(advanced_filter_clause)

        if filters:
            q = q.filter(and_(*filters))
        
        # Get total count
        total = q.count()
        
        # Apply sorting
        # GREATEST / LEAST give us a virtual "max axis" / "min axis" per row so the LLM can ask
        # for the biggest or smallest product in one call (sort=largest_dimension dir=desc).
        # NULL dimensions sort to the bottom on desc and top on asc — handled with NULLS LAST/FIRST.
        largest_dim = func.greatest(
            Product.dimensions_length,
            Product.dimensions_width,
            Product.dimensions_height,
        )
        smallest_dim = func.least(
            Product.dimensions_length,
            Product.dimensions_width,
            Product.dimensions_height,
        )
        sort_map = {
            "created_at": Product.created_at,
            "updated_at": Product.updated_at,
            "product_code": Product.product_code,
            "product_name": Product.product_name,
            "list_price": Product.list_price,
            "price": Product.list_price,
            "cost_price": Product.cost_price,
            "invoice_price": Product.invoice_price,
            "is_active": Product.is_active,
            "dimensions_length": Product.dimensions_length,
            "length": Product.dimensions_length,
            "dimensions_width": Product.dimensions_width,
            "width": Product.dimensions_width,
            "dimensions_height": Product.dimensions_height,
            "height": Product.dimensions_height,
            "largest_dimension": largest_dim,
            "smallest_dimension": smallest_dim,
        }
        sort_column = sort_map.get(sort_field, Product.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc().nulls_last())
        else:
            q = q.order_by(sort_column.asc().nulls_last())
        
        # Apply pagination
        offset = (page - 1) * limit
        # Eager-load relations referenced by ProductResponse to avoid N+1 lazy loads
        # during Pydantic serialization.
        products = (
            q.options(
                joinedload(Product.category),
                joinedload(Product.brand),
                joinedload(Product.base_uom),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

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
        """Get a single product by UUID or product_code (SKU)."""
        resolved_ids = resolve_identifier(
            self.db,
            product_id,
            Product,
            code_fields=("product_code",),
        )
        if not resolved_ids:
            raise handle_not_found("Product", product_id)
        product = (
            self.db.query(Product)
            .options(joinedload(Product.category), joinedload(Product.brand), joinedload(Product.base_uom))
            .filter(Product.id.in_(resolved_ids))
            .first()
        )
        if not product:
            raise handle_not_found("Product", product_id)
        return product
    
    def _system_settings_row(self) -> Optional[SystemSetting]:
        return self.db.query(SystemSetting).first()

    def _default_standard_lead_time_days(self) -> int:
        row = self._system_settings_row()
        if row is not None:
            try:
                n = int(row.default_product_standard_lead_time_days)
            except (TypeError, ValueError):
                n = 90
        else:
            n = 90
        return max(0, n)

    def _resolve_default_supplier_for_new_product(self) -> Optional[Supplier]:
        """
        Supplier for auto-created product_suppliers rows.
        Uses system_settings.default_product_supplier_id when set and valid; else oldest supplier by created_at.
        """
        row = self._system_settings_row()
        sid = (row.default_product_supplier_id or "").strip() if row else ""
        if sid:
            s = self.db.query(Supplier).filter(Supplier.id == sid).first()
            if s:
                return s
        return (
            self.db.query(Supplier)
            .order_by(Supplier.created_at.asc(), Supplier.id.asc())
            .first()
        )

    def _ensure_default_supplier_lead_time(self, product_id: str, lead_time_days: Optional[int] = None) -> None:
        """Link product to the configured default supplier with standard lead time (see app config)."""
        if lead_time_days is None:
            days = self._default_standard_lead_time_days()
        else:
            try:
                days = max(0, int(lead_time_days))
            except (TypeError, ValueError):
                days = self._default_standard_lead_time_days()
        supplier = self._resolve_default_supplier_for_new_product()
        if not supplier:
            return
        existing = self.db.query(ProductSupplier).filter(
            ProductSupplier.product_id == product_id,
            ProductSupplier.supplier_id == supplier.id,
        ).first()
        if existing:
            if existing.standard_lead_time_days != days:
                existing.standard_lead_time_days = days
                self.db.flush()
            return
        self.db.add(
            ProductSupplier(
                product_id=product_id,
                supplier_id=supplier.id,
                standard_lead_time_days=days,
            )
        )
        self.db.flush()

    def create_product(self, product_data: ProductCreate, created_by: str):
        """Create a new product."""
        # Trim product_code defensively (schema validator also does this; belt-and-suspenders)
        product_code = (product_data.product_code or "").strip()
        # Check if product_code already exists
        existing = self.db.query(Product).filter(Product.product_code == product_code).first()
        if existing:
            raise handle_conflict("Product code already exists. Please use a different code.")
        
        data = product_data.model_dump()
        data["product_code"] = product_code
        # Auto-populate dimensions from description LxWxH pattern when caller did not supply them.
        parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(data.get("description"))
        if parsed_l is not None and data.get("dimensions_length") is None:
            data["dimensions_length"] = parsed_l
        if parsed_w is not None and data.get("dimensions_width") is None:
            data["dimensions_width"] = parsed_w
        if parsed_h is not None and data.get("dimensions_height") is None:
            data["dimensions_height"] = parsed_h
        product = Product(**data, created_by=created_by)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self._ensure_default_supplier_lead_time(product.id)
        self.db.commit()
        self.db.refresh(product)
        publish_embedding_event(
            self.db,
            source_type="product",
            source_id=product.id,
            source_key=product.product_code,
            source_updated_at=product.updated_at or product.created_at,
            event_type="product.created",
            changed_fields=["product_code", "product_name", "description", "category_id", "brand_id", "is_active"],
            triggered_by=created_by,
        )
        return product
    
    def update_product(self, product_id: str, product_data: ProductUpdate, updated_by: str):
        """Update a product."""
        product = self.get_product(product_id)
        
        update_data = product_data.model_dump(exclude_unset=True)
        if update_data:
            update_data["updated_by"] = updated_by
            update_data["updated_at"] = datetime.utcnow()
            # When description is being updated, re-parse LxWxH and populate dimension columns
            # that the caller did NOT explicitly set in the same payload (explicit user value wins).
            if "description" in update_data:
                parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(update_data.get("description"))
                if parsed_l is not None and "dimensions_length" not in update_data:
                    update_data["dimensions_length"] = parsed_l
                if parsed_w is not None and "dimensions_width" not in update_data:
                    update_data["dimensions_width"] = parsed_w
                if parsed_h is not None and "dimensions_height" not in update_data:
                    update_data["dimensions_height"] = parsed_h
            for key, value in update_data.items():
                setattr(product, key, value)
            
            self.db.commit()
            self.db.refresh(product)
            publish_embedding_event(
                self.db,
                source_type="product",
                source_id=product.id,
                source_key=product.product_code,
                source_updated_at=product.updated_at or product.created_at,
                event_type="product.updated" if product.is_active else "product.deactivated",
                changed_fields=list(update_data.keys()),
                triggered_by=updated_by,
            )
        
        return product
    
    def delete_product(self, product_id: str):
        """Delete a product."""
        product = self.get_product(product_id)
        self.db.delete(product)
        self.db.commit()
        return {"message": "Product deleted successfully"}

    def bulk_delete_products(self, product_ids: List[str]):
        """Delete multiple products by ID."""
        if not product_ids:
            return {"message": "No products to delete", "deleted_count": 0}
        deleted = self.db.query(Product).filter(Product.id.in_(product_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()
        return {"message": f"Deleted {deleted} product(s)", "deleted_count": deleted}

    def _get_default_uom_id(self) -> str:
        """Return a default UOM id for bulk import (e.g. EA or first available)."""
        uom = (
            self.db.query(UnitOfMeasure)
            .filter(UnitOfMeasure.uom_code.ilike("ea"))
            .first()
        )
        if uom:
            return uom.id
        uom = self.db.query(UnitOfMeasure).first()
        if not uom:
            raise ValueError("No unit of measure found. Create at least one UOM (e.g. EA) for product import.")
        return uom.id

    def _resolve_category_id(self, item_group: Optional[str]) -> Optional[str]:
        """Resolve category by item_group (match category_code or category_name)."""
        if not item_group or not str(item_group).strip():
            return None
        q = str(item_group).strip()
        cat = (
            self.db.query(ProductCategory)
            .filter(
                or_(
                    ProductCategory.category_code.ilike(q),
                    ProductCategory.category_name.ilike(q),
                )
            )
            .first()
        )
        return cat.id if cat else None

    def _resolve_brand_id(self, item_brand: Optional[str]) -> Optional[str]:
        """Resolve brand by item_brand (match brand_code or brand_name)."""
        if not item_brand or not str(item_brand).strip():
            return None
        q = str(item_brand).strip()
        brand = (
            self.db.query(Brand)
            .filter(
                or_(
                    Brand.brand_code.ilike(q),
                    Brand.brand_name.ilike(q),
                )
            )
            .first()
        )
        return brand.id if brand else None

    BULK_IMPORT_CHUNK_SIZE = 500  # Commit every N rows; fewer round-trips
    _BULK_FETCH_CODES_BATCH = 5000  # Max product_codes per IN query

    def _build_category_map(self) -> dict:
        """Build item_group -> category_id map from all categories (code and name, case-insensitive)."""
        rows = self.db.query(ProductCategory.id, ProductCategory.category_code, ProductCategory.category_name).all()
        m = {}
        for id_, code, name in rows:
            if code:
                m[str(code).strip().lower()] = id_
            if name:
                m[str(name).strip().lower()] = id_
        return m

    def _build_brand_map(self) -> dict:
        """Build item_brand -> brand_id map from all brands (code and name, case-insensitive)."""
        rows = self.db.query(Brand.id, Brand.brand_code, Brand.brand_name).all()
        m = {}
        for id_, code, name in rows:
            if code:
                m[str(code).strip().lower()] = id_
            if name:
                m[str(name).strip().lower()] = id_
        return m

    def _fetch_existing_products_by_codes(self, codes: List[str]) -> dict:
        """Fetch existing products by product_code; return dict code -> Product."""
        if not codes:
            return {}
        seen = set()
        unique = [c for c in codes if c and c not in seen and not seen.add(c)]
        result = {}
        for i in range(0, len(unique), self._BULK_FETCH_CODES_BATCH):
            batch = unique[i : i + self._BULK_FETCH_CODES_BATCH]
            products = self.db.query(Product).filter(Product.product_code.in_(batch)).all()
            for p in products:
                result[p.product_code] = p
        return result

    def _fetch_product_ids_with_configured_lead_time(self, product_ids: List[str]) -> set:
        """Product IDs that have at least one product_suppliers row with standard_lead_time_days set."""
        if not product_ids:
            return set()
        seen: set = set()
        unique: List[str] = []
        for pid in product_ids:
            if pid and pid not in seen:
                seen.add(pid)
                unique.append(pid)
        out: set = set()
        for i in range(0, len(unique), self._BULK_FETCH_CODES_BATCH):
            batch = unique[i : i + self._BULK_FETCH_CODES_BATCH]
            rows = (
                self.db.query(ProductSupplier.product_id)
                .filter(
                    ProductSupplier.product_id.in_(batch),
                    ProductSupplier.standard_lead_time_days.isnot(None),
                )
                .distinct()
                .all()
            )
            for (pid,) in rows:
                out.add(pid)
        return out

    def bulk_import_products(
        self,
        products_data: List[dict],
        user_id: str,
        on_progress: Optional[Callable[[int, int, int, int], None]] = None,
    ) -> dict:
        """
        Bulk import products from Excel-style rows.
        Expects each row: product_code, product_name?, description?, item_group?, item_brand?, list_price?, is_active?
        item_group is matched to category (code or name); item_brand to brand (code or name).
        Creates or updates by product_code. Uses default UOM for new products.
        On update, if the product has no product_suppliers row with standard_lead_time_days set, applies the same default supplier/lead time as new products.
        Optimized: pre-loads categories, brands, and existing products to avoid per-row queries.
        on_progress: optional callback(processed, successful, failed, skipped) called at chunk boundaries for real-time UI.
        """
        created = 0
        updated = 0
        errors = []
        default_uom_id = self._get_default_uom_id()
        chunk_size = self.BULK_IMPORT_CHUNK_SIZE

        # One-time lookups (3 queries total instead of 3 per row)
        category_map = self._build_category_map()
        brand_map = self._build_brand_map()
        all_codes = []
        for row in products_data:
            code = (row.get("product_code") or row.get("Product Code") or row.get("Item Code") or "").strip()
            if code:
                all_codes.append(code)
        existing_by_code = self._fetch_existing_products_by_codes(all_codes)
        products_with_lead_time = self._fetch_product_ids_with_configured_lead_time(
            [p.id for p in existing_by_code.values()]
        )

        for idx, row in enumerate(products_data, start=1):
            try:
                product_code = (row.get("product_code") or row.get("Product Code") or row.get("Item Code") or "").strip()
                if not product_code:
                    errors.append(f"Row {idx}: product_code / Item Code is required")
                    continue
                product_name = (row.get("product_name") or row.get("Product Name") or row.get("Item Code") or product_code).strip() or product_code
                description = row.get("description") or row.get("Description") or ""
                desc2 = row.get("desc2") or row.get("Desc 2") or ""
                if desc2:
                    description = f"{description} {desc2}".strip()
                item_group = (row.get("item_group") or row.get("Item Group") or "").strip() or None
                item_brand = (row.get("item_brand") or row.get("Item Brand") or "").strip() or None
                raw_price = row.get("list_price") or row.get("Price") or row.get("price")
                try:
                    if raw_price is None or str(raw_price).strip() == "":
                        list_price = Decimal("0")
                    else:
                        list_price = Decimal(str(raw_price))
                    if list_price < 0:
                        errors.append(
                            f"Row {idx} ({product_code}): List price cannot be negative, got '{raw_price}'"
                        )
                        continue
                except Exception:
                    errors.append(
                        f"Row {idx} ({product_code}): Price must be a valid number, got '{raw_price}'"
                    )
                    continue
                raw_active = row.get("is_active") or row.get("Is Active") or row.get("Is active")
                is_active = True
                if raw_active is not None and str(raw_active).strip().upper() in ("F", "FALSE", "0", "N", "NO"):
                    is_active = False

                category_id = None
                if item_group:
                    category_id = category_map.get(str(item_group).strip().lower())
                if item_group and not category_id:
                    errors.append(f"Row {idx} ({product_code}): no category found for item_group '{item_group}'")
                    continue
                if not category_id:
                    errors.append(f"Row {idx} ({product_code}): item_group is required and must match a category")
                    continue

                brand_id = None
                if item_brand:
                    brand_id = brand_map.get(str(item_brand).strip().lower())
                if item_brand and not brand_id:
                    errors.append(f"Row {idx} ({product_code}): no brand found for item_brand '{item_brand}'")
                    continue

                parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(description)

                existing = existing_by_code.get(product_code)
                if existing:
                    existing.product_name = product_name
                    existing.description = description or None
                    existing.category_id = category_id
                    existing.brand_id = brand_id
                    existing.list_price = list_price
                    existing.is_active = is_active
                    existing.updated_by = user_id
                    existing.updated_at = datetime.utcnow()
                    if parsed_l is not None:
                        existing.dimensions_length = parsed_l
                    if parsed_w is not None:
                        existing.dimensions_width = parsed_w
                    if parsed_h is not None:
                        existing.dimensions_height = parsed_h
                    if existing.id not in products_with_lead_time:
                        self._ensure_default_supplier_lead_time(existing.id)
                        products_with_lead_time.add(existing.id)
                    updated += 1
                else:
                    product = Product(
                        product_code=product_code,
                        product_name=product_name,
                        description=description or None,
                        category_id=category_id,
                        brand_id=brand_id,
                        base_uom_id=default_uom_id,
                        list_price=list_price,
                        is_active=is_active,
                        dimensions_length=parsed_l,
                        dimensions_width=parsed_w,
                        dimensions_height=parsed_h,
                        created_by=user_id,
                    )
                    self.db.add(product)
                    self.db.flush()  # get product.id for default supplier link
                    self._ensure_default_supplier_lead_time(product.id)
                    products_with_lead_time.add(product.id)
                    existing_by_code[product_code] = product  # avoid duplicate add if same code again
                    created += 1

                if idx % chunk_size == 0:
                    self.db.commit()
                    if on_progress:
                        on_progress(idx, created + updated, len(errors), 0)
            except Exception as e:
                self.db.rollback()
                errors.append(f"Row {idx} ({row.get('product_code', '')}): {str(e)}")
                if idx % chunk_size == 0:
                    self.db.commit()
                    if on_progress:
                        on_progress(idx, created + updated, len(errors), 0)

        self.db.commit()
        if created or updated:
            touched = (
                self.db.query(Product.id, Product.product_code, Product.updated_at, Product.created_at)
                .filter(Product.product_code.in_(all_codes))
                .all()
            )
            for pid, pcode, updated_at, created_at in touched:
                publish_embedding_event(
                    self.db,
                    source_type="product",
                    source_id=pid,
                    source_key=pcode,
                    source_updated_at=updated_at or created_at,
                    event_type="product.updated",
                    changed_fields=["bulk_import"],
                    triggered_by=user_id,
                )
        if on_progress:
            on_progress(len(products_data), created + updated, len(errors), 0)
        return {"created": created, "updated": updated, "errors": errors}

    def validate_products_import(self, products_data: List[dict]) -> dict:
        """
        Run the same validation as bulk_import_products without writing to DB.
        Returns errors, warnings, and summary (would_create, would_update counts).
        """
        errors = []
        warnings = []
        would_create = 0
        would_update = 0
        category_map = self._build_category_map()
        brand_map = self._build_brand_map()
        all_codes = []
        for row in products_data:
            code = (row.get("product_code") or row.get("Product Code") or row.get("Item Code") or "").strip()
            if code:
                all_codes.append(code)
        existing_by_code = self._fetch_existing_products_by_codes(all_codes)

        for idx, row in enumerate(products_data, start=1):
            try:
                product_code = (row.get("product_code") or row.get("Product Code") or row.get("Item Code") or "").strip()
                if not product_code:
                    errors.append(f"Row {idx}: product_code / Item Code is required")
                    continue
                product_name = (row.get("product_name") or row.get("Product Name") or row.get("Item Code") or product_code).strip() or product_code
                item_group = (row.get("item_group") or row.get("Item Group") or "").strip() or None
                item_brand = (row.get("item_brand") or row.get("Item Brand") or "").strip() or None
                raw_price = row.get("list_price") or row.get("Price") or row.get("price")
                try:
                    if raw_price is None or str(raw_price).strip() == "":
                        list_price = Decimal("0")
                    else:
                        list_price = Decimal(str(raw_price))
                    if list_price < 0:
                        errors.append(
                            f"Row {idx} ({product_code}): List price cannot be negative, got '{raw_price}'"
                        )
                        continue
                except Exception:
                    errors.append(
                        f"Row {idx} ({product_code}): Price must be a valid number, got '{raw_price}'"
                    )
                    continue

                category_id = None
                if item_group:
                    category_id = category_map.get(str(item_group).strip().lower())
                if item_group and not category_id:
                    errors.append(f"Row {idx} ({product_code}): no category found for item_group '{item_group}'")
                    continue
                if not category_id:
                    errors.append(f"Row {idx} ({product_code}): item_group is required and must match a category")
                    continue

                brand_id = None
                if item_brand:
                    brand_id = brand_map.get(str(item_brand).strip().lower())
                if item_brand and not brand_id:
                    errors.append(f"Row {idx} ({product_code}): no brand found for item_brand '{item_brand}'")
                    continue

                existing = existing_by_code.get(product_code)
                if existing:
                    would_update += 1
                else:
                    would_create += 1
            except Exception as e:
                errors.append(f"Row {idx} ({row.get('product_code', '')}): {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "total_rows": len(products_data),
                "would_create": would_create,
                "would_update": would_update,
                "error_count": len(errors),
            },
        }


class ProductCategoryService:
    """Service for product category operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_categories(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List product categories. Ordered by display_order asc, then category_name asc."""
        q = self.db.query(ProductCategory)
        
        if query:
            q = q.filter(
                or_(
                    ProductCategory.category_code.ilike(f"%{query}%"),
                    ProductCategory.category_name.ilike(f"%{query}%")
                )
            )
        
        q = q.order_by(ProductCategory.display_order.asc(), ProductCategory.category_name.asc())
        total = q.count()
        offset = (page - 1) * limit
        categories = q.offset(offset).limit(limit).all()
        
        return {
            "data": categories,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_category(self, category_id: str):
        """Get a category by UUID or category_code/name."""
        resolved_ids = resolve_identifier(
            self.db,
            category_id,
            ProductCategory,
            code_fields=("category_code", "category_name"),
        )
        if not resolved_ids:
            raise handle_not_found("Category", category_id)
        category = self.db.query(ProductCategory).filter(ProductCategory.id.in_(resolved_ids)).first()
        if not category:
            raise handle_not_found("Category", category_id)
        return category
    
    def get_categories_tree(self):
        """Get product categories as a tree structure (includes both active and inactive)."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import func
        
        # Get all categories, active and inactive (display_order asc, then category_name asc)
        categories = self.db.query(ProductCategory).order_by(
            ProductCategory.display_order.asc(), ProductCategory.category_name.asc()
        ).all()
        
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
        
        # Sort by display_order asc, then category_name asc
        def sort_key(cat):
            return (cat.get("display_order") or 0, (cat.get("category_name") or "").lower())

        def sort_children(cat):
            if cat["children"]:
                cat["children"].sort(key=sort_key)
                for child in cat["children"]:
                    sort_children(child)

        root_categories.sort(key=sort_key)
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

    def delete_category(self, category_id: str):
        """Delete a category. Raises if any products use this category."""
        category = self.get_category(category_id)
        from sqlalchemy import func
        product_count = self.db.query(func.count(Product.id)).filter(
            Product.category_id == category_id
        ).scalar() or 0
        if product_count > 0:
            raise handle_conflict(
                f"Cannot delete category: {product_count} product(s) use this category. "
                "Change those products to another category before deleting."
            )
        self.db.delete(category)
        self.db.commit()


class BrandService:
    """Service for brand operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_brands(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List brands. Ordered by brand_name asc."""
        q = self.db.query(Brand)
        
        if query:
            q = q.filter(
                or_(
                    Brand.brand_code.ilike(f"%{query}%"),
                    Brand.brand_name.ilike(f"%{query}%")
                )
            )
        
        q = q.order_by(Brand.brand_name.asc())
        total = q.count()
        offset = (page - 1) * limit
        brands = q.offset(offset).limit(limit).all()
        if not brands:
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }
        brand_ids = [b.id for b in brands]
        counts = (
            self.db.query(Product.brand_id, func.count(Product.id))
            .filter(Product.brand_id.in_(brand_ids))
            .group_by(Product.brand_id)
            .all()
        )
        count_by_brand = {str(bid): c for bid, c in counts}
        data = []
        for b in brands:
            row = {
                "id": b.id,
                "brand_code": b.brand_code,
                "brand_name": b.brand_name,
                "manufacturer": b.manufacturer,
                "website": b.website,
                "description": b.description,
                "logo_url": b.logo_url,
                "is_active": b.is_active,
                "created_at": b.created_at,
                "updated_at": b.updated_at,
                "created_by": str(b.created_by) if b.created_by else None,
                "product_count": count_by_brand.get(b.id, 0),
            }
            data.append(row)
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    
    def get_brand(self, brand_id: str):
        """Get a brand by UUID or brand_code/name."""
        resolved_ids = resolve_identifier(
            self.db,
            brand_id,
            Brand,
            code_fields=("brand_code", "brand_name"),
        )
        if not resolved_ids:
            raise handle_not_found("Brand", brand_id)
        brand = self.db.query(Brand).filter(Brand.id.in_(resolved_ids)).first()
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

    def delete_brand(self, brand_id: str):
        """Delete a brand. Products using this brand have their brand_id set to null (brand is optional)."""
        brand = self.get_brand(brand_id)
        updated = (
            self.db.query(Product)
            .filter(Product.brand_id == brand_id)
            .update({Product.brand_id: None}, synchronize_session=False)
        )
        self.db.delete(brand)
        self.db.commit()
        return {
            "message": "Brand deleted successfully",
            "products_unlinked": updated,
        }


class UnitOfMeasureService:
    """Service for unit of measure operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_uoms(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List units of measure with product_count per UOM."""
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
        if not uoms:
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }
        uom_ids = [u.id for u in uoms]
        counts = (
            self.db.query(Product.base_uom_id, func.count(Product.id))
            .filter(Product.base_uom_id.in_(uom_ids))
            .group_by(Product.base_uom_id)
            .all()
        )
        count_by_uom = {str(uid): c for uid, c in counts}
        data = []
        for u in uoms:
            row = {
                "id": u.id,
                "uom_code": u.uom_code,
                "uom_name": u.uom_name,
                "base_uom_id": str(u.base_uom_id) if u.base_uom_id else None,
                "conversion_factor": u.conversion_factor,
                "description": u.description,
                "is_active": getattr(u, "is_active", True),
                "created_at": u.created_at,
                "updated_at": u.updated_at,
                "product_count": count_by_uom.get(u.id, 0),
            }
            if u.base_uom:
                row["base_uom"] = {
                    "id": u.base_uom.id,
                    "uom_code": u.base_uom.uom_code,
                    "uom_name": u.base_uom.uom_name,
                }
            data.append(row)
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
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

    def delete_uom(self, uom_id: str):
        """Delete a UOM. Fails if any products use this UOM. Other UOMs that use this as base_uom have base_uom_id set to null."""
        uom = self.get_uom(uom_id)
        product_count = (
            self.db.query(func.count(Product.id)).filter(Product.base_uom_id == uom_id).scalar()
            or 0
        )
        if product_count > 0:
            raise handle_conflict(
                f"Cannot delete UOM: {product_count} product(s) use this UOM. "
                "Change those products to another UOM before deleting."
            )
        # Unlink any other UOMs that use this as their base
        self.db.query(UnitOfMeasure).filter(UnitOfMeasure.base_uom_id == uom_id).update(
            {UnitOfMeasure.base_uom_id: None}, synchronize_session=False
        )
        self.db.delete(uom)
        self.db.commit()
        return {"message": "UOM deleted successfully"}


class ProductAttachmentService:
    """Service for product attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def _resolve_product_identifier(self, product_identifier: Optional[str]) -> Optional[str]:
        """Accept either product UUID or product_code and return the UUID string."""
        if not product_identifier:
            return None
        normalized = str(product_identifier).strip()
        if not normalized:
            return None

        try:
            uuid.UUID(normalized)
            return normalized
        except (ValueError, AttributeError, TypeError):
            pass

        product = (
            self.db.query(Product.id)
            .filter(Product.product_code == normalized)
            .first()
        )
        return str(product.id) if product else None
    
    def list_product_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        product_id: Optional[str] = None,
        attachment_id: Optional[str] = None,
        user_type: Optional[str] = None
    ):
        """List product attachments with filtering and pagination."""
        from sqlalchemy.orm import joinedload
        
        q = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        )
        
        if product_id:
            resolved_product_id = self._resolve_product_identifier(product_id)
            if not resolved_product_id:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(ProductAttachment.product_id == resolved_product_id)
        
        if attachment_id:
            q = q.filter(ProductAttachment.attachment_id == attachment_id)
        
        if user_type:
            q = q.filter(ProductAttachment.attachment.has(Attachment.access_levels.contains([user_type])))
        
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
    
    def get_product_attachments_by_product(self, product_id: str, user_type: Optional[str] = None):
        """Get all non-deleted attachments for a specific product UUID or product code."""
        from sqlalchemy.orm import joinedload
        resolved_product_id = self._resolve_product_identifier(product_id)
        if not resolved_product_id:
            return []
        q = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(
            ProductAttachment.product_id == resolved_product_id,
            ProductAttachment.attachment.has(Attachment.is_deleted == False),
        ).order_by(
            ProductAttachment.sort_order.asc().nulls_last(),
            ProductAttachment.created_at.asc()
        )
        if user_type:
            q = q.filter(ProductAttachment.attachment.has(Attachment.access_levels.contains([user_type])))
        return q.all()
