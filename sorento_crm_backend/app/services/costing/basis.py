"""The cost behind a product on a date (contract section 3, AC-LC-01..06, AC-ST-02/03).

`load_context` reads everything a set of products needs in a few queries (links, cost rows,
rates, transport rules, overrides, last PO lines), so a page of rows costs the same handful of
queries whatever its size. `compute` is then pure over that context. `cost_basis` is the
one-product convenience.

No fallback between methods: a method that yields nothing returns its reason and a blank
landing, never another method's number (AC-LC-05). Unknown numbers are None, never 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cost_price import ProductSupplierCost
from app.models.costing import (
    CostingCategoryRule,
    CostingProductOverride,
    CostingSettings,
    CustomerCostingProfile,
)
from app.models.procurement import (
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.services.costing import formula
from app.services.costing.rates import RateBook, load_rate_book
from app.services.procurement.supplier_cost_service import current_cost
from app.services.scm.money import BASE_CURRENCY, normalize_currency

DEFAULT_SST = Decimal("1.1")
DEFAULT_METHOD = "primary"
METHODS = ("primary", "selected", "average", "last_po")
METHOD_LABELS = {
    "primary": "Primary supplier",
    "selected": "Selected supplier",
    "average": "Average of supplier prices",
    "last_po": "Last PO price",
}
_CHUNK = 5000


@dataclass
class Link:
    id: str
    supplier_id: str
    supplier_code: str
    supplier_name: str
    is_primary: bool
    lead_time_days: Optional[int]
    unit_cost: Optional[Decimal]
    currency: Optional[str]
    rows: list = field(default_factory=list)


@dataclass
class PoLine:
    unit_cost: Decimal
    currency: str
    po_number: str
    po_date: date
    supplier_id: Optional[str]
    supplier_code: Optional[str]
    supplier_name: Optional[str] = None


@dataclass
class Profile:
    markup_pct: Decimal
    cost_method: Optional[str]
    is_active: bool


@dataclass
class CostContext:
    as_of: date
    sst: Decimal
    default_method: str
    profile: Optional[Profile]
    rates: RateBook
    rules: dict
    overrides: dict
    links: dict
    category_of: dict
    pos: dict


def _chunks(ids: list, size: int = _CHUNK):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def load_settings(db: Session) -> tuple[Decimal, str]:
    """The company's SST factor and default method; the defaults when nothing was saved."""
    row = db.query(CostingSettings).first()
    if row is None:
        return DEFAULT_SST, DEFAULT_METHOD
    return Decimal(row.sst_factor), row.default_method


def load_profile(db: Session, customer_id: Optional[str]) -> Optional[Profile]:
    if not customer_id:
        return None
    row = db.query(CustomerCostingProfile).filter(CustomerCostingProfile.customer_id == customer_id).first()
    if row is None:
        return None
    return Profile(Decimal(row.markup_pct), row.cost_method, bool(row.is_active))


def effective_method(override, profile: Optional[Profile], default_method: str) -> tuple[str, str]:
    """Product override > party profile > company default (AC-LC-04)."""
    if override is not None and override.cost_method:
        return override.cost_method, "product"
    if profile is not None and profile.cost_method:
        return profile.cost_method, "party"
    return default_method, "company"


def load_context(
    db: Session,
    category_of: dict,
    *,
    as_of: date,
    party_customer_id: Optional[str] = None,
) -> CostContext:
    """`category_of` maps every product id to be costed to its category id."""
    product_ids = list(category_of)
    sst, default_method = load_settings(db)
    profile = load_profile(db, party_customer_id)

    rules = {r.category_id: r for r in db.query(CostingCategoryRule).all()}
    overrides: dict = {}
    links: dict = {}
    for chunk in _chunks(product_ids):
        for o in db.query(CostingProductOverride).filter(CostingProductOverride.product_id.in_(chunk)):
            overrides[o.product_id] = o
        rows = (
            db.query(ProductSupplier, Supplier)
            .join(Supplier, Supplier.id == ProductSupplier.supplier_id)
            .filter(ProductSupplier.product_id.in_(chunk))
            .all()
        )
        by_link: dict = {}
        for ps, sup in rows:
            link = Link(
                id=str(ps.id), supplier_id=str(ps.supplier_id), supplier_code=sup.supplier_code,
                supplier_name=sup.supplier_name, is_primary=bool(ps.is_primary_supplier),
                lead_time_days=ps.standard_lead_time_days,
                unit_cost=Decimal(ps.unit_cost) if ps.unit_cost is not None else None,
                currency=ps.currency,
            )
            by_link[link.id] = link
            links.setdefault(ps.product_id, []).append(link)
        if by_link:
            for cost in db.query(ProductSupplierCost).filter(
                ProductSupplierCost.product_supplier_id.in_(list(by_link))
            ):
                by_link[str(cost.product_supplier_id)].rows.append(cost)
    for plist in links.values():
        plist.sort(key=lambda l: (not l.is_primary, l.supplier_code or ""))

    ctx = CostContext(
        as_of=as_of, sst=sst, default_method=default_method, profile=profile,
        rates=load_rate_book(db), rules=rules, overrides=overrides, links=links,
        category_of=category_of, pos={},
    )
    needs_po = [
        pid for pid in product_ids
        if effective_method(overrides.get(pid), profile, default_method)[0] == "last_po"
    ]
    ctx.pos = _load_last_pos(db, needs_po, as_of)
    return ctx


def _load_last_pos(db: Session, product_ids: list, as_of: date) -> dict:
    out: dict = {}
    for chunk in _chunks(product_ids):
        rows = (
            db.query(
                PurchaseOrderLine.product_id, PurchaseOrderLine.unit_cost, PurchaseOrderLine.currency,
                PurchaseOrder.currency, PurchaseOrder.po_number, PurchaseOrder.issue_date,
                PurchaseOrder.supplier_id, Supplier.supplier_code, Supplier.supplier_name,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(
                PurchaseOrderLine.product_id.in_(chunk),
                PurchaseOrderLine.unit_cost.isnot(None),
                PurchaseOrderLine.removed_unreferenced.is_(False),
                PurchaseOrder.issue_date.isnot(None),
                PurchaseOrder.issue_date <= as_of,
            )
            .distinct(PurchaseOrderLine.product_id)
            .order_by(
                PurchaseOrderLine.product_id,
                PurchaseOrder.issue_date.desc(),
                PurchaseOrderLine.created_at.desc(),
                PurchaseOrderLine.id.desc(),
            )
            .all()
        )
        for pid, cost, line_cur, po_cur, po_number, issue, sup_id, sup_code, sup_name in rows:
            out[pid] = PoLine(
                unit_cost=Decimal(cost), currency=normalize_currency(line_cur or po_cur),
                po_number=po_number, po_date=issue,
                supplier_id=str(sup_id) if sup_id else None, supplier_code=sup_code, supplier_name=sup_name,
            )
    return out


# ------------------------------------------------------------------ pieces


def rate_for(ctx: CostContext, currency: Optional[str], day: date):
    """`(rate_to_base, effective_from)` in force for `currency` on `day`; MYR is (1, None);
    None when there is no row on or before the day."""
    code = normalize_currency(currency)
    if code == BASE_CURRENCY:
        return Decimal(1), None
    row = ctx.rates.on(code, day)
    if row is None:
        return None
    return Decimal(row.rate_to_base), row.effective_from


def link_cost(link: Link, day: date) -> tuple[Optional[Decimal], Optional[str]]:
    """The cost list's price in force on `day` (the `current_cost` reader), or, for a link with
    no cost rows at all, the link's own price."""
    if link.rows:
        row = current_cost(link.rows, day)
        if row is None:
            return None, None
        return Decimal(row.unit_cost), normalize_currency(row.currency)
    if link.unit_cost is not None:
        return link.unit_cost, normalize_currency(link.currency)
    return None, None


def resolve_transport(ctx: CostContext, product_id: str):
    """`(mode, value, source)`: product override > the product's own category rule > none."""
    ov = ctx.overrides.get(product_id)
    if ov is not None and ov.transport_mode:
        return ov.transport_mode, Decimal(ov.transport_value), "product"
    rule = ctx.rules.get(ctx.category_of.get(product_id))
    if rule is not None:
        return rule.mode, Decimal(rule.value), "category"
    return None, None, None


def evaluate(ctx: CostContext, unit_cost, currency, day, mode, value):
    """Rate and landing for one price. Returns `(rate, rate_from, landing, reason)`; `reason` is
    the `no_rate` dict when the currency has no rate on `day`."""
    if unit_cost is None:
        return None, None, None, None
    found = rate_for(ctx, currency, day)
    if found is None:
        return None, None, None, {"code": "no_rate", "currency": currency, "date": day}
    rate, rate_from = found
    return rate, rate_from, formula.landing(unit_cost, rate, ctx.sst, mode, value), None


def evaluate_link(ctx: CostContext, link: Link, mode, value) -> dict:
    unit_cost, currency = link_cost(link, ctx.as_of)
    rate, rate_from, landing, reason = evaluate(ctx, unit_cost, currency, ctx.as_of, mode, value)
    if unit_cost is None:
        reason = {"code": "no_cost"}
    return {
        "unit_cost": unit_cost, "currency": currency, "rate": rate, "rate_from": rate_from,
        "landing": landing, "reason": reason,
    }


# ------------------------------------------------------------------ the basis


def compute(ctx: CostContext, product_id: str) -> dict:
    ov = ctx.overrides.get(product_id)
    method, method_source = effective_method(ov, ctx.profile, ctx.default_method)
    mode, value, tsource = resolve_transport(ctx, product_id)
    rule = ctx.rules.get(ctx.category_of.get(product_id))
    links = ctx.links.get(product_id, [])

    out = {
        "product_id": product_id,
        "landing": None, "cost_method": method, "cost_method_source": method_source,
        "cost_method_supplier_id": ov.cost_method_supplier_id if ov is not None and method == "selected" else None,
        "supplier_id": None, "supplier_code": None, "supplier_name": None,
        "unit_cost": None, "currency": None, "rate_to_base": None, "rate_effective_from": None,
        "sst_factor": ctx.sst,
        "transport_mode": mode, "transport_value": value, "transport_source": tsource,
        "category_transport_mode": rule.mode if rule is not None else None,
        "category_transport_value": Decimal(rule.value) if rule is not None else None,
        "reasons": [], "skipped": [], "po_number": None, "po_date": None,
    }

    def take(link: Link) -> None:
        ev = evaluate_link(ctx, link, mode, value)
        out.update(
            supplier_id=link.supplier_id, supplier_code=link.supplier_code, supplier_name=link.supplier_name,
            unit_cost=ev["unit_cost"], currency=ev["currency"] if ev["unit_cost"] is not None else None,
            rate_to_base=ev["rate"], rate_effective_from=ev["rate_from"], landing=ev["landing"],
        )
        if ev["reason"] is not None:
            out["reasons"].append(ev["reason"])

    if method == "primary":
        primary = next((l for l in links if l.is_primary), None)
        if primary is None:
            out["reasons"].append({"code": "no_primary"})
        else:
            take(primary)
    elif method == "selected":
        chosen = next((l for l in links if ov is not None and l.supplier_id == str(ov.cost_method_supplier_id)), None)
        if chosen is None:
            out["reasons"].append({"code": "selected_not_linked"})
        else:
            take(chosen)
    elif method == "average":
        landings = []
        for link in links:
            ev = evaluate_link(ctx, link, mode, value)
            if ev["landing"] is not None:
                landings.append(ev["landing"])
            else:
                out["skipped"].append({"supplier_code": link.supplier_code, "reason": ev["reason"]["code"]})
        if landings:
            out["landing"] = sum(landings, Decimal(0)) / len(landings)
        else:
            out["reasons"].append({"code": "no_cost"})
    else:  # last_po
        po = ctx.pos.get(product_id)
        if po is None:
            out["reasons"].append({"code": "no_po_price"})
        else:
            rate, rate_from, landing, reason = evaluate(ctx, po.unit_cost, po.currency, po.po_date, mode, value)
            out.update(
                supplier_id=po.supplier_id, supplier_code=po.supplier_code, supplier_name=po.supplier_name,
                unit_cost=po.unit_cost, currency=po.currency, rate_to_base=rate,
                rate_effective_from=rate_from, landing=landing,
                po_number=po.po_number, po_date=po.po_date,
            )
            if reason is not None:
                out["reasons"].append(reason)

    if tsource is None:
        out["reasons"].append({"code": "no_transport_rule"})
    return out


def cost_basis(
    db: Session, product_id: str, *, as_of: date, party_customer_id: Optional[str] = None
) -> dict:
    """The contract's Row cost fields for one product (see `compute`)."""
    product = db.query(Product).filter(Product.id == product_id).first()
    category_id = product.category_id if product is not None else None
    ctx = load_context(db, {str(product_id): category_id}, as_of=as_of, party_customer_id=party_customer_id)
    return compute(ctx, str(product_id))


REASON_TEXT = {
    "no_cost": "No cost",
    "no_primary": "Set a primary supplier",
    "selected_not_linked": "Selected supplier no longer linked",
    "no_po_price": "No PO price",
    "no_transport_rule": "No transport rule",
    "no_list_price": "No list price",
}


def reason_text(reason: dict) -> str:
    """The UI/Excel wording of a reason code."""
    if reason["code"] == "no_rate":
        d = reason["date"]
        return f"No rate for {reason['currency']} on {d:%d/%m/%Y}"
    return REASON_TEXT[reason["code"]]
