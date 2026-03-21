"""Dynamic export rows (flattened for order lines) using same filter compiler as list search."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, exists, not_, or_
from sqlalchemy.orm import Session, joinedload

from app.models.order import Customer, Order, OrderLine
from app.models.product import Product
from app.models.procurement import Supplier
from app.schemas.list_query import ListExportRequest
from app.services.list_query_metadata_service import ListQueryMetadataService
from app.services.query.filter_compiler import compile_optional_filter


def _json_safe(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bool):
        return val
    return val


def _value_from_obj(obj: Any, compile_key: str) -> Any:
    _, attr = compile_key.split(".", 1)
    return _json_safe(getattr(obj, attr, None))


def _value_from_line_export(line: Any, compile_key: str) -> Any:
    """Resolve line.* and line.product.* / line.warehouse.* for flattened order-line export."""
    parts = compile_key.split(".")
    if not parts or parts[0] != "line":
        return None
    if len(parts) == 2:
        return _json_safe(getattr(line, parts[1], None))
    if len(parts) == 3 and parts[1] == "product":
        prod = getattr(line, "product", None)
        return _json_safe(getattr(prod, parts[2], None) if prod is not None else None)
    if len(parts) == 3 and parts[1] == "warehouse":
        wh = getattr(line, "warehouse", None)
        return _json_safe(getattr(wh, parts[2], None) if wh is not None else None)
    return None


def _dedupe_record_ids(raw: Optional[Sequence[str]]) -> Optional[List[str]]:
    if not raw:
        return None
    out: List[str] = []
    seen: set[str] = set()
    for x in raw:
        if x is None:
            continue
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or None


class ListQueryExportService:
    def __init__(self, db: Session):
        self.db = db
        self.meta = ListQueryMetadataService(db)

    def export_rows(self, req: ListExportRequest) -> List[Dict[str, Any]]:
        resource = self.meta.get_resource(req.resource)
        if not resource:
            raise ValueError(f"Unknown resource: {req.resource}")

        field_by_key = self.meta.fields_by_key(req.resource)
        selected = []
        for sel in req.fields:
            m = field_by_key.get(sel.field_key)
            if not m or not m.exportable:
                raise ValueError(f"Unknown or non-exportable field: {sel.field_key}")
            selected.append(m)

        clause = compile_optional_filter(req.resource, req.filter, field_by_key)

        if req.resource == "orders":
            return self._export_orders(selected, clause, req)
        if req.resource == "products":
            return self._export_products(selected, clause, req)
        if req.resource == "suppliers":
            return self._export_suppliers(selected, clause, req)
        raise ValueError(f"Unsupported resource: {req.resource}")

    def _export_orders(
        self,
        selected: list,
        clause: Optional[Any],
        req: ListExportRequest,
    ) -> List[Dict[str, Any]]:
        q = self.db.query(Order).filter(Order.deleted_at.is_(None))
        if req.customer_id and req.customer_id != "all":
            q = q.filter(Order.customer_id == req.customer_id)
        if req.order_status_id and req.order_status_id != "all":
            q = q.filter(Order.order_status_id == req.order_status_id)
        hol = (req.has_order_lines or "").strip().lower()
        if hol == "yes":
            q = q.filter(exists().where(OrderLine.order_id == Order.id))
        elif hol == "no":
            q = q.filter(not_(exists().where(OrderLine.order_id == Order.id)))
        if req.quick_search:
            q = q.filter(
                or_(
                    Order.order_number.ilike(f"%{req.quick_search}%"),
                    Order.customer.has(Customer.customer_name.ilike(f"%{req.quick_search}%")),
                    Order.customer.has(Customer.customer_code.ilike(f"%{req.quick_search}%")),
                )
            )
        if clause is not None:
            q = q.filter(clause)

        id_list = _dedupe_record_ids(req.record_ids)
        if id_list:
            q = q.filter(Order.id.in_(id_list))

        orders = q.options(
            joinedload(Order.lines).joinedload(OrderLine.product),
            joinedload(Order.lines).joinedload(OrderLine.warehouse),
        ).all()
        if id_list:
            by_id = {str(o.id): o for o in orders}
            orders = [by_id[i] for i in id_list if i in by_id]
        else:
            orders = sorted(
                orders,
                key=lambda o: o.created_at or datetime.min,
                reverse=True,
            )

        parent_fields = [m for m in selected if not m.is_line_field]
        line_fields = [m for m in selected if m.is_line_field]

        rows: List[Dict[str, Any]] = []
        for order in orders:
            parent_vals = {}
            for m in parent_fields:
                key = m.export_column_name or m.field_key
                parent_vals[key] = _value_from_obj(order, m.compile_key)

            lines = list(order.lines or [])
            if not lines:
                row = dict(parent_vals)
                for m in line_fields:
                    key = m.export_column_name or m.field_key
                    row[key] = None
                rows.append(row)
                continue
            for line in lines:
                row = dict(parent_vals)
                for m in line_fields:
                    key = m.export_column_name or m.field_key
                    row[key] = _value_from_line_export(line, m.compile_key)
                rows.append(row)
        return rows

    def _export_products(self, selected: list, clause: Optional[Any], req: ListExportRequest) -> List[Dict[str, Any]]:
        from decimal import Decimal

        q = self.db.query(Product)
        if req.category_id and req.category_id != "all":
            q = q.filter(Product.category_id == req.category_id)
        if req.brand_id and req.brand_id != "all":
            q = q.filter(Product.brand_id == req.brand_id)
        if req.product_status and req.product_status != "all":
            q = q.filter(Product.is_active == (req.product_status == "active"))
        if req.item_type:
            q = q.filter(Product.item_type == req.item_type)
        if req.price_min or req.price_max:
            pf = []
            if req.price_min is not None:
                pf.append(Product.list_price >= Decimal(str(req.price_min)))
            if req.price_max is not None:
                pf.append(Product.list_price <= Decimal(str(req.price_max)))
            q = q.filter(and_(*pf))
        if req.quick_search:
            q = q.filter(
                or_(
                    Product.product_code.ilike(f"%{req.quick_search}%"),
                    Product.product_name.ilike(f"%{req.quick_search}%"),
                )
            )
        if clause is not None:
            q = q.filter(clause)

        id_list = _dedupe_record_ids(req.record_ids)
        if id_list:
            q = q.filter(Product.id.in_(id_list))

        products = q.all()
        if id_list:
            by_id = {str(p.id): p for p in products}
            products = [by_id[i] for i in id_list if i in by_id]
        else:
            products = sorted(
                products,
                key=lambda p: p.created_at or datetime.min,
                reverse=True,
            )
        out = []
        for p in products:
            row = {}
            for m in selected:
                key = m.export_column_name or m.field_key
                row[key] = _value_from_obj(p, m.compile_key)
            out.append(row)
        return out

    def _export_suppliers(self, selected: list, clause: Optional[Any], req: ListExportRequest) -> List[Dict[str, Any]]:
        q = self.db.query(Supplier)
        if req.quick_search:
            q = q.filter(
                or_(
                    Supplier.supplier_code.ilike(f"%{req.quick_search}%"),
                    Supplier.supplier_name.ilike(f"%{req.quick_search}%"),
                )
            )
        if clause is not None:
            q = q.filter(clause)

        id_list = _dedupe_record_ids(req.record_ids)
        if id_list:
            q = q.filter(Supplier.id.in_(id_list))

        suppliers = q.all()
        if id_list:
            by_id = {str(s.id): s for s in suppliers}
            suppliers = [by_id[i] for i in id_list if i in by_id]
        else:
            suppliers = sorted(
                suppliers,
                key=lambda s: s.created_at or datetime.min,
                reverse=True,
            )
        out = []
        for s in suppliers:
            row = {}
            for m in selected:
                key = m.export_column_name or m.field_key
                row[key] = _value_from_obj(s, m.compile_key)
            out.append(row)
        return out
