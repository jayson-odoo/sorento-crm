"""Product service for business logic."""
from datetime import datetime
import re
import uuid
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from typing import Any, Optional, List, Callable, Tuple, Iterable
from decimal import Decimal
from app.models.product import Product, ProductCategory, Brand, UnitOfMeasure, ProductAttachment


def _populate_field_attachments(db: Session, products: Iterable[Product]) -> None:
    """Attach a transient ``field_attachments`` dict to each product.

    Pydantic ``ProductResponse`` reads it via ``from_attributes=True``. The map
    has shape ``{field_key: [AttachmentSimple-shaped dict, ...]}`` and is set
    only when at least one attachment is linked to a field on the row.
    """
    from app.services.attachment_field_link_service import AttachmentFieldLinkService
    from app.schemas.product import AttachmentSimple

    rows = list(products)
    ids = [str(p.id) for p in rows if getattr(p, "id", None)]
    if not ids:
        return
    by_row = AttachmentFieldLinkService(db).get_field_attachments_for_rows(
        "product", ids
    )
    if not by_row:
        for p in rows:
            try:
                setattr(p, "field_attachments", None)
            except Exception:
                pass
        return
    for p in rows:
        per_field = by_row.get(str(p.id))
        if not per_field:
            try:
                setattr(p, "field_attachments", None)
            except Exception:
                pass
            continue
        out: dict[str, list[dict]] = {}
        for field_key, atts in per_field.items():
            out[field_key] = [
                AttachmentSimple.model_validate(a).model_dump() for a in atts
            ]
        try:
            setattr(p, "field_attachments", out or None)
        except Exception:
            pass


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


def is_discontinued_from_description(description: Optional[str]) -> bool:
    """True when description starts with `****` (after lstrip).

    Auto-derived flag: a product whose description begins with four asterisks
    is considered discontinued. Recomputed on every save (single create/edit
    and bulk import) — never edited manually.
    """
    if not description:
        return False
    return description.lstrip().startswith("****")


from app.models.procurement import ProductSupplier, Supplier
from app.models.resources import Attachment, AttachmentType
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductCategoryCreate, ProductCategoryUpdate,
    BrandCreate, BrandUpdate, UnitOfMeasureCreate, UnitOfMeasureUpdate,
    ProductAttachmentCreate, ProductAttachmentUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict, AppException
from app.schemas.common import PaginationResponse
from app.models.user import SystemSetting
from app.services.embedding_events import publish_embedding_event
from app.services.identifier_resolver import resolve_identifier


class ProductService:
    """Service for product operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # Sentinel: a filter resolved to a definitively-empty set (e.g. an unknown
    # category/brand identifier, or `entities` that matched no product codes).
    # `_build_list_query` returns this instead of a Query so callers short-circuit
    # to an empty result without hitting the DB.
    _EMPTY_RESULT = object()

    def _build_list_query(
        self,
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
        entity_buckets: Optional[Any] = None,
        product_ids: Optional[list[str]] = None,
        discontinued_batch_id: Optional[str] = None,
        variant_filter: Optional[str] = None,
    ):
        """Build the filtered + sorted products query shared by ``list_products``
        and ``neighbours`` so the two can never drift.

        Returns the SQLAlchemy ``Query`` (already filtered + ordered), or
        :data:`_EMPTY_RESULT` when a filter resolves to a definitively empty set
        (unknown category/brand id, or `entity_buckets` with no product codes).

        The ORDER BY always appends ``Product.id`` as a deterministic tie-breaker
        so offset position and prev/next neighbours are unambiguous when the
        primary sort column (or its NULLS) has equal values.
        """
        q = self.db.query(Product)

        filters = []
        if product_ids:
            filters.append(Product.id.in_(product_ids))
        if entity_buckets is not None:
            if not getattr(entity_buckets, "product_codes", None):
                return self._EMPTY_RESULT
            from sqlalchemy import func as _func
            lowered = [c.lower() for c in entity_buckets.product_codes]
            filters.append(_func.lower(Product.product_code).in_(lowered))

        category_ids = resolve_identifier(
            self.db,
            category_id,
            ProductCategory,
            code_fields=("category_code", "category_name"),
        )
        if category_ids is not None:
            if not category_ids:
                return self._EMPTY_RESULT
            filters.append(Product.category_id.in_(category_ids))

        brand_ids = resolve_identifier(
            self.db,
            brand_id,
            Brand,
            code_fields=("brand_code", "brand_name"),
        )
        if brand_ids is not None:
            if not brand_ids:
                return self._EMPTY_RESULT
            filters.append(Product.brand_id.in_(brand_ids))

        if status and status != "all":
            filters.append(Product.is_active == (status == "active"))

        # Base / Variant / All variant-graph filter.
        if variant_filter == "base":
            filters.append(Product.variant_of_id.is_(None))
        elif variant_filter == "variant":
            filters.append(Product.variant_of_id.isnot(None))

        if item_type:
            filters.append(Product.item_type == item_type)

        # Deep link from a "products discontinued" notification: show exactly the
        # products reported in that batch (see product_discontinued_notify_service).
        if discontinued_batch_id:
            filters.append(Product.discontinued_notify_batch_id == discontinued_batch_id)

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
            q = q.order_by(sort_column.desc().nulls_last(), Product.id.asc())
        else:
            q = q.order_by(sort_column.asc().nulls_last(), Product.id.asc())
        return q

    def neighbours(
        self,
        product_id: str,
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
        discontinued_batch_id: Optional[str] = None,
    ) -> dict:
        """Resolve prev/next neighbours for ``product_id`` within the active list
        query.

        Reuses :meth:`_build_list_query` (the exact filter+sort path the product
        list GET uses) so list and neighbours can never drift. Selects only the
        ordered ids, then defers position/wrap math to the pure
        ``compute_neighbours`` helper. If the record is not in the filtered set
        (deep link, edited out of the filter, or a filter that resolved to an
        empty set), falls back to the unfiltered, default-sorted set so the pager
        is never dead (D2).

        Accepts a product UUID or product_code (SKU); resolved to the canonical
        UUID first so the neighbour math matches the ids ``_build_list_query``
        emits.
        """
        from app.services.record_navigation import compute_neighbours

        # Resolve SKU -> canonical UUID (the list query yields Product.id values).
        resolved_ids = resolve_identifier(
            self.db, product_id, Product, code_fields=("product_code",)
        )
        resolved_id = resolved_ids[0] if resolved_ids else product_id

        def _ordered_ids(q) -> list[str]:
            if q is self._EMPTY_RESULT:
                return []
            return [str(row[0]) for row in q.with_entities(Product.id).all()]

        filtered_q = self._build_list_query(
            query=query,
            category_id=category_id,
            brand_id=brand_id,
            status=status,
            price_min=price_min,
            price_max=price_max,
            item_type=item_type,
            length_min=length_min,
            length_max=length_max,
            width_min=width_min,
            width_max=width_max,
            height_min=height_min,
            height_max=height_max,
            any_dimension_min=any_dimension_min,
            any_dimension_max=any_dimension_max,
            sort_field=sort_field,
            sort_dir=sort_dir,
            discontinued_batch_id=discontinued_batch_id,
        )
        result = compute_neighbours(_ordered_ids(filtered_q), resolved_id)
        if result["index"] is not None:
            return result

        # D2: current record not in the filtered set -> fall back to the
        # unfiltered, default-sorted set so prev/next still works and total
        # reflects all products.
        unfiltered_q = self._build_list_query()
        return compute_neighbours(_ordered_ids(unfiltered_q), resolved_id)

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
        entities: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
        discontinued_batch_id: Optional[str] = None,
        variant_filter: Optional[str] = None,
    ):
        """List products with filtering and pagination.

        `entities` is the single-bag free-text filter for AI/MCP callers. Product
        matches narrow Product.product_code; other resolved types echo back but
        do not filter (products are keyed by product master).
        """
        from app.services.entity_resolver import (
            EntityFilterBuckets,
            resolve_entities_to_filters,
        )

        entity_buckets: Optional[EntityFilterBuckets] = None
        if entities:
            entity_buckets = resolve_entities_to_filters(
                self.db,
                entities,
                allowed_entity_types=(
                    "product", "customer", "customer_order", "transporter",
                    "inbound_shipment", "spo_allocation", "grn", "promotion",
                    "attachment", "form", "supplier",
                ),
            )
            if not entity_buckets.product_codes:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                    "resolved_entities": entity_buckets.as_echo(),
                }

        q = self._build_list_query(
            query=query,
            category_id=category_id,
            brand_id=brand_id,
            status=status,
            price_min=price_min,
            price_max=price_max,
            item_type=item_type,
            length_min=length_min,
            length_max=length_max,
            width_min=width_min,
            width_max=width_max,
            height_min=height_min,
            height_max=height_max,
            any_dimension_min=any_dimension_min,
            any_dimension_max=any_dimension_max,
            sort_field=sort_field,
            sort_dir=sort_dir,
            advanced_filter_clause=advanced_filter_clause,
            entity_buckets=entity_buckets,
            product_ids=product_ids,
            discontinued_batch_id=discontinued_batch_id,
            variant_filter=variant_filter,
        )
        if q is self._EMPTY_RESULT:
            payload = {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }
            if entity_buckets is not None:
                payload["resolved_entities"] = entity_buckets.as_echo()
            self._attach_product_alternatives(payload, query)
            return payload

        # Get total count
        total = q.count()

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
        _populate_field_attachments(self.db, products)
        self._populate_list_variant_fields(products)

        payload = {
            "data": products,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit
            },
            "empty": total == 0
        }
        if entity_buckets is not None:
            payload["resolved_entities"] = entity_buckets.as_echo()
        if total == 0:
            self._attach_product_alternatives(payload, query)
        return payload

    def _attach_product_alternatives(self, payload: dict, input_code: Optional[str]) -> None:
        """Attach trigram/graph sibling-product alternatives to an empty listing.

        Best-effort (§3.3, entity axis): a suggestion probe must never turn a
        legitimately-empty listing into a 500 (AC-R1). Only mutates `payload` when
        real data-bearing neighbours are found.
        """
        try:
            alternatives = self._product_entity_alternatives(input_code)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "product alternatives probe failed", exc_info=True
            )
            alternatives = None
        if alternatives:
            payload["alternatives"] = alternatives
            payload["relaxed_axis"] = "entity"

    def _product_entity_alternatives(self, input_code: Optional[str]) -> list[dict]:
        """Trigram/graph sibling products (existing + priced) for a row-miss.

        Fires on a genuine ``total == 0`` — a `query` code that matched no product
        row. The neighbour helper's input product does not exist, so it falls to
        trigram recall (§3.1 "did you mean") over EXISTING siblings. The has-data
        gate = candidate has a non-null, positive ``list_price`` so a price question
        gets a priced neighbour.

        Deliberately NOT called when a product resolves but carries ``list_price``
        0 — that is a field-level miss, and substituting a different SKU's price is
        misleading (a variant's price is legitimately different). Only the row-miss
        (nothing matched) path reaches here.
        """
        code = (input_code or "").strip()
        if not code:
            return []

        def _is_priced(candidate_ids: list[str]) -> set[str]:
            if not candidate_ids:
                return set()
            rows = (
                self.db.query(Product.id)
                .filter(
                    Product.id.in_(candidate_ids),
                    Product.list_price.isnot(None),
                    Product.list_price > 0,
                )
                .all()
            )
            return {str(row.id) for row in rows}

        from app.services.entity_resolver import find_entity_neighbours_with_data

        return find_entity_neighbours_with_data(
            self.db, code, has_data=_is_priced
        )

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
        _populate_field_attachments(self.db, [product])
        self._populate_variant_graph(product)
        return product

    def _populate_variant_graph(self, product) -> None:
        """Stash the variant-graph refs the detail serializer reads.

        Populates two throwaway instance attrs consumed by ProductResponse via
        `validation_alias` (`_variant_of_ref`, `_variant_children`) so the schema
        never touches the SQLAlchemy relationships directly — keeping LIST rows
        (which never call this) free of variant N+1s. See
        PLAN-suggest-on-miss-variant-graph.md §1.5.
        """
        parent = None
        if product.variant_of_id:
            parent = (
                self.db.query(Product)
                .filter(Product.id == product.variant_of_id)
                .first()
            )
        product._variant_of_ref = parent
        children = (
            self.db.query(Product)
            .filter(Product.variant_of_id == product.id)
            .order_by(Product.product_code.asc())
            .all()
        )
        product._variant_children = children
        product._variant_child_count = len(children)

    def set_variant_parent(self, product_id: str, parent_id: str, updated_by: str):
        """Manually set/change a product's variant parent (D1 — sticky override).

        Sets ``variant_of_id`` + ``variant_link_manual = True`` so auto-derivation
        never re-points it. Rejects self-parent and cycles (walking the chosen
        parent's ancestor chain). Returns the ORM product so the route serializes
        the full variant graph. Also the "attach a child" path: call this with the
        child's id and ``parent_id`` = this product.
        """
        product = self.get_product(product_id)  # 404 if the product is unknown
        if not parent_id or not str(parent_id).strip():
            raise AppException(
                status_code=400, message="parent_id is required", code="VALIDATION_ERROR"
            )
        resolved = resolve_identifier(
            self.db, parent_id, Product, code_fields=("product_code",)
        )
        parent = None
        if resolved:
            parent = self.db.query(Product).filter(Product.id.in_(resolved)).first()
        if parent is None:
            raise AppException(
                status_code=404, message="Parent product not found", code="NOT_FOUND"
            )
        if parent.id == product.id:
            raise AppException(
                status_code=400,
                message="A product cannot be a variant of itself",
                code="VALIDATION_ERROR",
            )
        # Cycle check — walk the chosen parent's ancestor chain via variant_of_id.
        # If `product` is encountered, linking would create a cycle. Visited-set
        # guards against a pre-existing cycle looping forever.
        visited: set[str] = set()
        cursor = parent
        while cursor is not None:
            if cursor.id == product.id:
                raise AppException(
                    status_code=400,
                    message="Cannot set parent: this would create a variant cycle",
                    code="VALIDATION_ERROR",
                )
            if cursor.id in visited:
                break
            visited.add(cursor.id)
            if not cursor.variant_of_id:
                break
            cursor = (
                self.db.query(Product)
                .filter(Product.id == cursor.variant_of_id)
                .first()
            )
        product.variant_of_id = parent.id
        product.variant_link_manual = True
        product.updated_by = updated_by
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(product)
        _populate_field_attachments(self.db, [product])
        self._populate_variant_graph(product)
        return product

    def unlink_variant(self, product_id: str, updated_by: str):
        """Manually unlink a product from its parent (D1 — sticky override).

        Nulls ``variant_of_id`` and sets ``variant_link_manual = True`` so
        auto-reconcile will not re-link it. Also the "remove a child" path: call
        with the child's id. Returns the ORM product.
        """
        product = self.get_product(product_id)  # 404 if the product is unknown
        product.variant_of_id = None
        product.variant_link_manual = True
        product.updated_by = updated_by
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(product)
        _populate_field_attachments(self.db, [product])
        self._populate_variant_graph(product)
        return product

    def reset_variant_auto(self, product_id: str):
        """Clear the manual override and re-derive this row's link from its code.

        Commits the flag clear first so the reset always persists even when the
        subsequent derivation yields no change, then runs the best-effort reconcile
        (which re-derives this row's parent AND adopts its orphans, committing its
        own unit of work). Never 500s a succeeded reset. Returns the ORM product.
        """
        product = self.get_product(product_id)  # 404 if the product is unknown
        product.variant_link_manual = False
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self._reconcile_variant_links(product.id)
        self.db.refresh(product)
        _populate_field_attachments(self.db, [product])
        self._populate_variant_graph(product)
        return product

    def _populate_list_variant_fields(self, products: Iterable[Product]) -> None:
        """Stash per-list-row variant fields WITHOUT N+1 (two bounded IN-queries).

        Mirrors :func:`_populate_field_attachments`: after the page rows are
        fetched, one query resolves parent refs (human-readable "Variant of"
        column) and one aggregates direct-child counts. The detail path uses
        :meth:`_populate_variant_graph` instead. Read by ``ProductResponse`` via
        the ``_variant_of_ref`` / ``_variant_child_count`` validation aliases.
        """
        rows = list(products)
        # Defaults so the schema serializes cleanly on the base / childless path.
        for p in rows:
            try:
                p._variant_of_ref = None
                p._variant_child_count = 0
            except Exception:
                pass
        page_ids = [str(p.id) for p in rows if getattr(p, "id", None)]
        if not page_ids:
            return

        # 1) Parent refs — one IN-query over just the parents referenced on this page.
        parent_ids = {
            str(p.variant_of_id) for p in rows if getattr(p, "variant_of_id", None)
        }
        if parent_ids:
            parents = (
                self.db.query(Product)
                .filter(Product.id.in_(parent_ids))
                .all()
            )
            parent_by_id = {str(pr.id): pr for pr in parents}
            for p in rows:
                if getattr(p, "variant_of_id", None):
                    p._variant_of_ref = parent_by_id.get(str(p.variant_of_id))

        # 2) Direct-child counts — one grouped IN-query keyed on this page's ids.
        counts = (
            self.db.query(Product.variant_of_id, func.count(Product.id))
            .filter(Product.variant_of_id.in_(page_ids))
            .group_by(Product.variant_of_id)
            .all()
        )
        count_by_id = {str(pid): int(c) for pid, c in counts}
        for p in rows:
            p._variant_child_count = count_by_id.get(str(p.id), 0)

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
        data["is_discontinued"] = is_discontinued_from_description(data.get("description"))
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
        self._reconcile_variant_links(product.id)
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
                new_discontinued = is_discontinued_from_description(update_data.get("description"))
                update_data["is_discontinued"] = new_discontinued
                # is_discontinued True->False: reset the notify watermark so a later
                # re-discontinuation is reported again by the batch cron. product.* is
                # still the OLD value here (setattr loop runs below).
                if product.is_discontinued and not new_discontinued:
                    update_data["discontinued_notified_at"] = None
                    update_data["discontinued_notify_batch_id"] = None
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
            # Re-derive the variant link only when the code (the derivation input)
            # actually changed — avoids churn on price/description-only edits.
            if "product_code" in update_data:
                # Capture existing children BEFORE re-deriving: a rename can break
                # the old-code prefix match, so each former child must re-derive to
                # its next ancestor (else it stays mis-linked to us — the FK is
                # unchanged by a rename). Mirrors delete_product's re-anchor.
                ex_children = self._variant_child_ids(product.id)
                self._reconcile_variant_links(product.id)
                for child_id in ex_children:
                    self._reconcile_variant_links(child_id)

        return product

    def delete_product(self, product_id: str):
        """Delete a product."""
        product = self.get_product(product_id)
        # Capture children BEFORE delete so we can re-anchor them to the next
        # existing ancestor afterwards (DB ondelete=SET NULL orphans them).
        ex_children = self._variant_child_ids(product_id)
        self.db.delete(product)
        self.db.commit()
        for child_id in ex_children:
            self._reconcile_variant_links(child_id)
        return {"message": "Product deleted successfully"}

    def _reconcile_variant_links(self, code_or_id: str) -> None:
        """Best-effort post-commit variant-graph reconcile. Never raises — a
        side effect running AFTER the row committed must not 500 a succeeded op
        (post-commit side-effect rule, CLAUDE.md)."""
        try:
            from app.services.variant_link_service import reconcile_variant_links

            reconcile_variant_links(self.db, code_or_id)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "variant link reconcile failed for %s", code_or_id, exc_info=True
            )
            try:
                self.db.rollback()
            except Exception:
                pass

    def _variant_child_ids(self, product_id: str) -> List[str]:
        try:
            from app.services.variant_link_service import child_ids_of

            return child_ids_of(self.db, product_id)
        except Exception:
            return []

    def bulk_delete_products(self, product_ids: List[str]):
        """Delete multiple products by ID."""
        if not product_ids:
            return {"message": "No products to delete", "deleted_count": 0}
        # Capture children of all deleted rows (excluding the deleted set itself)
        # so survivors re-anchor to their next existing ancestor.
        ex_children: List[str] = []
        for pid in product_ids:
            ex_children.extend(self._variant_child_ids(pid))
        deleted_set = set(product_ids)
        deleted = self.db.query(Product).filter(Product.id.in_(product_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()
        for child_id in ex_children:
            if child_id in deleted_set:
                continue
            self._reconcile_variant_links(child_id)
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

    def _bulk_publish_product_embedding_events(
        self,
        touched: List[Tuple[str, str, Any, Any]],
        user_id: str,
    ) -> None:
        """
        Bulk-insert embedding queue rows for many products in one commit, then enqueue RQ jobs.
        The per-row publish_embedding_event path does add+flush+enqueue+commit+refresh per call,
        which dominates wall time for 10k-row imports. This batched path: 1 INSERT + 1 commit, then
        N (cheap) RQ enqueues with no DB roundtrips.
        """
        if not touched:
            return
        from app.models.embeddings import EmbeddingQueue
        from app.services.queue_service import get_queue
        from app.services.embedding_service import _get_embedding_worker
        from app.config import settings as _settings

        now = datetime.utcnow()
        rows: List[dict] = []
        enqueue_payload: List[str] = []  # queue row ids to enqueue post-commit
        for pid, pcode, updated_at, created_at in touched:
            sua = updated_at or created_at
            event_id = str(uuid.uuid4())
            correlation_id = str(uuid.uuid4())
            queue_id = str(uuid.uuid4())
            payload = {
                "event_id": event_id,
                "event_type": "product.updated",
                "event_version": 1,
                "occurred_at": now.isoformat(),
                "source_type": "product",
                "source_id": str(pid),
                "source_key": pcode,
                "source_updated_at": sua.isoformat() if sua else None,
                "changed_fields": ["bulk_import"],
                "correlation_id": correlation_id,
                "triggered_by": user_id,
                "payload": {},
            }
            rows.append({
                "id": queue_id,
                "source_type": "product",
                "source_id": str(pid),
                "event_type": "product.updated",
                "event_version": 1,
                "source_updated_at": sua,
                "payload": payload,
                "status": "pending",
                "correlation_id": correlation_id,
            })
            enqueue_payload.append(queue_id)

        try:
            self.db.bulk_insert_mappings(EmbeddingQueue, rows)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        try:
            queue = get_queue(_settings.embedding_queue_name)
            worker = _get_embedding_worker()
            for q_id in enqueue_payload:
                queue.enqueue(worker, q_id, job_timeout=900)
        except Exception:
            # Embedding side effects must never block the import; rows are persisted
            # and can be picked up by a sweeper. Log and move on.
            import logging
            logging.getLogger(__name__).exception(
                "Failed to bulk-enqueue embedding events after product import"
            )

    def bulk_import_products(
        self,
        products_data: List[dict],
        user_id: str,
        on_progress: Optional[Callable[[int, int, int, int], None]] = None,
        outcome=None,
    ) -> dict:
        """
        Bulk import products from Excel-style rows.
        Expects each row: product_code, product_name?, description?, item_group?, item_brand?, list_price?, is_active?
        item_group is matched to category (code or name); item_brand to brand (code or name).
        Creates or updates by product_code. Uses default UOM for new products.
        On update, if the product has no product_suppliers row with standard_lead_time_days set, applies the same default supplier/lead time as new products.
        Optimized: pre-loads categories, brands, and existing products to avoid per-row queries.
        on_progress: optional callback(processed, successful, failed, skipped) called at chunk boundaries for real-time UI.
        outcome: optional ImportOutcome recorder, so every row's fate (created /
            updated / skipped-with-a-reason) is captured for the job detail page.
            None for non-job callers.
        """
        from app.services import import_outcome_codes as _oc
        from app.services.import_outcome import ImportOutcome as _ImportOutcome

        if outcome is None:
            outcome = _ImportOutcome(None, persist=False)

        def _row_identity(_row: dict, _code: str) -> dict:
            return {
                "product_code": _code,
                "item_group": (_row.get("item_group") or _row.get("Item Group") or None),
                "item_brand": (_row.get("item_brand") or _row.get("Item Brand") or None),
            }

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

        # Cache default supplier + lead-time once (was N× per row inside _ensure_default_supplier_lead_time).
        default_supplier = self._resolve_default_supplier_for_new_product()
        default_supplier_id = default_supplier.id if default_supplier else None
        default_lead_time_days = self._default_standard_lead_time_days()

        # Pre-fetch existing ProductSupplier rows on the default supplier for every existing product
        # we may touch, so per-row link decisions become an O(1) dict lookup.
        existing_default_ps: dict[str, ProductSupplier] = {}
        if default_supplier_id and existing_by_code:
            existing_pids = list({p.id for p in existing_by_code.values()})
            for i in range(0, len(existing_pids), self._BULK_FETCH_CODES_BATCH):
                batch = existing_pids[i : i + self._BULK_FETCH_CODES_BATCH]
                rows = (
                    self.db.query(ProductSupplier)
                    .filter(
                        ProductSupplier.supplier_id == default_supplier_id,
                        ProductSupplier.product_id.in_(batch),
                    )
                    .all()
                )
                for ps in rows:
                    existing_default_ps[ps.product_id] = ps

        def link_default_supplier(product_id: str) -> None:
            if not default_supplier_id:
                return
            ps = existing_default_ps.get(product_id)
            if ps is not None:
                if ps.standard_lead_time_days != default_lead_time_days:
                    ps.standard_lead_time_days = default_lead_time_days
                return
            new_ps = ProductSupplier(
                product_id=product_id,
                supplier_id=default_supplier_id,
                standard_lead_time_days=default_lead_time_days,
            )
            self.db.add(new_ps)
            existing_default_ps[product_id] = new_ps

        for idx, row in enumerate(products_data, start=1):
            try:
                product_code = (row.get("product_code") or row.get("Product Code") or row.get("Item Code") or "").strip()
                if not product_code:
                    msg = "product_code / Item Code is required"
                    errors.append(f"Row {idx}: {msg}")
                    outcome.skip(row=idx, code=_oc.MISSING_ITEM_CODE, message=msg)
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
                    # A negative list price (e.g. the -1 "no price" sentinel from the
                    # source system) is coerced to 0 rather than rejecting the row.
                    if list_price < 0:
                        list_price = Decimal("0")
                except Exception:
                    msg = f"Price must be a valid number, got '{raw_price}'"
                    errors.append(f"Row {idx} ({product_code}): {msg}")
                    outcome.skip(
                        row=idx,
                        code=_oc.INVALID_QUANTITY,
                        message=msg,
                        value=product_code,
                        identity=_row_identity(row, product_code),
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
                    msg = f"no category found for item_group '{item_group}'"
                    errors.append(f"Row {idx} ({product_code}): {msg}")
                    outcome.skip(
                        row=idx,
                        code=_oc.MISSING_REQUIRED_FIELD,
                        message=msg,
                        value=str(item_group),
                        identity=_row_identity(row, product_code),
                    )
                    continue
                if not category_id:
                    msg = "item_group is required and must match a category"
                    errors.append(f"Row {idx} ({product_code}): {msg}")
                    outcome.skip(
                        row=idx,
                        code=_oc.MISSING_REQUIRED_FIELD,
                        message=msg,
                        value=product_code,
                        identity=_row_identity(row, product_code),
                    )
                    continue

                brand_id = None
                if item_brand:
                    brand_id = brand_map.get(str(item_brand).strip().lower())
                if item_brand and not brand_id:
                    msg = f"no brand found for item_brand '{item_brand}'"
                    errors.append(f"Row {idx} ({product_code}): {msg}")
                    outcome.skip(
                        row=idx,
                        code=_oc.MISSING_REQUIRED_FIELD,
                        message=msg,
                        value=str(item_brand),
                        identity=_row_identity(row, product_code),
                    )
                    continue

                parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(description)
                discontinued = is_discontinued_from_description(description)

                existing = existing_by_code.get(product_code)
                if existing:
                    # is_discontinued True->False: reset the notify watermark so a later
                    # re-discontinuation is reported again (capture OLD before assigning).
                    if existing.is_discontinued and not discontinued:
                        existing.discontinued_notified_at = None
                        existing.discontinued_notify_batch_id = None
                    existing.product_name = product_name
                    existing.description = description or None
                    existing.category_id = category_id
                    existing.brand_id = brand_id
                    existing.list_price = list_price
                    existing.is_active = is_active
                    existing.is_discontinued = discontinued
                    existing.updated_by = user_id
                    existing.updated_at = datetime.utcnow()
                    if parsed_l is not None:
                        existing.dimensions_length = parsed_l
                    if parsed_w is not None:
                        existing.dimensions_width = parsed_w
                    if parsed_h is not None:
                        existing.dimensions_height = parsed_h
                    if existing.id not in products_with_lead_time:
                        link_default_supplier(existing.id)
                        products_with_lead_time.add(existing.id)
                    updated += 1
                    outcome.updated(
                        row=idx,
                        message=f"Product updated: {product_code}",
                        value=product_code,
                        identity=_row_identity(row, product_code),
                        entity_type="product",
                        entity_id=existing.id,
                    )
                else:
                    # Generate UUID Python-side so we can link ProductSupplier without per-row flush().
                    product = Product(
                        id=str(uuid.uuid4()),
                        product_code=product_code,
                        product_name=product_name,
                        description=description or None,
                        category_id=category_id,
                        brand_id=brand_id,
                        base_uom_id=default_uom_id,
                        list_price=list_price,
                        is_active=is_active,
                        is_discontinued=discontinued,
                        dimensions_length=parsed_l,
                        dimensions_width=parsed_w,
                        dimensions_height=parsed_h,
                        created_by=user_id,
                    )
                    self.db.add(product)
                    link_default_supplier(product.id)
                    products_with_lead_time.add(product.id)
                    existing_by_code[product_code] = product  # avoid duplicate add if same code again
                    created += 1
                    outcome.success(
                        row=idx,
                        message=f"Product created: {product_code}",
                        value=product_code,
                        identity=_row_identity(row, product_code),
                        entity_type="product",
                        entity_id=product.id,
                    )

                if idx % chunk_size == 0:
                    self.db.commit()
                    if on_progress:
                        on_progress(idx, created + updated, len(errors), 0)
            except Exception as e:
                self.db.rollback()
                errors.append(f"Row {idx} ({row.get('product_code', '')}): {str(e)}")
                outcome.fail(
                    row=idx,
                    code=_oc.ROW_ERROR,
                    message=str(e),
                    value=str(row.get("product_code") or row.get("Product Code") or "") or None,
                )
                if idx % chunk_size == 0:
                    self.db.commit()
                    if on_progress:
                        on_progress(idx, created + updated, len(errors), 0)

        self.db.commit()
        # Report 100% progress BEFORE embedding fan-out so the UI doesn't appear stuck
        # while we batch-write embedding queue rows + enqueue RQ jobs.
        if on_progress:
            on_progress(len(products_data), created + updated, len(errors), 0)

        if created or updated:
            touched = (
                self.db.query(Product.id, Product.product_code, Product.updated_at, Product.created_at)
                .filter(Product.product_code.in_(all_codes))
                .all()
            )
            self._bulk_publish_product_embedding_events(touched, user_id)
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
                    # A negative list price (e.g. the -1 "no price" sentinel from the
                    # source system) is coerced to 0 rather than rejecting the row.
                    if list_price < 0:
                        list_price = Decimal("0")
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
    
    def list_categories(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        category_ids: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
    ):
        """List product categories. Ordered by display_order asc, then category_name asc."""
        q = self.db.query(ProductCategory)

        if query:
            q = q.filter(
                or_(
                    ProductCategory.category_code.ilike(f"%{query}%"),
                    ProductCategory.category_name.ilike(f"%{query}%")
                )
            )

        if category_ids is not None or product_ids is not None:
            allowed: set = set(category_ids or [])
            if product_ids:
                rows = (
                    self.db.query(Product.category_id)
                    .filter(Product.id.in_(product_ids), Product.category_id.isnot(None))
                    .distinct()
                    .all()
                )
                allowed.update(str(r[0]) for r in rows)
            q = q.filter(ProductCategory.id.in_(allowed))

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
    
    def list_brands(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        brand_ids: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
    ):
        """List brands. Ordered by brand_name asc."""
        q = self.db.query(Brand)

        if query:
            q = q.filter(
                or_(
                    Brand.brand_code.ilike(f"%{query}%"),
                    Brand.brand_name.ilike(f"%{query}%")
                )
            )

        if brand_ids is not None or product_ids is not None:
            allowed: set = set(brand_ids or [])
            if product_ids:
                rows = (
                    self.db.query(Product.brand_id)
                    .filter(Product.id.in_(product_ids), Product.brand_id.isnot(None))
                    .distinct()
                    .all()
                )
                allowed.update(str(r[0]) for r in rows)
            q = q.filter(Brand.id.in_(allowed))

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
    
    def list_uoms(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        uom_ids: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
    ):
        """List units of measure with product_count per UOM."""
        q = self.db.query(UnitOfMeasure)

        if query:
            q = q.filter(
                or_(
                    UnitOfMeasure.uom_code.ilike(f"%{query}%"),
                    UnitOfMeasure.uom_name.ilike(f"%{query}%")
                )
            )

        if uom_ids is not None or product_ids is not None:
            allowed: set = set(uom_ids or [])
            if product_ids:
                rows = (
                    self.db.query(Product.base_uom_id)
                    .filter(Product.id.in_(product_ids), Product.base_uom_id.isnot(None))
                    .distinct()
                    .all()
                )
                allowed.update(str(r[0]) for r in rows)
            q = q.filter(UnitOfMeasure.id.in_(allowed))

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

    def _resolve_product_identifiers(self, product_identifier: Optional[str]) -> Optional[list[str]]:
        """Resolve a product UUID or product_code to one or more product UUIDs.

        - UUID input -> [uuid].
        - Non-UUID input -> case-insensitive substring (ilike) match across product_code,
          so callers passing a partial/base code (e.g. ``SRTMCB6084-WH``) also find
          variants (``SRTMCB6084-WH-DF`` etc.).
        - Returns ``None`` when input is empty; ``[]`` when no product matches.
        """
        if not product_identifier:
            return None
        normalized = str(product_identifier).strip()
        if not normalized:
            return None

        try:
            uuid.UUID(normalized)
            return [normalized]
        except (ValueError, AttributeError, TypeError):
            pass

        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        fuzzy_rows = (
            self.db.query(Product.id)
            .filter(Product.product_code.ilike(f"%{escaped}%", escape="\\"))
            .all()
        )
        return [str(row.id) for row in fuzzy_rows]
    
    def list_product_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        product_id: Optional[str] = None,
        attachment_id: Optional[str] = None,
        user_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
        entities: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
        attachment_ids: Optional[list[str]] = None,
        attachment_type_ids: Optional[list[str]] = None,
        query: Optional[str] = None,
    ):
        """List product attachments with filtering and pagination.

        When *contact_access_codes* is supplied, restricts to attachments whose
        ``access_levels`` overlaps the contact's codes. ``contact_access_codes=[]``
        returns nothing (contact has no assigned access types).
        """
        from sqlalchemy.orm import joinedload
        from sqlalchemy import cast as _sa_cast, text as _sa_text, String as _sa_String, func as _sa_func
        from sqlalchemy.dialects.postgresql import ARRAY as _PG_ARRAY
        from app.services.entity_filter_helpers import (
            attach_echo,
            empty_payload,
            resolve_or_empty,
        )

        entity_buckets = resolve_or_empty(self.db, entities)
        if entity_buckets is not None and not entity_buckets.product_codes:
            return empty_payload(entity_buckets, page=page, limit=limit)

        # Track which product(s) the caller scoped to, so an empty result can offer
        # data-bearing variant/neighbour alternatives (§3.4 M5 entity-axis).
        _scoped_product_ids: set[str] = set()

        q = self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(
            # Exclude trashed (soft-deleted) attachments — mirrors
            # get_product_attachments_by_product. Without this, "Move to Trash"d
            # files keep showing in product-attachment listings.
            ProductAttachment.attachment.has(Attachment.is_deleted == False),
        )

        if entity_buckets is not None and entity_buckets.product_codes:
            lowered = [c.lower() for c in entity_buckets.product_codes]
            q = q.filter(
                ProductAttachment.product.has(_sa_func.lower(Product.product_code).in_(lowered))
            )
            code_rows = (
                self.db.query(Product.id)
                .filter(_sa_func.lower(Product.product_code).in_(lowered))
                .all()
            )
            _scoped_product_ids.update(str(r[0]) for r in code_rows)

        if product_id:
            resolved_product_ids = self._resolve_product_identifiers(product_id)
            if not resolved_product_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(ProductAttachment.product_id.in_(resolved_product_ids))
            _scoped_product_ids.update(str(pid) for pid in resolved_product_ids)

        if attachment_id:
            q = q.filter(ProductAttachment.attachment_id == attachment_id)

        if product_ids:
            q = q.filter(ProductAttachment.product_id.in_(product_ids))
            _scoped_product_ids.update(str(pid) for pid in product_ids)
        if attachment_ids:
            q = q.filter(ProductAttachment.attachment_id.in_(attachment_ids))
        if attachment_type_ids:
            # Narrow to product-attachment rows whose underlying Attachment
            # carries one of the supplied AttachmentType UUIDs (brochure / spec
            # sheet / installation guide / etc.). Empty list → no filter.
            q = q.filter(
                ProductAttachment.attachment.has(
                    Attachment.attachment_type_id.in_(attachment_type_ids)
                )
            )

        if user_type:
            q = q.filter(ProductAttachment.attachment.has(Attachment.access_levels.contains([user_type])))
        if contact_access_codes is not None:
            if not contact_access_codes:
                q = q.filter(_sa_text("false"))
            else:
                q = q.filter(
                    ProductAttachment.attachment.has(
                        Attachment.access_levels.op("?|")(
                            _sa_cast(contact_access_codes, _PG_ARRAY(_sa_String))
                        )
                    )
                )

        # Free-text search box (DataGrid `query`): match product code / name,
        # attachment filename (original or display), or attachment type name.
        if query and query.strip():
            like = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    ProductAttachment.product.has(
                        or_(
                            Product.product_code.ilike(like),
                            Product.product_name.ilike(like),
                        )
                    ),
                    ProductAttachment.attachment.has(
                        or_(
                            Attachment.original_filename.ilike(like),
                            Attachment.stored_filename.ilike(like),
                            Attachment.attachment_type.has(
                                AttachmentType.type_name.ilike(like)
                            ),
                        )
                    ),
                )
            )

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

        payload = {
            "data": product_attachments,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
        # Entity-axis relaxation (§3.4 M5): the product resolved but has no
        # (matching-type) attachment. Offer data-bearing variant/neighbour
        # products that DO have such an attachment. Only on the empty path — a
        # non-empty result stays byte-identical (AC-R1).
        if total == 0:
            # Best-effort: a suggestion probe must never turn an empty attachment
            # listing into a 500 (AC-R1).
            try:
                alternatives = self._attachment_entity_alternatives(
                    _scoped_product_ids, attachment_type_ids
                )
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "attachment alternatives probe failed", exc_info=True
                )
                alternatives = None
            if alternatives:
                payload["alternatives"] = alternatives
                payload["relaxed_axis"] = "entity"

        return attach_echo(payload, entity_buckets)

    def _attachment_entity_alternatives(
        self,
        product_ids: set[str],
        attachment_type_ids: Optional[list[str]],
    ) -> list[dict]:
        """Data-bearing variant/neighbour alternatives for an empty attachment result.

        Only fires when exactly ONE input product resolved. The has-data gate =
        the candidate product has at least one non-trashed product-attachment,
        narrowed to ``attachment_type_ids`` when the caller asked for a specific
        document class (e.g. a certificate). Reuses the shared neighbour helper —
        no bespoke neighbour ranking here.
        """
        ids = list(product_ids or [])
        if len(ids) != 1:
            return []
        prod = (
            self.db.query(Product.product_code)
            .filter(Product.id == ids[0])
            .first()
        )
        if not prod or not prod.product_code:
            return []

        def _has_attachment(candidate_ids: list[str]) -> set:
            if not candidate_ids:
                return set()
            aq = self.db.query(ProductAttachment.product_id).filter(
                ProductAttachment.product_id.in_(candidate_ids),
                ProductAttachment.attachment.has(Attachment.is_deleted == False),
            )
            if attachment_type_ids:
                aq = aq.filter(
                    ProductAttachment.attachment.has(
                        Attachment.attachment_type_id.in_(attachment_type_ids)
                    )
                )
            return {str(r.product_id) for r in aq.distinct().all()}

        from app.services.entity_resolver import find_entity_neighbours_with_data

        return find_entity_neighbours_with_data(
            self.db, prod.product_code, has_data=_has_attachment
        )

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
        """Create or refresh a product attachment relationship.

        TCK-2026-000020: external n8n intake re-posts the same (product_id,
        attachment_id) when an attachment is replaced. Switch from hard
        conflict to idempotent update so the linked record refreshes its
        sort_order / is_primary / access_levels instead of duplicate-rejecting.
        The returned row carries `_already_existed=True` so the route can
        echo it back to the caller.
        """
        from sqlalchemy.orm import joinedload

        existing = self.db.query(ProductAttachment).filter(
            ProductAttachment.product_id == product_attachment_data.product_id,
            ProductAttachment.attachment_id == product_attachment_data.attachment_id
        ).first()
        if existing:
            update_dict = product_attachment_data.model_dump(exclude_unset=True)
            chosen = update_dict.pop("is_primary", None)
            for key, value in update_dict.items():
                if key in ("product_id", "attachment_id"):
                    continue
                setattr(existing, key, value)
            # Same single decision as the update path: setting this flag without clearing the
            # previous holder trips the partial unique index, so the n8n re-post of a replaced
            # photograph would 500 rather than move the choice.
            if chosen:
                from app.services import product_image_service

                product_image_service.choose(self.db, existing)
            elif chosen is not None:
                existing.is_primary = False
            from datetime import datetime as _dt
            existing.updated_at = _dt.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            row = self.db.query(ProductAttachment).options(
                joinedload(ProductAttachment.product),
                joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
            ).filter(ProductAttachment.id == existing.id).first()
            if row is not None:
                setattr(row, "_already_existed", True)
            return row

        attachment_dict = product_attachment_data.model_dump()
        if created_by:
            attachment_dict["created_by"] = created_by
        # Held back until the row exists, so `choose` can clear the previous holder first.
        chosen = bool(attachment_dict.pop("is_primary", False))

        product_attachment = ProductAttachment(**attachment_dict)
        self.db.add(product_attachment)
        if chosen:
            from app.services import product_image_service

            self.db.flush()
            product_image_service.choose(self.db, product_attachment)
        self.db.commit()
        self.db.refresh(product_attachment)

        return self.db.query(ProductAttachment).options(
            joinedload(ProductAttachment.product),
            joinedload(ProductAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(ProductAttachment.id == product_attachment.id).first()
    
    def update_product_attachment(self, product_attachment_id: str, product_attachment_data: ProductAttachmentUpdate):
        """Update a product attachment relationship.

        ``is_primary`` is the ONE decision about which photograph is the product, read by the
        brochure, by 3D-model generation and by the quotation. The invariant is exactly one per
        product, and `product_attachments` holds a partial unique index on
        `(company_id, product_id) WHERE is_primary IS TRUE` to enforce it - so setting a second
        one here without clearing the first does not quietly produce two, it 500s the save.
        Routed through `product_image_service.choose` so this endpoint and every other writer
        record the choice the same way.
        """
        product_attachment = self.get_product_attachment(product_attachment_id)

        update_data = product_attachment_data.model_dump(exclude_unset=True)
        chosen = update_data.pop("is_primary", None)
        for key, value in update_data.items():
            setattr(product_attachment, key, value)
        if chosen is not None:
            from app.services import product_image_service

            if chosen:
                product_image_service.choose(self.db, product_attachment)
            else:
                product_attachment.is_primary = False

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
    
    def get_product_attachments_by_product(
        self,
        product_id: str,
        user_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
    ):
        """Get all non-deleted attachments for a specific product UUID or product code.

        ``contact_access_codes=[]`` returns nothing (no overlap with anything).
        """
        from sqlalchemy.orm import joinedload
        from sqlalchemy import cast as _sa_cast, text as _sa_text, String as _sa_String
        from sqlalchemy.dialects.postgresql import ARRAY as _PG_ARRAY
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
        if contact_access_codes is not None:
            if not contact_access_codes:
                q = q.filter(_sa_text("false"))
            else:
                q = q.filter(
                    ProductAttachment.attachment.has(
                        Attachment.access_levels.op("?|")(
                            _sa_cast(contact_access_codes, _PG_ARRAY(_sa_String))
                        )
                    )
                )
        return q.all()
