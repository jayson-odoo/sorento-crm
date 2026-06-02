"""Order service for business logic."""
import logging
import uuid
import time
from typing import Any, Optional
from io import BytesIO
from datetime import datetime

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func, exists
from decimal import Decimal
from app.models.order import Order, OrderStatus, Customer, OrderLine, Transporter
from app.models.product import Product
from app.models.inventory import Warehouse
from app.schemas.order import (
    OrderCreate, OrderUpdate, CustomerCreate, CustomerUpdate,
    OrderStatusCreate, OrderStatusUpdate,
    OrderLineCreate, OrderLineUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.import_log_service import ImportLogService
from app.services.calendar_service import CalendarService
from app.services.identifier_resolver import resolve_identifier
from app.services.embedding_change_listener import (
    suppress_embedding_events,
    bulk_enqueue_embedding_events,
)
from app.services.fuzzy_resolver import resolve_via_embedding_then_ilike
from app.services.entity_resolver import (
    EntityFilterBuckets,
    resolve_entities_to_filters,
)

logger = logging.getLogger(__name__)


class OrderService:
    """Service for order operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_orders(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        customer_query: Optional[str] = None,
        product_query: Optional[str] = None,
        transporter_query: Optional[str] = None,
        customer_id: Optional[str] = None,
        order_status_id: Optional[str] = None,
        has_order_lines: Optional[str] = None,
        has_actual_delivery_date: Optional[str] = None,
        order_date_from: Optional[datetime] = None,
        order_date_to: Optional[datetime] = None,
        actual_delivery_date_from: Optional[datetime] = None,
        actual_delivery_date_to: Optional[datetime] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        advanced_filter_clause: Optional[Any] = None,
        entities: Optional[list[str]] = None,
        order_ids: Optional[list[str]] = None,
        customer_ids: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
        transporter_ids: Optional[list[str]] = None,
    ):
        """List orders with filtering and pagination.

        `entities` is the single-bag entity filter for AI/MCP callers: pass a list of
        free-text strings (customer names, product codes, transporter labels, order
        numbers). The server resolves each via the entity_resolver and applies the
        matched filters internally. The resolution is echoed back as
        `_resolved_entities` on the response so the agent can show the user what
        was actually matched. Typed params (`customer_query`, `product_query`, ...)
        remain for direct callers and are AND'd with `entities`.
        """
        # Capture typed UUID params into locals up-front so later code that
        # reuses the names (e.g. `customer_ids = resolve_identifier(...)`)
        # cannot shadow them.
        _order_uuid_filter = list(order_ids) if order_ids else None
        _customer_uuid_filter = list(customer_ids) if customer_ids else None
        _product_uuid_filter = list(product_ids) if product_ids else None
        _transporter_uuid_filter = list(transporter_ids) if transporter_ids else None

        q = self.db.query(Order).filter(Order.deleted_at.is_(None))

        entity_buckets: Optional[EntityFilterBuckets] = None
        if entities:
            entity_buckets = resolve_entities_to_filters(
                self.db,
                entities,
                allowed_entity_types=(
                    "product", "customer", "customer_order", "transporter",
                    "inbound_shipment", "spo_allocation", "grn", "promotion",
                    "attachment", "form",
                ),
            )
            # Caller passed `entities` but nothing resolved above the RAG
            # similarity threshold → return empty rather than fall through and
            # unintentionally list every order. Echo the unresolved inputs so the
            # agent surfaces "no match" to the user.
            if not entity_buckets.has_resolved_filter:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                    "resolved_entities": entity_buckets.as_echo(),
                }

        filters = []

        if _order_uuid_filter:
            filters.append(Order.id.in_(_order_uuid_filter))

        if _customer_uuid_filter:
            # Match Order.customer_id IN (...) OR legacy debtor_name match.
            # Backfill 207 should make the OR branch redundant for new data, but
            # historical rows with NULL customer_id stay reachable.
            from sqlalchemy import func as _func
            customer_names_subq = (
                self.db.query(Customer.customer_name)
                .filter(Customer.id.in_(_customer_uuid_filter))
                .subquery()
            )
            filters.append(
                or_(
                    Order.customer_id.in_(_customer_uuid_filter),
                    _func.lower(_func.btrim(Order.debtor_name)).in_(
                        self.db.query(_func.lower(_func.btrim(customer_names_subq.c.customer_name)))
                    ),
                )
            )

        if _product_uuid_filter:
            filters.append(
                Order.lines.any(OrderLine.product_id.in_(_product_uuid_filter))
            )

        if _transporter_uuid_filter:
            from sqlalchemy import func as _func
            transporter_names_subq = (
                self.db.query(Transporter.name)
                .filter(Transporter.id.in_(_transporter_uuid_filter))
                .subquery()
            )
            filters.append(
                or_(
                    Order.transporter_id.in_(_transporter_uuid_filter),
                    _func.lower(_func.btrim(Order.transporter)).in_(
                        self.db.query(_func.lower(_func.btrim(transporter_names_subq.c.name)))
                    ),
                )
            )

        customer_ids = resolve_identifier(
            self.db,
            customer_id,
            Customer,
            code_fields=("customer_code", "customer_name"),
        )
        if customer_ids is not None:
            if not customer_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            filters.append(Order.customer_id.in_(customer_ids))

        status_ids = resolve_identifier(
            self.db,
            order_status_id,
            OrderStatus,
            code_fields=("status_code", "status_name"),
        )
        if status_ids is not None:
            if not status_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            filters.append(Order.order_status_id.in_(status_ids))

        hol = (has_order_lines or "").strip().lower()
        if hol == "yes":
            filters.append(exists().where(OrderLine.order_id == Order.id))
        elif hol == "no":
            filters.append(~exists().where(OrderLine.order_id == Order.id))

        hadd = (has_actual_delivery_date or "").strip().lower()
        if hadd == "yes":
            filters.append(Order.actual_delivery_date.is_not(None))
        elif hadd == "no":
            filters.append(Order.actual_delivery_date.is_(None))

        if order_date_from is not None:
            filters.append(Order.order_date >= order_date_from)

        if order_date_to is not None:
            filters.append(Order.order_date <= order_date_to)

        if actual_delivery_date_from is not None:
            filters.append(Order.actual_delivery_date >= actual_delivery_date_from)

        if actual_delivery_date_to is not None:
            filters.append(Order.actual_delivery_date <= actual_delivery_date_to)
        
        query_filter = None
        if query and (query := (query or "").strip()):
            term = f"%{query}%"
            # Split into UNION of matching id sets. The original OR-with-EXISTS-on-customers
            # forces a Seq Scan on orders even with pg_trgm indexes; pulling the cross-table
            # match into its own subquery lets each branch use its trigram index independently.
            direct_ids = self.db.query(Order.id).filter(
                or_(
                    Order.order_number.ilike(term),
                    Order.debtor_name.ilike(term),
                    Order.debtor_code.ilike(term),
                    # Legacy free-text transporter column kept for back-compat
                    # rows that pre-date the transporters FK.
                    Order.transporter.ilike(term),
                )
            )
            customer_ids = (
                self.db.query(Order.id)
                .join(Customer, Order.customer_id == Customer.id)
                .filter(
                    or_(
                        Customer.customer_name.ilike(term),
                        Customer.customer_code.ilike(term),
                    )
                )
            )
            # Canonical transporter join: matches Transporter.code / name so the
            # DO grid free-text search resolves transporter searches the same
            # way the Filters panel does (transporter_id FK).
            transporter_ids = (
                self.db.query(Order.id)
                .join(Transporter, Order.transporter_id == Transporter.id)
                .filter(
                    or_(
                        Transporter.code.ilike(term),
                        Transporter.name.ilike(term),
                    )
                )
            )
            query_filter = Order.id.in_(
                direct_ids.union(customer_ids).union(transporter_ids)
            )
        if customer_query and (customer_query := (customer_query or "").strip()):
            customer_clause, _ = resolve_via_embedding_then_ilike(
                self.db,
                customer_query,
                source_type="customer",
                ilike_columns=[Order.debtor_name, Order.debtor_code],
                canonical_model=Customer,
                canonical_fields=("customer_name", "customer_code"),
                extra_filter_builders=[
                    lambda like: Order.customer.has(Customer.customer_name.ilike(like)),
                    lambda like: Order.customer.has(Customer.customer_code.ilike(like)),
                ],
            )
            if customer_clause is not None:
                filters.append(customer_clause)
        if product_query and (product_query := (product_query or "").strip()):
            product_clause, _ = resolve_via_embedding_then_ilike(
                self.db,
                product_query,
                source_type="product",
                ilike_columns=[],
                canonical_model=Product,
                canonical_fields=("product_code", "product_name"),
                extra_filter_builders=[
                    lambda like: Order.lines.any(
                        OrderLine.product.has(
                            or_(
                                Product.product_code.ilike(like),
                                Product.product_name.ilike(like),
                                Product.description.ilike(like),
                            )
                        )
                    ),
                ],
            )
            if product_clause is not None:
                filters.append(product_clause)
        if transporter_query and (transporter_query := (transporter_query or "").strip()):
            transporter_clause, _ = resolve_via_embedding_then_ilike(
                self.db,
                transporter_query,
                source_type="transporter",
                ilike_columns=[Order.transporter],
            )
            if transporter_clause is not None:
                filters.append(transporter_clause)

        if entity_buckets is not None and entity_buckets.has_resolved_filter:
            entity_clauses = self._build_entity_filter_clauses(entity_buckets)
            filters.extend(entity_clauses)

        if advanced_filter_clause is not None:
            filters.append(advanced_filter_clause)

        base_q = q.filter(and_(*filters)) if filters else q
        q = base_q.filter(query_filter) if query_filter is not None else base_q
        
        total = q.count()
        if query_filter is not None and total == 0 and filters:
            # General fallback: if text query yields nothing but structured filters exist,
            # prioritize structured filters instead of returning a false empty result.
            q = base_q
            total = q.count()

        # Nullable columns: use nulls_last so NULLs don't break sort order
        nullable_sort_fields = {
            "order_date",
            "estimated_delivery_date",
            "actual_delivery_date",
            "delivery_days",
            "debtor_name",
            "debtor_code",
            "agent",
            "remarks_cs",
            "order_type",
        }
        sort_map = {
            "order_number": Order.order_number,
            "order_date": Order.order_date,
            "estimated_delivery_date": Order.estimated_delivery_date,
            "actual_delivery_date": Order.actual_delivery_date,
            "delivery_days": Order.delivery_days,
            "debtor_name": Order.debtor_name,
            "debtor_code": Order.debtor_code,
            "agent": Order.agent,
            "is_cancelled": Order.is_cancelled,
            "remarks_cs": Order.remarks_cs,
            "order_type": Order.order_type,
            "total_amount": Order.total_amount,
            "created_at": Order.created_at,
            "updated_at": Order.updated_at,
        }
        if sort_field == "order_status.status_name":
            q = q.outerjoin(Order.order_status)
            status_col = OrderStatus.status_name
            if sort_dir == "desc":
                q = q.order_by(status_col.desc().nulls_last())
            else:
                q = q.order_by(status_col.asc().nulls_last())
        else:
            sort_column = sort_map.get(sort_field, Order.created_at)
            nullable_sort = sort_field in nullable_sort_fields
            if sort_dir == "desc":
                if nullable_sort:
                    q = q.order_by(sort_column.desc().nulls_last())
                else:
                    q = q.order_by(sort_column.desc())
            else:
                if nullable_sort:
                    q = q.order_by(sort_column.asc().nulls_last())
                else:
                    q = q.order_by(sort_column.asc())

        offset = (page - 1) * limit
        # Eager-load relations referenced by OrderResponse to avoid N+1 lazy loads
        # during Pydantic serialization. joinedload for to-one (customer, order_status),
        # selectinload for the lines collection (1 batched IN query, then per-line
        # product is also batched).
        from sqlalchemy.orm import selectinload
        orders = (
            q.options(
                joinedload(Order.customer),
                joinedload(Order.order_status),
                selectinload(Order.lines).joinedload(OrderLine.product),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        payload = {
            "data": orders,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit
            },
            "empty": total == 0
        }
        if entity_buckets is not None:
            payload["resolved_entities"] = entity_buckets.as_echo()
        return payload

    def _build_entity_filter_clauses(
        self,
        buckets: "EntityFilterBuckets",
        *,
        product_join_already_present: bool = False,
    ) -> list[Any]:
        """Translate resolved entity buckets into SQL filter clauses for Order queries.

        Same-type entities are OR'd (e.g. two product codes → IN). Different types are
        returned as separate clauses so the caller AND's them across types — the user
        said "orders for X and product Y" should intersect, not union. When the caller
        has already joined OrderLine + Product (e.g. list_orders_by_product), pass
        `product_join_already_present=True` so the product clause filters on the
        existing join instead of adding a redundant EXISTS subquery.
        """
        clauses: list[Any] = []
        if buckets.product_codes:
            lowered_codes = [c.lower() for c in buckets.product_codes]
            if product_join_already_present:
                clauses.append(func.lower(Product.product_code).in_(lowered_codes))
            else:
                clauses.append(
                    Order.lines.any(
                        OrderLine.product.has(
                            func.lower(Product.product_code).in_(lowered_codes)
                        )
                    )
                )
        if buckets.order_numbers:
            clauses.append(
                func.lower(Order.order_number).in_([o.lower() for o in buckets.order_numbers])
            )
        customer_subclauses: list[Any] = []
        if buckets.debtor_names:
            lowered = [d.lower() for d in buckets.debtor_names]
            customer_subclauses.append(func.lower(Order.debtor_name).in_(lowered))
        if buckets.customer_codes:
            lowered = [c.lower() for c in buckets.customer_codes]
            customer_subclauses.append(func.lower(Order.debtor_code).in_(lowered))
            customer_subclauses.append(
                Order.customer.has(func.lower(Customer.customer_code).in_(lowered))
            )
        if buckets.customer_names:
            lowered = [n.lower() for n in buckets.customer_names]
            customer_subclauses.append(
                Order.customer.has(func.lower(Customer.customer_name).in_(lowered))
            )
            customer_subclauses.append(func.lower(Order.debtor_name).in_(lowered))
        if customer_subclauses:
            clauses.append(or_(*customer_subclauses))
        if buckets.transporter_codes or buckets.transporter_names:
            from app.models.order import Transporter

            transporter_subclauses: list[Any] = []
            transporter_ids: list[str] = []
            if buckets.transporter_codes:
                lowered = [c.lower() for c in buckets.transporter_codes]
                rows = (
                    self.db.query(Transporter.id)
                    .filter(func.lower(Transporter.code).in_(lowered))
                    .all()
                )
                transporter_ids = [str(r[0]) for r in rows if r[0]]
                if transporter_ids:
                    transporter_subclauses.append(Order.transporter_id.in_(transporter_ids))
                for c in buckets.transporter_codes:
                    transporter_subclauses.append(Order.transporter.ilike(f"%{c}%"))
            if buckets.transporter_names:
                for n in buckets.transporter_names:
                    transporter_subclauses.append(Order.transporter.ilike(f"%{n}%"))
                rows = (
                    self.db.query(Transporter.id)
                    .filter(
                        or_(
                            func.lower(Transporter.name).in_(
                                [n.lower() for n in buckets.transporter_names]
                            ),
                            func.lower(Transporter.normalized_name).in_(
                                [n.lower() for n in buckets.transporter_names]
                            ),
                        )
                    )
                    .all()
                )
                extra_ids = [str(r[0]) for r in rows if r[0] and str(r[0]) not in transporter_ids]
                if extra_ids:
                    transporter_subclauses.append(Order.transporter_id.in_(extra_ids))
            if transporter_subclauses:
                clauses.append(or_(*transporter_subclauses))
        return clauses

    def get_order(self, order_id: str):
        """Get a single order by UUID or order_number (accepts either form)."""
        resolved_ids = resolve_identifier(
            self.db,
            order_id,
            Order,
            code_fields=("order_number",),
        )
        if not resolved_ids:
            raise handle_not_found("Order", order_id)
        order = (
            self.db.query(Order)
            .filter(Order.id.in_(resolved_ids), Order.deleted_at.is_(None))
            .options(
                joinedload(Order.lines).joinedload(OrderLine.product),
                joinedload(Order.lines).joinedload(OrderLine.warehouse),
            )
            .first()
        )
        if not order:
            raise handle_not_found("Order", order_id)
        return order

    def list_orders_by_product(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        customer_query: Optional[str] = None,
        product_query: Optional[str] = None,
        product_id: Optional[str] = None,
        has_actual_delivery_date: Optional[str] = None,
        order_date_from: Optional[datetime] = None,
        order_date_to: Optional[datetime] = None,
        actual_delivery_date_from: Optional[datetime] = None,
        actual_delivery_date_to: Optional[datetime] = None,
        sort_field: str = "order_date",
        sort_dir: str = "desc",
        entities: Optional[list[str]] = None,
        product_ids: Optional[list[str]] = None,
        customer_ids: Optional[list[str]] = None,
        transporter_ids: Optional[list[str]] = None,
    ):
        """List distinct orders matched by product search.

        `entities` is the single-bag entity filter (see list_orders). At least one
        entity must resolve to a product — the endpoint is product-centric and falls
        back to empty otherwise. Customer / transporter / order_number entities are
        applied as additional AND filters.
        """
        # Capture typed UUID kwargs before any local variable shadows them.
        _product_uuid_filter = list(product_ids) if product_ids else None
        _customer_uuid_filter = list(customer_ids) if customer_ids else None
        _transporter_uuid_filter = list(transporter_ids) if transporter_ids else None

        q = (
            self.db.query(Order)
            .join(Order.lines)
            .join(OrderLine.product)
            .filter(Order.deleted_at.is_(None))
            .distinct()
        )

        if _product_uuid_filter:
            q = q.filter(OrderLine.product_id.in_(_product_uuid_filter))

        if _customer_uuid_filter:
            from sqlalchemy import func as _func
            customer_names_subq = (
                self.db.query(Customer.customer_name)
                .filter(Customer.id.in_(_customer_uuid_filter))
                .subquery()
            )
            q = q.filter(
                or_(
                    Order.customer_id.in_(_customer_uuid_filter),
                    _func.lower(_func.btrim(Order.debtor_name)).in_(
                        self.db.query(_func.lower(_func.btrim(customer_names_subq.c.customer_name)))
                    ),
                )
            )

        if _transporter_uuid_filter:
            from sqlalchemy import func as _func
            transporter_names_subq = (
                self.db.query(Transporter.name)
                .filter(Transporter.id.in_(_transporter_uuid_filter))
                .subquery()
            )
            q = q.filter(
                or_(
                    Order.transporter_id.in_(_transporter_uuid_filter),
                    _func.lower(_func.btrim(Order.transporter)).in_(
                        self.db.query(_func.lower(_func.btrim(transporter_names_subq.c.name)))
                    ),
                )
            )

        entity_buckets: Optional[EntityFilterBuckets] = None
        if entities:
            entity_buckets = resolve_entities_to_filters(
                self.db,
                entities,
                allowed_entity_types=(
                    "product", "customer", "customer_order", "transporter",
                    "inbound_shipment", "spo_allocation", "grn", "promotion",
                    "attachment", "form",
                ),
            )
            # Caller passed `entities` but nothing resolved above the RAG
            # similarity threshold → return empty rather than fall through and
            # unintentionally list every order. Echo the unresolved inputs so the
            # agent surfaces "no match" to the user.
            if not entity_buckets.has_resolved_filter:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                    "resolved_entities": entity_buckets.as_echo(),
                }

        filters = []
        product_match_filters: list = []

        # Normalize `product_id` into a list of raw tokens. Accepts a single
        # UUID/SKU, a comma-separated string ("A,B"), or a Python list (n8n
        # repeated ?product_id=A&product_id=B). Each token is resolved through
        # the standard exact path first; tokens that still don't match a
        # product_code fall through to an embedding fuzzy resolve so the LLM
        # can hand us partials like "SRTWC8608" or "SRTWC8608-SC-UF" without
        # n8n having to canonicalise the SKU upstream.
        raw_tokens: list[str] = []
        if isinstance(product_id, list):
            for item in product_id:
                if item is None:
                    continue
                for piece in str(item).split(","):
                    piece = piece.strip()
                    if piece:
                        raw_tokens.append(piece)
        elif product_id is not None:
            for piece in str(product_id).split(","):
                piece = piece.strip()
                if piece:
                    raw_tokens.append(piece)
        raw_tokens = list(dict.fromkeys(raw_tokens))

        product_ids: list[str] = []
        if raw_tokens:
            for token in raw_tokens:
                ids = resolve_identifier(
                    self.db,
                    token,
                    Product,
                    code_fields=("product_code",),
                )
                if ids:
                    product_ids.extend(ids)
                    continue
                # Prefix / substring ILIKE on product_code — deterministic
                # match for partial SKUs like "SRTWC8608" → "SRTWC8608-SC",
                # "SRTWC8608-SC-UF". Capped to avoid runaway broad tokens.
                like_rows = (
                    self.db.query(Product.id, Product.product_code)
                    .filter(Product.product_code.ilike(f"%{token}%"))
                    .limit(20)
                    .all()
                )
                if like_rows:
                    product_ids.extend(str(r[0]) for r in like_rows)
                    continue
                # Embedding fuzzy fallback only when prefix/substring code
                # match yields nothing. Useful for descriptive tokens (e.g.
                # "kitchen sink") rather than partial codes.
                _fuzzy_clause, canonical_values = resolve_via_embedding_then_ilike(
                    self.db,
                    token,
                    source_type="product",
                    ilike_columns=[Product.product_code],
                    canonical_model=Product,
                    canonical_fields=("product_code",),
                )
                if canonical_values:
                    fuzzy_rows = (
                        self.db.query(Product.id)
                        .filter(Product.product_code.in_(canonical_values))
                        .all()
                    )
                    product_ids.extend(str(r[0]) for r in fuzzy_rows)
            product_ids = list(dict.fromkeys(product_ids))
            if not product_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            filters.append(OrderLine.product_id.in_(product_ids))
            product_match_filters.append(OrderLine.product_id.in_(product_ids))

        hadd = (has_actual_delivery_date or "").strip().lower()
        if hadd == "yes":
            filters.append(Order.actual_delivery_date.is_not(None))
        elif hadd == "no":
            filters.append(Order.actual_delivery_date.is_(None))

        if order_date_from is not None:
            filters.append(Order.order_date >= order_date_from)

        if order_date_to is not None:
            filters.append(Order.order_date <= order_date_to)

        if actual_delivery_date_from is not None:
            filters.append(Order.actual_delivery_date >= actual_delivery_date_from)

        if actual_delivery_date_to is not None:
            filters.append(Order.actual_delivery_date <= actual_delivery_date_to)

        query_filter = None
        if query and (query := (query or "").strip()):
            term = f"%{query}%"
            # Transporter sub-id set joined to the canonical transporters table
            # so by-product search also finds DOs by transporter code / name
            # (matches `list_orders` behavior).
            transporter_id_subq = (
                self.db.query(Transporter.id).filter(
                    or_(
                        Transporter.code.ilike(term),
                        Transporter.name.ilike(term),
                    )
                )
            )
            query_filter = or_(
                Order.order_number.ilike(term),
                Order.debtor_name.ilike(term),
                Order.transporter.ilike(term),  # legacy free-text column
                Order.transporter_id.in_(transporter_id_subq),
                Product.product_code.ilike(term),
                Product.product_name.ilike(term),
                Product.description.ilike(term),
            )
            product_match_filters.append(
                or_(
                    Product.product_code.ilike(term),
                    Product.product_name.ilike(term),
                    Product.description.ilike(term),
                )
            )
        if customer_query and (customer_query := (customer_query or "").strip()):
            customer_clause, _ = resolve_via_embedding_then_ilike(
                self.db,
                customer_query,
                source_type="customer",
                ilike_columns=[Order.debtor_name, Order.debtor_code],
                canonical_model=Customer,
                canonical_fields=("customer_name", "customer_code"),
                extra_filter_builders=[
                    lambda like: Order.customer.has(Customer.customer_name.ilike(like)),
                    lambda like: Order.customer.has(Customer.customer_code.ilike(like)),
                ],
            )
            if customer_clause is not None:
                filters.append(customer_clause)
        if product_query and (product_query := (product_query or "").strip()):
            product_clause, _ = resolve_via_embedding_then_ilike(
                self.db,
                product_query,
                source_type="product",
                ilike_columns=[
                    Product.product_code,
                    Product.product_name,
                    Product.description,
                ],
                canonical_model=Product,
                canonical_fields=("product_code", "product_name"),
            )
            if product_clause is not None:
                filters.append(product_clause)
                product_match_filters.append(product_clause)

        if entity_buckets is not None and entity_buckets.has_resolved_filter:
            entity_clauses = self._build_entity_filter_clauses(
                entity_buckets, product_join_already_present=True
            )
            filters.extend(entity_clauses)
            if entity_buckets.product_codes:
                product_match_filters.append(
                    func.lower(Product.product_code).in_(
                        [c.lower() for c in entity_buckets.product_codes]
                    )
                )

        # By-product endpoint is product-centric: if the caller passed `entities` but
        # zero of them resolved to a product (and no other product filter is in
        # play), there's nothing to look up. Return an explicit empty rather than
        # silently fanning across every order.
        if (
            entity_buckets is not None
            and entities
            and not entity_buckets.product_codes
            and not product_id
            and not product_query
            and not (query and query.strip())
        ):
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
                "resolved_entities": entity_buckets.as_echo(),
            }

        base_q = q.filter(and_(*filters)) if filters else q
        q = base_q.filter(query_filter) if query_filter is not None else base_q

        sort_map = {
            "order_number": Order.order_number,
            "order_date": Order.order_date,
            "actual_delivery_date": Order.actual_delivery_date,
            "debtor_name": Order.debtor_name,
            "created_at": Order.created_at,
            "updated_at": Order.updated_at,
        }
        sort_column = sort_map.get(sort_field, Order.order_date)
        if (sort_dir or "").lower() == "asc":
            q = q.order_by(sort_column.asc().nulls_last())
        else:
            q = q.order_by(sort_column.desc().nulls_last())

        total = q.count()
        if query_filter is not None and total == 0 and filters:
            # General fallback for noisy intent-like query text.
            q = base_q
            total = q.count()
        offset = (page - 1) * limit
        orders = q.offset(offset).limit(limit).all()

        # Attach matched_products per order so callers know which order line
        # caused the match (esp. important when product_id was an ilike /
        # fuzzy hit rather than an exact UUID).
        order_ids = [str(o.id) for o in orders]
        matched_by_order: dict[str, list[dict]] = {}
        if order_ids and product_match_filters:
            mq = (
                self.db.query(
                    OrderLine.order_id,
                    Product.id,
                    Product.product_code,
                    Product.product_name,
                )
                .join(Product, Product.id == OrderLine.product_id)
                .filter(OrderLine.order_id.in_(order_ids))
                .filter(and_(*product_match_filters))
            )
            seen: set[tuple[str, str]] = set()
            for oid, pid, pcode, pname in mq.distinct().all():
                key = (str(oid), str(pid))
                if key in seen:
                    continue
                seen.add(key)
                matched_by_order.setdefault(str(oid), []).append(
                    {"id": str(pid), "product_code": pcode, "product_name": pname}
                )
        for o in orders:
            setattr(o, "matched_products", matched_by_order.get(str(o.id), []))

        payload = {
            "data": orders,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
            },
            "empty": total == 0,
        }
        if entity_buckets is not None:
            payload["resolved_entities"] = entity_buckets.as_echo()
        return payload

    @staticmethod
    def _normalize_uuid_fields(data: dict, keys: tuple = ("customer_id", "order_status_id", "billing_address_id", "shipping_address_id")) -> dict:
        """Set empty-string UUID fields to None so PostgreSQL accepts them."""
        out = dict(data)
        for key in keys:
            if key in out and out[key] == "":
                out[key] = None
        return out

    def _upsert_customer_from_debtor(
        self,
        debtor_name: Optional[str],
        debtor_code: Optional[str],
    ) -> Optional[str]:
        """Find-or-create a Customer row from order debtor fields, return its id.

        Match key is the (customer_code, customer_name) PAIR — case + whitespace
        insensitive — because one Sage code can carry multiple distinct debtor
        names (e.g. "300-D093" maps to both "Deluxe Home Center (KTN)" and
        "Deluxe Home Center AC (I)"). Each unique pair gets its own customers
        row. Matches the composite unique index created in migration 220.

        When debtor_code is missing, fall back to a deterministic `DBR-<hash>`
        slug derived from the name so the same blank-code debtor doesn't
        explode into duplicate rows.
        """
        name = (debtor_name or "").strip()
        if not name:
            return None
        code = (debtor_code or "").strip()
        if not code:
            import hashlib
            code = "DBR-" + hashlib.md5(name.lower().encode("utf-8")).hexdigest()[:10]
        # Pair match (case + whitespace normalized on both columns).
        existing = (
            self.db.query(Customer)
            .filter(
                func.lower(func.btrim(Customer.customer_code)) == code.lower(),
                func.lower(func.btrim(Customer.customer_name)) == name.lower(),
            )
            .first()
        )
        if existing is not None:
            return str(existing.id)
        new_customer = Customer(
            customer_code=code,
            customer_name=name,
            customer_type="company",
            is_active=True,
        )
        self.db.add(new_customer)
        # Flush so the new id is available before the order persists; commit
        # remains with the order so a single transaction wraps both writes.
        self.db.flush()
        return str(new_customer.id)

    def _upsert_transporter_from_text(self, transporter_text: Optional[str]) -> Optional[str]:
        """Find-or-create a Transporter row keyed by normalized_name, return id.

        Mirrors migration 200's seeding rule. `normalized_name = lower(btrim(...))`
        is the unique key — code + name default to the raw stripped text on
        first sight.
        """
        raw = (transporter_text or "").strip()
        if not raw:
            return None
        normalized = raw.lower()
        existing = (
            self.db.query(Transporter)
            .filter(Transporter.normalized_name == normalized)
            .first()
        )
        if existing is not None:
            return str(existing.id)
        new_row = Transporter(
            code=raw,
            name=raw,
            normalized_name=normalized,
        )
        self.db.add(new_row)
        self.db.flush()
        return str(new_row.id)

    def _sync_order_master_refs(self, order_dict: dict) -> dict:
        """Populate `customer_id` and `transporter_id` from text fields, in place.

        Called by create_order / update_order before persistence. Only writes
        the FK when (a) the caller did not supply one explicitly, OR (b) the
        existing value does not match the text field (text edit re-points the
        FK). Idempotent: master rows are deduped via the unique
        `customer_code` / `transporters.normalized_name` indexes.
        """
        out = dict(order_dict)

        debtor_name = out.get("debtor_name")
        if debtor_name:
            cid = self._upsert_customer_from_debtor(debtor_name, out.get("debtor_code"))
            if cid:
                out["customer_id"] = cid  # always re-point; debtor_name edit can change customer

        transporter_text = out.get("transporter")
        if transporter_text:
            tid = self._upsert_transporter_from_text(transporter_text)
            if tid:
                out["transporter_id"] = tid

        return out

    def create_order(self, order_data: OrderCreate, created_by: str):
        """Create a new order."""
        # Check if order_number already exists
        existing = self.db.query(Order).filter(Order.order_number == order_data.order_number).first()
        if existing:
            raise handle_conflict("Order number already exists. Please use a different number.")
        
        # Calculate total if not provided
        subtotal = order_data.subtotal_amount or Decimal("0")
        discount = order_data.discount_amount or Decimal("0")
        tax = order_data.tax_amount or Decimal("0")
        total = subtotal - discount + tax
        
        order_dict = order_data.model_dump()
        order_dict = self._normalize_uuid_fields(order_dict)
        # Auto-upsert customer + transporter master rows from text fields so the
        # FKs stay populated for every new order (mirrors migrations 200/206/207).
        order_dict = self._sync_order_master_refs(order_dict)
        order_dict["total_amount"] = total
        order_dict["created_by"] = created_by

        order = Order(**order_dict)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def update_order(self, order_id: str, order_data: OrderUpdate, updated_by: str):
        """Update an order."""
        order = self.get_order(order_id)
        
        update_data = order_data.model_dump(exclude_unset=True)
        if update_data:
            update_data = self._normalize_uuid_fields(update_data)
            # Recalculate total if amounts changed
            if any(k in update_data for k in ["subtotal_amount", "discount_amount", "tax_amount"]):
                subtotal = update_data.get("subtotal_amount", order.subtotal_amount) or Decimal("0")
                discount = update_data.get("discount_amount", order.discount_amount) or Decimal("0")
                tax = update_data.get("tax_amount", order.tax_amount) or Decimal("0")
                update_data["total_amount"] = subtotal - discount + tax

            # Re-sync customer_id / transporter_id whenever debtor_name /
            # debtor_code / transporter text changes on update. Carry the
            # pre-existing values forward so the upsert sees full context even
            # if the caller only patched one field.
            text_view = {
                "debtor_name": update_data.get("debtor_name", order.debtor_name),
                "debtor_code": update_data.get("debtor_code", order.debtor_code),
                "transporter": update_data.get("transporter", order.transporter),
            }
            synced = self._sync_order_master_refs(text_view)
            if "customer_id" in synced:
                update_data["customer_id"] = synced["customer_id"]
            if "transporter_id" in synced:
                update_data["transporter_id"] = synced["transporter_id"]

            update_data["updated_by"] = updated_by
            for key, value in update_data.items():
                setattr(order, key, value)

            self.db.commit()
            self.db.refresh(order)

        return order

    def create_order_line(self, order_id: str, data: OrderLineCreate):
        """Add a line to an order. Lines are ordered by line_sequence (multiple lines may share product+warehouse)."""
        self.get_order(order_id)  # ensure order exists
        next_seq = (
            self.db.query(func.coalesce(func.max(OrderLine.line_sequence), 0))
            .filter(OrderLine.order_id == order_id)
            .scalar()
        )
        next_seq = int(next_seq or 0) + 1
        line = OrderLine(order_id=order_id, line_sequence=next_seq, **data.model_dump())
        self.db.add(line)
        self.db.commit()
        self.db.refresh(line)
        return line

    def update_order_line(self, order_id: str, line_id: str, data: OrderLineUpdate):
        """Update an order line."""
        line = (
            self.db.query(OrderLine)
            .filter(OrderLine.id == line_id, OrderLine.order_id == order_id)
            .first()
        )
        if not line:
            raise handle_not_found("Order line", line_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(line, key, value)
        self.db.commit()
        self.db.refresh(line)
        return line

    def delete_order_line(self, order_id: str, line_id: str):
        """Remove an order line."""
        line = (
            self.db.query(OrderLine)
            .filter(OrderLine.id == line_id, OrderLine.order_id == order_id)
            .first()
        )
        if not line:
            raise handle_not_found("Order line", line_id)
        self.db.delete(line)
        self.db.commit()
        return {"message": "Order line deleted"}

    def bulk_delete_order_lines(self, order_id: str, line_ids: list[str]):
        """Delete multiple lines from an order by line IDs."""
        if not line_ids:
            return {"message": "No order lines to delete", "deleted_count": 0}
        deleted = (
            self.db.query(OrderLine)
            .filter(OrderLine.order_id == order_id, OrderLine.id.in_(line_ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {"message": f"Deleted {deleted} order line(s)", "deleted_count": deleted}

    def get_order_by_order_number(self, order_number: str):
        """Get order by order_number (doc no). Returns None if not found."""
        if not (order_number or "").strip():
            return None
        return (
            self.db.query(Order)
            .filter(Order.deleted_at.is_(None), Order.order_number == (order_number or "").strip())
            .first()
        )

    def _get_order_any(self, order_id: str):
        """Get order by ID including archived."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise handle_not_found("Order", order_id)
        return order

    def archive_order(self, order_id: str):
        """Archive an order (soft delete). Data remains for retention."""
        from datetime import datetime, timezone
        order = self.get_order(order_id)
        order.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"message": "Order archived successfully"}

    def restore_order(self, order_id: str):
        """Restore an archived order."""
        order = self._get_order_any(order_id)
        if order.deleted_at is None:
            raise handle_conflict("Order is not archived")
        order.deleted_at = None
        self.db.commit()
        return {"message": "Order restored successfully"}

    def delete_order(self, order_id: str):
        """Hard delete an order (permanent). Use archive for retention."""
        order = self._get_order_any(order_id)
        self.db.delete(order)
        self.db.commit()
        return {"message": "Order deleted successfully"}

    def bulk_delete_orders(self, order_ids: list[str]):
        """Delete multiple orders by ID. Returns count of deleted."""
        if not order_ids:
            return {"message": "No orders to delete", "deleted_count": 0}
        deleted = self.db.query(Order).filter(Order.id.in_(order_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"message": f"Deleted {deleted} order(s)", "deleted_count": deleted}

    def bulk_import_orders(self, orders_data: list[dict], user_id: str):
        """Bulk import orders from Excel data.
        
        Args:
            orders_data: List of dictionaries containing order data from Excel
            user_id: ID of the user performing the import
            
        Returns:
            dict with created, updated counts and errors
        """
        from datetime import datetime
        import re
        
        created = 0
        updated = 0
        errors = []
        warnings = []
        
        # Column mapping from Excel headers to database fields
        column_mapping = {
            'id': 'id',
            'ID': 'id',
            'order_number': 'order_number',
            'Order Number': 'order_number',
            'order_date': 'order_date',
            'Order Date': 'order_date',
            'estimated_delivery_date': 'estimated_delivery_date',
            'Estimated Delivery Date': 'estimated_delivery_date',
            'Promised Delivery Date': 'estimated_delivery_date',  # legacy Excel headers
            'promised_delivery_date': 'estimated_delivery_date',  # legacy column / export key
            'actual_delivery_date': 'actual_delivery_date',
            'Actual Delivery Date': 'actual_delivery_date',
            'customer_id': 'customer_id',
            'Customer ID': 'customer_id',
            'order_status_id': 'order_status_id',
            'Order Status ID': 'order_status_id',
            'subtotal_amount': 'subtotal_amount',
            'Subtotal Amount': 'subtotal_amount',
            'discount_amount': 'discount_amount',
            'Discount Amount': 'discount_amount',
            'tax_amount': 'tax_amount',
            'Tax Amount': 'tax_amount',
            'total_amount': 'total_amount',
            'Total Amount': 'total_amount',
            'remarks': 'remarks',
            'Remarks': 'remarks',
            'billing_address_id': 'billing_address_id',
            'Billing Address ID': 'billing_address_id',
            'shipping_address_id': 'shipping_address_id',
            'Shipping Address ID': 'shipping_address_id',
        }
        
        def parse_date(value):
            """Parse date from various formats."""
            if not value or value == '':
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                # Try ISO format first
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except:
                    pass
                # Try other common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(value, fmt)
                    except:
                        continue
            return None
        
        def parse_decimal(value):
            """Parse decimal value."""
            if value is None or value == '':
                return Decimal("0")
            try:
                return Decimal(str(value))
            except:
                return Decimal("0")
        
        for idx, row_data in enumerate(orders_data, start=1):
            try:
                # Map Excel columns to database fields
                mapped_data = {}
                for excel_key, value in row_data.items():
                    db_key = column_mapping.get(excel_key, excel_key.lower())
                    if db_key in ['order_date', 'estimated_delivery_date', 'actual_delivery_date']:
                        mapped_data[db_key] = parse_date(value)
                    elif db_key in ['subtotal_amount', 'discount_amount', 'tax_amount', 'total_amount']:
                        mapped_data[db_key] = parse_decimal(value)
                    elif db_key in ['customer_id', 'order_status_id', 'billing_address_id', 'shipping_address_id']:
                        # Convert to string, handle empty values
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                    elif db_key in ['order_number', 'remarks']:
                        mapped_data[db_key] = str(value).strip() if value else None
                    elif db_key == 'id':
                        # ID is optional - if provided, will update; if not, will create
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                
                order_id = mapped_data.pop('id', None)
                
                # Validate required fields
                if not mapped_data.get('order_number'):
                    errors.append(f"Row {idx}: Order Number is required")
                    continue
                
                # Check if order exists (by ID first, then by order_number)
                existing_order = None
                
                # First, try to find by ID if provided
                if order_id:
                    existing_order = self.db.query(Order).filter(
                        Order.id == order_id,
                        Order.deleted_at.is_(None)
                    ).first()
                
                # If not found by ID, try to find by order_number
                if not existing_order:
                    existing_order = self.db.query(Order).filter(
                        Order.order_number == mapped_data['order_number'],
                        Order.deleted_at.is_(None)
                    ).first()
                
                # If creating new order, check for duplicate order_number
                if not existing_order:
                    duplicate = self.db.query(Order).filter(
                        Order.order_number == mapped_data['order_number'],
                        Order.deleted_at.is_(None)
                    ).first()
                    if duplicate:
                        errors.append(f"Row {idx}: Order Number '{mapped_data['order_number']}' already exists")
                        continue
                
                # Calculate total if not provided
                if 'total_amount' not in mapped_data or not mapped_data['total_amount']:
                    subtotal = mapped_data.get('subtotal_amount', Decimal("0")) or Decimal("0")
                    discount = mapped_data.get('discount_amount', Decimal("0")) or Decimal("0")
                    tax = mapped_data.get('tax_amount', Decimal("0")) or Decimal("0")
                    mapped_data['total_amount'] = subtotal - discount + tax
                
                if existing_order:
                    # Update existing order
                    for key, value in mapped_data.items():
                        if key != 'order_number':  # Don't update order_number
                            setattr(existing_order, key, value)
                    existing_order.updated_by = user_id
                    updated += 1
                else:
                    # Create new order
                    mapped_data['created_by'] = user_id
                    order = Order(**mapped_data)
                    self.db.add(order)
                    created += 1
                
            except Exception as e:
                error_msg = f"Row {idx}: {str(e)}"
                errors.append(error_msg)
                continue
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            errors.append(f"Database error: {str(e)}")
        
        return {
            "created": created,
            "updated": updated,
            "errors": errors
        }

    def import_excel_tracking(self, file_data: bytes, user_id: str, validate_only: bool = False):
        """Import orders from Excel file with Master and Overall Tracking sheets. If validate_only=True, run validation and return errors/warnings without persisting (rollback)."""
        from io import BytesIO
        from datetime import datetime, date, time as dt_time, timedelta
        import openpyxl
        from decimal import Decimal

        created = 0
        updated = 0
        errors = []
        warnings = []
        kpi_warnings = []
        import_session_id = str(uuid.uuid4())
        start_time = time.monotonic()
        master_rows = 0
        tracking_rows = 0
        calendar_service = CalendarService(self.db)

        # Resolve "new" and "delivered" status ids (case-insensitive match to status_code)
        status_rows = (
            self.db.query(OrderStatus)
            .filter(func.lower(OrderStatus.status_code).in_(["new", "delivered"]))
            .all()
        )
        status_by_code_lower = {str(s.status_code).lower(): s.id for s in status_rows}
        new_status_id = status_by_code_lower.get("new")
        delivered_status_id = status_by_code_lower.get("delivered")

        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            raise ValueError(f"Failed to read Excel file: {exc}") from exc

        logger.info("Order tracking import: opened workbook, sheets=%s", workbook.sheetnames)

        required_sheets = {"Master", "Overall Tracking"}
        if not required_sheets.issubset(set(workbook.sheetnames)):
            missing = required_sheets.difference(set(workbook.sheetnames))
            raise ValueError(f"Missing required sheet(s): {', '.join(sorted(missing))}")

        master_sheet = workbook["Master"]
        tracking_sheet = workbook["Overall Tracking"]

        master_mapping = {
            "Doc. No.": "order_number",
            "Date": "order_date",
            "Created Time": "created_time",
            "Debtor Code": "debtor_code",
            "Debtor Name": "debtor_name",
            "Agent": "agent",
            "Cancel": "is_cancelled",
            "Remarks CS": "remarks_cs",
            "Type": "order_type",
        }

        tracking_mapping = {
            "Doc Number": "order_number",
            "Doc No.": "order_number",
            "Date": "actual_delivery_date",
            "Delivery Date": "actual_delivery_date",
            "Time": "pickup_time",
            "Checker": "checker",
            "Transporter": "transporter",
            "Driver Name": "driver_name",
            "Lorry Plate": "lorry_plate",
            "Customer": "customer_ref",
            "Remarks CS": "delivery_remarks_cs",
            "Remarks": "delivery_remarks",
            "Salesman": "salesman",
            "Trips": "trips",
            "W/H": "warehouse",
            "Doc Date": "doc_date",
        }

        def normalize_header(value):
            return str(value).strip() if value is not None else ""

        def iter_sheet_rows(sheet, sheet_name_for_log=""):
            headers = [normalize_header(cell.value) for cell in sheet[1]]
            if sheet_name_for_log:
                logger.info("Order tracking import: sheet %r headers (row 1)=%s", sheet_name_for_log, headers)
            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not any(cell is not None and str(cell).strip() for cell in row):
                    continue
                row_data = {}
                for idx, value in enumerate(row):
                    header = headers[idx] if idx < len(headers) else ""
                    if header:
                        row_data[header] = value
                yield row_idx, row_data

        def chunked(values, size):
            for i in range(0, len(values), size):
                yield values[i:i + size]

        def normalize_order_number(value):
            if value is None:
                return ""
            return str(value).strip()

        master_rows_list = list(iter_sheet_rows(master_sheet, "Master"))
        tracking_rows_list = list(iter_sheet_rows(tracking_sheet, "Overall Tracking"))
        master_rows = len(master_rows_list)
        tracking_rows = len(tracking_rows_list)

        master_order_numbers = {
            normalize_order_number(row_data.get("Doc. No.")).lower()
            for _, row_data in master_rows_list
            if normalize_order_number(row_data.get("Doc. No."))
        }
        tracking_order_numbers = {
            normalize_order_number(row_data.get("Doc Number") or row_data.get("Doc No.")).lower()
            for _, row_data in tracking_rows_list
            if normalize_order_number(row_data.get("Doc Number") or row_data.get("Doc No."))
        }
        all_order_numbers = master_order_numbers.union(tracking_order_numbers)

        existing_orders = {}
        if all_order_numbers:
            for number_chunk in chunked(sorted(all_order_numbers), 500):
                orders = self.db.query(Order).filter(
                    func.lower(Order.order_number).in_(number_chunk),
                    Order.deleted_at.is_(None)
                ).all()
                for order in orders:
                    if order.order_number:
                        existing_orders[order.order_number.lower()] = order

        def parse_date_value(value, doc_date_value=None):
            if value is None or value == "":
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, date):
                return datetime.combine(value, dt_time.min)
            if isinstance(value, str):
                cleaned = value.strip()
                for fmt in ["%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        return datetime.strptime(cleaned, fmt)
                    except ValueError:
                        continue
                try:
                    parsed = datetime.strptime(cleaned, "%d-%b")
                    year = doc_date_value.year if isinstance(doc_date_value, (datetime, date)) else datetime.now().year
                    return parsed.replace(year=year)
                except ValueError:
                    return None
            return None

        def parse_time_value(value):
            if value is None or value == "":
                return None
            if isinstance(value, dt_time):
                return value
            if isinstance(value, datetime):
                return value.time()
            if isinstance(value, str):
                cleaned = value.strip()
                for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"]:
                    try:
                        return datetime.strptime(cleaned, fmt).time()
                    except ValueError:
                        continue
            return None

        def parse_bool(value):
            if value is None or value == "":
                return False
            if isinstance(value, bool):
                return value
            return str(value).strip().upper() not in {"F", "FALSE", "0", "NO", "N"}

        def json_safe(value):
            if isinstance(value, (datetime, date, dt_time)):
                return value.isoformat()
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {str(k): json_safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [json_safe(v) for v in value]
            return value

        working_weekdays = calendar_service.get_working_weekdays()

        mapped_master_rows = []
        min_master_date = None
        max_master_date = None
        touched_orders: list[Order] = []

        # Process Master sheet
        for row_idx, row_data in master_rows_list:
            try:
                mapped = {}
                for header, value in row_data.items():
                    if header not in master_mapping:
                        continue
                    db_key = master_mapping[header]
                    if db_key in {"order_date", "created_time"}:
                        mapped[db_key] = parse_date_value(value)
                    elif db_key == "is_cancelled":
                        mapped[db_key] = parse_bool(value)
                    else:
                        mapped[db_key] = str(value).strip() if value is not None else None

                order_number = (mapped.get("order_number") or "").strip()
                if not order_number:
                    errors.append({"row": row_idx, "error": "Doc. No. is required", "data": row_data})
                    continue
                mapped["order_number"] = order_number
                order_date_value = mapped.get("order_date")
                if isinstance(order_date_value, (datetime, date)):
                    date_value = order_date_value.date() if isinstance(order_date_value, datetime) else order_date_value
                    min_master_date = date_value if min_master_date is None else min(min_master_date, date_value)
                    max_master_date = date_value if max_master_date is None else max(max_master_date, date_value)
                mapped_master_rows.append((row_idx, row_data, mapped))
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        holidays_master = set()
        if min_master_date and max_master_date:
            holidays_master = calendar_service.get_public_holidays_between(
                min_master_date,
                max_master_date + timedelta(days=30),
            )

        for row_idx, row_data, mapped in mapped_master_rows:
            try:
                if mapped.get("order_date"):
                    mapped["estimated_delivery_date"] = calendar_service.add_business_days(
                        mapped["order_date"],
                        2,
                        working_weekdays=working_weekdays,
                        holidays=holidays_master,
                    )

                order_number = mapped["order_number"]
                existing_order = existing_orders.get(order_number.lower())

                if existing_order:
                    for key, value in mapped.items():
                        if key != "order_number":
                            setattr(existing_order, key, value)
                    # Orders without actual delivery date should be "new"; Tracking will set "delivered" where applicable
                    if new_status_id:
                        existing_order.order_status_id = new_status_id
                    existing_order.updated_by = user_id
                    updated += 1
                    touched_orders.append(existing_order)
                else:
                    mapped["created_by"] = user_id
                    if new_status_id:
                        mapped["order_status_id"] = new_status_id
                    order = Order(**mapped)
                    self.db.add(order)
                    created += 1
                    existing_orders[order_number.lower()] = order
                    touched_orders.append(order)
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        tracking_updates = []
        min_tracking_date = None
        max_tracking_date = None

        # Process Overall Tracking sheet
        for row_idx, row_data in tracking_rows_list:
            try:
                mapped = {}
                doc_date_value = None
                for header, value in row_data.items():
                    if header not in tracking_mapping:
                        continue
                    db_key = tracking_mapping[header]
                    if db_key == "doc_date":
                        doc_date_value = parse_date_value(value)
                        continue
                    if db_key == "actual_delivery_date":
                        mapped[db_key] = parse_date_value(value, doc_date_value=doc_date_value)
                    elif db_key == "trips":
                        mapped[db_key] = int(value) if value not in (None, "") else None
                    else:
                        mapped[db_key] = str(value).strip() if value is not None else None

                order_number = (mapped.get("order_number") or "").strip()
                if not order_number:
                    errors.append({"row": row_idx, "error": "Doc Number is required", "data": row_data})
                    continue

                order = existing_orders.get(order_number.lower())
                if not order:
                    warnings.append({"row": row_idx, "warning": f"Order '{order_number}' not found in Master sheet", "data": row_data})
                    continue

                delivery_date = mapped.get("actual_delivery_date")
                pickup_time = parse_time_value(row_data.get("Time"))
                if delivery_date:
                    if pickup_time:
                        mapped["actual_delivery_date"] = datetime.combine(
                            delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date,
                            pickup_time,
                        )
                    else:
                        # Date only: store as midnight for DateTime column
                        d = delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date
                        mapped["actual_delivery_date"] = datetime.combine(d, dt_time.min)
                    delivery_date = mapped["actual_delivery_date"]

                for key, value in mapped.items():
                    if key != "order_number":
                        setattr(order, key, value)

                if order.order_date and delivery_date:
                    start_date_value = order.order_date.date() if isinstance(order.order_date, datetime) else order.order_date
                    end_date_value = delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date
                    min_tracking_date = start_date_value if min_tracking_date is None else min(min_tracking_date, start_date_value)
                    max_tracking_date = end_date_value if max_tracking_date is None else max(max_tracking_date, end_date_value)
                    tracking_updates.append((order, delivery_date))
                    if delivered_status_id:
                        order.order_status_id = delivered_status_id
                else:
                    order.delivery_days = None
                    order.kpi_warning = False
                    if new_status_id:
                        order.order_status_id = new_status_id

                order.updated_by = user_id
                updated += 1
                touched_orders.append(order)
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        holidays_tracking = set()
        if min_tracking_date and max_tracking_date:
            holidays_tracking = calendar_service.get_public_holidays_between(min_tracking_date, max_tracking_date)

        for order, delivery_date in tracking_updates:
            delivery_days = calendar_service.business_days_between(
                order.order_date,
                delivery_date,
                working_weekdays=working_weekdays,
                holidays=holidays_tracking,
            )
            order.delivery_days = delivery_days
            order.kpi_warning = delivery_days > 2
            if order.kpi_warning:
                kpi_warnings.append({"order_number": order.order_number, "days": delivery_days})

        logger.info(
            "Order tracking import: Master rows=%s, Tracking rows=%s, created=%s, updated=%s, errors=%s",
            master_rows, tracking_rows, created, updated, len(errors),
        )
        for i, err in enumerate(errors[:5]):
            if isinstance(err, dict):
                data = err.get("data")
                if isinstance(data, dict):
                    data_keys = list(data.keys())
                elif isinstance(data, list):
                    data_keys = f"list({len(data)})"
                else:
                    data_keys = type(data).__name__ if data is not None else None
                logger.warning(
                    "Order tracking import error [%s]: row=%s %s | data keys=%s",
                    i + 1,
                    err.get("row"),
                    err.get("error"),
                    data_keys,
                )
            else:
                logger.warning("Order tracking import error [%s]: %s", i + 1, err)
        for i, warn in enumerate(warnings[:5]):
            if isinstance(warn, dict):
                data = warn.get("data")
                if isinstance(data, dict):
                    data_keys = list(data.keys())
                elif isinstance(data, list):
                    data_keys = f"list({len(data)})"
                else:
                    data_keys = type(data).__name__ if data is not None else None
                logger.warning(
                    "Order tracking import warning [%s]: row=%s %s | data keys=%s",
                    i + 1,
                    warn.get("row"),
                    warn.get("warning"),
                    data_keys,
                )
            else:
                logger.warning("Order tracking import warning [%s]: %s", i + 1, warn)
        if len(errors) > 5:
            logger.warning("Order tracking import: ... and %s more errors", len(errors) - 5)

        if validate_only:
            self.db.rollback()
            err_list = [e.get("error", str(e)) if isinstance(e, dict) else str(e) for e in errors]
            warn_list = [w.get("warning", str(w)) if isinstance(w, dict) else str(w) for w in warnings]
            return {
                "valid": len(errors) == 0,
                "errors": err_list,
                "warnings": warn_list,
                "summary": {
                    "master_rows": master_rows,
                    "tracking_rows": tracking_rows,
                    "would_create": created,
                    "would_update": updated,
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "kpi_warnings": kpi_warnings,
                },
            }

        try:
            with suppress_embedding_events("order"):
                self.db.flush()
                seen: set[str] = set()
                touched_ids: list[str] = []
                for o in touched_orders:
                    oid = getattr(o, "id", None)
                    if oid is None:
                        continue
                    sid = str(oid)
                    if sid in seen:
                        continue
                    seen.add(sid)
                    touched_ids.append(sid)
                enqueued = bulk_enqueue_embedding_events(
                    self.db, "order", touched_ids, event_type="order.updated"
                )
                logger.info(
                    "Order tracking import: bulk-enqueued %s embedding events (touched=%s)",
                    enqueued, len(touched_orders),
                )
                self.db.commit()
        except Exception as exc:
            self.db.rollback()
            errors.append({"row": None, "error": f"Database error: {exc}", "data": None})
            logger.exception("Order tracking import: database commit failed")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        if not validate_only:
            try:
                import_log_service = ImportLogService(self.db)
                import_log_service.create_import_log(
                    entity_type="order",
                    entity_table="orders",
                    import_session_id=import_session_id,
                    filename=None,
                    import_type="EXCEL_IMPORT",
                    total_rows=master_rows + tracking_rows,
                    successful_rows=created + updated,
                    created_rows=created,
                    updated_rows=updated,
                    failed_rows=len(errors),
                    skipped_rows=len(warnings),
                    warnings=json_safe(warnings),
                    errors=json_safe(errors),
                    summary=json_safe({"kpi_warnings": kpi_warnings, "master_rows": master_rows, "tracking_rows": tracking_rows, "warnings": len(warnings)}),
                    imported_by=user_id,
                    duration_ms=duration_ms,
                )
            except Exception:
                pass

        return {
            "import_session_id": import_session_id,
            "created": created,
            "updated": updated,
            "errors": errors,
            "warnings": warnings,
            "kpi_warnings": kpi_warnings,
            "master_rows": master_rows,
            "tracking_rows": tracking_rows,
        }

    def validate_delivery_order_detail_excel(self, file_data: bytes) -> dict:
        """Validate delivery order detail import file (order lines) without writing to DB."""
        import openpyxl
        from app.api.v1.external.utils import normalize_code

        def _normalize_header(value) -> str:
            if value is None:
                return ""
            return str(value).strip().lower()

        def _find(row_d: dict, *candidates: str):
            for c in candidates:
                key = c.lower().strip()
                if key in row_d:
                    return row_d.get(key)
            return None

        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            raise ValueError(f"Failed to read Excel file: {exc}") from exc

        sheet = workbook.active
        if not sheet:
            raise ValueError("Workbook has no active sheet")

        headers = [_normalize_header(cell.value) for cell in sheet[1]]
        parsed_rows = []
        all_doc_nos = set()
        all_product_codes = set()
        all_locations = set()
        errors: list[str] = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue

            row_data: dict = {}
            for idx, value in enumerate(row):
                if idx < len(headers) and headers[idx]:
                    row_data[headers[idx]] = value

            doc_no = (_find(row_data, "doc no", "doc number", "order number") and str(_find(row_data, "doc no", "doc number", "order number")).strip()) or None
            item_code = (_find(row_data, "item code", "product code") and str(_find(row_data, "item code", "product code")).strip()) or None
            location = (_find(row_data, "location", "warehouse", "warehouse code") and str(_find(row_data, "location", "warehouse", "warehouse code")).strip()) or None

            # Ignore trailing / formatted "empty" rows (e.g. stray 0, F, or styled blanks) with no line identity
            if not doc_no and not item_code and not location:
                continue

            if not doc_no:
                errors.append(f"Row {row_idx}: Missing doc no")
            if not item_code:
                errors.append(f"Row {row_idx}: Missing item code")
            if not location:
                errors.append(f"Row {row_idx}: Missing location")

            if doc_no:
                all_doc_nos.add(doc_no)
            if item_code:
                all_product_codes.add(item_code)
            if location:
                all_locations.add(location)

            parsed_rows.append((row_idx, doc_no, item_code, location))

        orders_by_number = {}
        if all_doc_nos:
            for order in self.db.query(Order).filter(Order.order_number.in_(all_doc_nos), Order.deleted_at.is_(None)).all():
                orders_by_number[order.order_number] = order

        products_by_code = {}
        if all_product_codes:
            for product in self.db.query(Product).filter(Product.product_code.in_(all_product_codes)).all():
                products_by_code[(product.product_code or "").strip()] = product

        warehouses_map = {}
        if all_locations:
            all_warehouses = self.db.query(Warehouse).all()
            for wh in all_warehouses:
                if wh.warehouse_code:
                    warehouses_map[normalize_code(wh.warehouse_code)] = wh
                if wh.warehouse_name:
                    warehouses_map[normalize_code(wh.warehouse_name)] = wh

        for row_idx, doc_no, item_code, location in parsed_rows:
            if not doc_no or not item_code or not location:
                continue
            if doc_no not in orders_by_number:
                errors.append(f"Row {row_idx}: Order not found: {doc_no}")
            if item_code not in products_by_code:
                errors.append(f"Row {row_idx}: Product not found: {item_code}")
            if normalize_code(location) not in warehouses_map:
                errors.append(f"Row {row_idx}: Warehouse not found: {location}")

        total_rows = len(parsed_rows)
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
            "summary": {
                "rows": total_rows,
                "error_count": len(errors),
            },
        }


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_customers(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List customers."""
        q = self.db.query(Customer)
        
        if query:
            q = q.filter(
                or_(
                    Customer.customer_code.ilike(f"%{query}%"),
                    Customer.customer_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        customers = q.offset(offset).limit(limit).all()
        
        return {
            "data": customers,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_customer(self, customer_id: str):
        """Get a customer by ID."""
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise handle_not_found("Customer", customer_id)
        return customer
    
    def create_customer(self, customer_data: CustomerCreate):
        """Create a new customer.

        Uniqueness is on the (customer_code, customer_name) pair — case +
        whitespace insensitive — so the same Sage code can legitimately host
        multiple debtor names (e.g. "300-D093" for "Deluxe Home Center (KTN)"
        and "Deluxe Home Center AC (I)").
        """
        code = (customer_data.customer_code or "").strip()
        name = (customer_data.customer_name or "").strip()
        existing = self.db.query(Customer).filter(
            func.lower(func.btrim(Customer.customer_code)) == code.lower(),
            func.lower(func.btrim(Customer.customer_name)) == name.lower(),
        ).first()
        if existing:
            raise handle_conflict("Customer with this code + name already exists.")

        customer = Customer(**customer_data.model_dump())
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer
    
    def update_customer(self, customer_id: str, customer_data: CustomerUpdate):
        """Update a customer."""
        customer = self.get_customer(customer_id)
        
        update_data = customer_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(customer, key, value)
        
        self.db.commit()
        self.db.refresh(customer)
        return customer


class OrderStatusService:
    """Service for order status operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_order_statuses(self, page: int = 1, limit: int = 50):
        """List order statuses."""
        q = self.db.query(OrderStatus).order_by(OrderStatus.sequence)
        
        total = q.count()
        offset = (page - 1) * limit
        statuses = q.offset(offset).limit(limit).all()
        
        return {
            "data": statuses,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_order_status(self, status_id: str):
        """Get an order status by ID."""
        status = self.db.query(OrderStatus).filter(OrderStatus.id == status_id).first()
        if not status:
            raise handle_not_found("Order Status", status_id)
        return status
    
    def create_order_status(self, status_data: OrderStatusCreate):
        """Create a new order status."""
        existing = self.db.query(OrderStatus).filter(
            OrderStatus.status_code == status_data.status_code
        ).first()
        if existing:
            raise handle_conflict("Status code already exists.")
        
        status = OrderStatus(**status_data.model_dump())
        self.db.add(status)
        self.db.commit()
        self.db.refresh(status)
        return status
    
    def update_order_status(self, status_id: str, status_data: OrderStatusUpdate):
        """Update an order status."""
        status = self.get_order_status(status_id)
        
        update_data = status_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(status, key, value)
        
        self.db.commit()
        self.db.refresh(status)
        return status
