"""What the Costing page reads: rows, a row's suppliers and a row's history (contract 4.1, 4.2, 4.4).

Rows are costed from one bulk-loaded context (`basis.load_context`), so a page costs a handful
of queries however many rows it holds. The SQL path (filter, sort, page) is used whenever the
answer does not depend on a computed value; a "Has cost" filter or a sort on a computed column
costs the whole filtered set first, then pages it.

Internal rows hold Decimals at full precision. `serialize_row` is the one place they become the
API's floats (6 dp).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import String, and_, cast, func, literal, or_
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.costing import CostingProductOverride, CustomerCostingProduct
from app.models.procurement import Supplier
from app.models.product import Brand, Product, ProductCategory
from app.models.user import User
from app.services.costing import basis, formula, party as party_service
from app.services.costing.rates import units_per_base

SORTS = ("product_code", "category_name", "landing", "final", "markup_pct", "margin_pct")
COMPUTED_SORTS = frozenset({"landing", "final", "markup_pct", "margin_pct"})
_SIX = Decimal("0.000001")


@dataclass
class RowsQuery:
    party_id: Optional[str] = None
    q: Optional[str] = None
    category_ids: list = field(default_factory=list)
    brand_ids: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    has_cost: bool = False
    as_of: Optional[date] = None
    page: int = 1
    limit: Optional[int] = 50  # None = no paging (the export)
    sort: str = "product_code"
    direction: str = "asc"


# ------------------------------------------------------------------ serialization


def _f6(value) -> Optional[float]:
    if value is None:
        return None
    return float(Decimal(value).quantize(_SIX, rounding=ROUND_HALF_UP))


def serialize_reasons(reasons: list) -> list:
    out = []
    for r in reasons:
        item = {"code": r["code"]}
        if r["code"] == "no_rate":
            item["currency"] = r["currency"]
            item["date"] = r["date"].isoformat()
        out.append(item)
    return out


def serialize_row(row: dict) -> dict:
    """The contract's `Row`: Decimals to floats at 6 dp, dates to ISO."""
    out = dict(row)
    for key in ("list_price", "unit_cost", "rate_to_base", "sst_factor", "transport_value", "landing",
                "markup_pct", "final", "margin_pct", "category_transport_value"):
        out[key] = _f6(row[key])
    ups = row["units_per_base"]
    out["units_per_base"] = float(ups) if ups is not None else None
    out["rate_effective_from"] = row["rate_effective_from"].isoformat() if row["rate_effective_from"] else None
    out["po_date"] = row["po_date"].isoformat() if row["po_date"] else None
    out["reasons"] = serialize_reasons(row["reasons"])
    return out


# ------------------------------------------------------------------ rows


def _sql_query(db: Session, rq: RowsQuery, profile, default_method: str):
    cols = [
        Product.id, Product.product_code, Product.product_name, Product.category_id,
        ProductCategory.category_name, Product.brand_id, Brand.brand_name, Product.list_price,
    ]
    query = (
        db.query(*cols)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
    )
    if rq.party_id:
        query = query.join(
            CustomerCostingProduct,
            and_(CustomerCostingProduct.product_id == Product.id,
                 CustomerCostingProduct.customer_id == rq.party_id),
        ).add_columns(CustomerCostingProduct.id, CustomerCostingProduct.markup_pct)
    if rq.q:
        term = rq.q.strip()
        if term:
            query = query.filter(or_(
                Product.product_code.icontains(term, autoescape=True),
                Product.product_name.icontains(term, autoescape=True),
            ))
    if rq.category_ids:
        query = query.filter(Product.category_id.in_(rq.category_ids))
    if rq.brand_ids:
        query = query.filter(Product.brand_id.in_(rq.brand_ids))
    if rq.methods:
        party_method = profile.cost_method if profile is not None else None
        effective = func.coalesce(
            CostingProductOverride.cost_method,
            literal(party_method, type_=String),
            literal(default_method, type_=String),
        )
        query = query.outerjoin(
            CostingProductOverride, CostingProductOverride.product_id == Product.id
        ).filter(effective.in_(rq.methods))
    return query


def _assemble(base, basis_row: dict, profile) -> dict:
    """One internal Row from the product columns and its cost basis."""
    (pid, code, name, cat_id, cat_name, brand_id, brand_name, list_price, *party_cols) = base
    pid = str(pid)
    list_price = Decimal(list_price) if list_price is not None else None
    landing = basis_row["landing"]
    rate = basis_row["rate_to_base"]

    if party_cols:
        party_product_id, row_markup = party_cols
        if row_markup is not None:
            markup, source = Decimal(row_markup), "row"
        else:
            markup, source = (profile.markup_pct if profile else None), "party"
        final = formula.party_final(landing, markup) if landing is not None and markup is not None else None
        margin = (
            formula.margin(list_price, final)
            if final is not None and final != 0 and list_price is not None else None
        )
        party_product_id = str(party_product_id)
    else:
        party_product_id = None
        source = "achieved"
        final = list_price
        margin = None
        markup = (
            formula.achieved_markup(list_price, landing)
            if landing is not None and landing != 0 and list_price is not None else None
        )

    return {
        "product_id": pid, "product_code": code, "product_name": name,
        "category_id": str(cat_id) if cat_id else None, "category_name": cat_name,
        "brand_id": str(brand_id) if brand_id else None, "brand_name": brand_name,
        "list_price": list_price,
        "supplier_id": basis_row["supplier_id"], "supplier_code": basis_row["supplier_code"],
        "currency": basis_row["currency"], "unit_cost": basis_row["unit_cost"],
        "rate_to_base": rate, "units_per_base": units_per_base(rate) if rate is not None else None,
        "rate_effective_from": basis_row["rate_effective_from"],
        "sst_factor": basis_row["sst_factor"],
        "transport_mode": basis_row["transport_mode"], "transport_value": basis_row["transport_value"],
        "transport_source": basis_row["transport_source"],
        "category_transport_mode": basis_row["category_transport_mode"],
        "category_transport_value": basis_row["category_transport_value"],
        "landing": landing,
        "cost_method": basis_row["cost_method"], "cost_method_source": basis_row["cost_method_source"],
        "cost_method_supplier_id": basis_row["cost_method_supplier_id"],
        "markup_pct": markup, "markup_source": source, "final": final, "margin_pct": margin,
        "po_number": basis_row["po_number"], "po_date": basis_row["po_date"],
        "reasons": basis_row["reasons"], "skipped": basis_row["skipped"],
        "party_product_id": party_product_id,
    }


def _cost_rows(db: Session, bases: list, rq: RowsQuery, as_of: date, profile) -> list:
    category_of = {str(b[0]): b[3] for b in bases}
    ctx = basis.load_context(db, category_of, as_of=as_of, party_customer_id=rq.party_id)
    return [_assemble(b, basis.compute(ctx, str(b[0])), profile) for b in bases]


def _sorted(rows: list, key: str, direction: str) -> list:
    known = [r for r in rows if r[key] is not None]
    unknown = [r for r in rows if r[key] is None]
    known.sort(key=lambda r: r[key], reverse=direction == "desc")
    return known + unknown


def list_rows(db: Session, rq: RowsQuery, today: date) -> dict:
    """The page (or, with `limit=None`, the whole filtered set). Returns internal rows."""
    as_of = rq.as_of or today
    party = party_service.get_party(db, rq.party_id) if rq.party_id else None
    base = {
        "as_of": as_of, "view": "party" if rq.party_id else "standard", "party": party,
        "page": rq.page, "limit": rq.limit,
    }
    sst, default_method = basis.load_settings(db)
    base["settings"] = {"sst_factor": float(sst), "default_method": default_method}
    if party is not None and not party["has_profile"]:
        return {**base, "rows": [], "total": 0}

    profile = basis.load_profile(db, rq.party_id)
    query = _sql_query(db, rq, profile, default_method)

    if rq.has_cost or rq.sort in COMPUTED_SORTS:
        bases = query.order_by(Product.product_code, Product.id).all()
        rows = _cost_rows(db, bases, rq, as_of, profile)
        if rq.has_cost:
            rows = [r for r in rows if r["landing"] is not None]
        if rq.sort in COMPUTED_SORTS:
            rows = _sorted(rows, rq.sort, rq.direction)
        total = len(rows)
        if rq.limit is not None:
            start = (rq.page - 1) * rq.limit
            rows = rows[start:start + rq.limit]
        return {**base, "rows": rows, "total": total}

    total = query.order_by(None).count()
    desc = rq.direction == "desc"
    if rq.sort == "category_name":
        order = [ProductCategory.category_name.desc().nulls_last() if desc
                 else ProductCategory.category_name.asc().nulls_last()]
    else:
        order = []
    order += [Product.product_code.desc() if desc else Product.product_code.asc(), Product.id]
    query = query.order_by(*order)
    if rq.limit is not None:
        query = query.offset((rq.page - 1) * rq.limit).limit(rq.limit)
    return {**base, "rows": _cost_rows(db, query.all(), rq, as_of, profile), "total": total}


# ------------------------------------------------------------------ a row's suppliers


def get_product(db: Session, product_id: str) -> Product:
    if not party_service.valid_uuid(product_id):
        raise party_service.not_found("Product")
    product = db.query(Product).filter(Product.id == str(product_id)).first()
    if product is None:
        raise party_service.not_found("Product")
    return product


def supplier_rows(db: Session, product_id: str, party_id: Optional[str], as_of: date) -> list:
    product = get_product(db, product_id)
    if party_id:
        party_service.get_customer(db, party_id)
    ctx = basis.load_context(db, {str(product.id): product.category_id}, as_of=as_of, party_customer_id=party_id)
    mode, value, _source = basis.resolve_transport(ctx, str(product.id))
    list_price = Decimal(product.list_price) if product.list_price is not None else None

    markup = None
    if party_id and ctx.profile is not None:
        row = (
            db.query(CustomerCostingProduct.markup_pct)
            .filter(CustomerCostingProduct.customer_id == party_id,
                    CustomerCostingProduct.product_id == product.id)
            .first()
        )
        markup = Decimal(row[0]) if row is not None and row[0] is not None else ctx.profile.markup_pct

    out = []
    for link in ctx.links.get(str(product.id), []):
        ev = basis.evaluate_link(ctx, link, mode, value)
        landing = ev["landing"]
        if party_id:
            final = formula.party_final(landing, markup) if landing is not None and markup is not None else None
            margin = (
                formula.margin(list_price, final)
                if final is not None and final != 0 and list_price is not None else None
            )
            m = markup
        else:
            final = list_price
            margin = None
            m = (
                formula.achieved_markup(list_price, landing)
                if landing is not None and landing != 0 and list_price is not None else None
            )
        out.append({
            "supplier_id": link.supplier_id, "supplier_code": link.supplier_code,
            "supplier_name": link.supplier_name, "is_primary": link.is_primary,
            "lead_time_days": link.lead_time_days,
            "currency": ev["currency"], "unit_cost": _f6(ev["unit_cost"]), "landing": _f6(landing),
            "final": _f6(final), "markup_pct": _f6(m), "margin_pct": _f6(margin),
            "reasons": serialize_reasons([ev["reason"]] if ev["reason"] else []),
        })
    return out


# ------------------------------------------------------------------ a row's history

_OVERRIDE_FIELDS = ("transport_mode", "transport_value", "cost_method", "cost_method_supplier_id")
_NUMERIC_FIELDS = frozenset({"markup_pct", "transport_value"})


def _norm(field_name: str, value):
    if value is None:
        return None
    if field_name in _NUMERIC_FIELDS:
        return float(value)
    return value


def history(db: Session, product_id: str, party_id: Optional[str]) -> list:
    """Audit entries of the product's override row and, with a party, that party's row for the
    product. One entry per changed column, newest first."""
    product = get_product(db, product_id)
    targets = [("costing_product_overrides", str(product.id), _OVERRIDE_FIELDS)]
    if party_id:
        party_service.get_customer(db, party_id)
        link = (
            db.query(CustomerCostingProduct.id)
            .filter(CustomerCostingProduct.customer_id == party_id,
                    CustomerCostingProduct.product_id == product.id)
            .first()
        )
        if link is not None:
            targets.append(("customer_costing_products", str(link[0]), ("markup_pct",)))

    entries = []
    for entity_type, entity_id, fields in targets:
        logs = (
            db.query(AuditLog, User.name)
            .outerjoin(User, User.id == cast(AuditLog.user_id, String))
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .all()
        )
        for log, user_name in logs:
            old_values, new_values = log.old_values or {}, log.new_values or {}
            for name in fields:
                if name not in old_values and name not in new_values:
                    continue
                old, new = _norm(name, old_values.get(name)), _norm(name, new_values.get(name))
                if old == new:
                    continue
                entries.append((log.changed_at, str(log.id), {
                    "changed_at": log.changed_at.isoformat(), "user_name": user_name or "System",
                    "field": name, "old": old, "new": new,
                }))
    entries.sort(key=lambda e: (e[0], e[1]), reverse=True)
    out = [e[2] for e in entries]

    # A supplier id is shown as its code, never as an id.
    ids = {v for e in out if e["field"] == "cost_method_supplier_id" for v in (e["old"], e["new"]) if v}
    if ids:
        codes = {str(i): c for i, c in db.query(Supplier.id, Supplier.supplier_code).filter(Supplier.id.in_(ids))}
        for e in out:
            if e["field"] == "cost_method_supplier_id":
                e["old"] = codes.get(e["old"], e["old"]) if e["old"] else None
                e["new"] = codes.get(e["new"], e["new"]) if e["new"] else None
    return out
