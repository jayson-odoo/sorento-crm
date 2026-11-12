"""The Costing page's one Save: `PATCH /rows` (contract 4.3, AC-CG-08).

All or nothing. Every change is checked against the database first; only when the whole batch is
valid is anything written, and one commit ends it. A "cell" is what the page shows as one
editable value: Mark-up, Transport (mode and value together), Cost method (method and its
supplier together). `updated` counts the cells whose value actually changed; a cell sent with the
value it already has writes nothing, not even an audit row.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.costing import CostingProductOverride, CustomerCostingProduct
from app.models.procurement import ProductSupplier
from app.models.product import Product
from app.services.costing import basis, party as party_service
from app.services.costing.formula import to_decimal
from app.services.error_handler import AppException

_OVERRIDE_KEYS = ("transport_mode", "transport_value", "cost_method", "cost_method_supplier_id")


@dataclass
class Change:
    """One validated change. `given` is the set of keys the caller sent."""

    product_id: str
    given: frozenset
    markup_pct: Optional[Decimal] = None
    transport_mode: Optional[str] = None
    transport_value: Optional[Decimal] = None
    cost_method: Optional[str] = None
    cost_method_supplier_id: Optional[str] = None


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="VALIDATION_ERROR")


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return to_decimal(a) == to_decimal(b)


def apply_changes(db: Session, party_id: Optional[str], changes: list[Change], *, actor: Optional[str]) -> int:
    if party_id:
        party_service.get_customer(db, party_id)
    if not changes:
        return 0

    product_ids = list(dict.fromkeys(c.product_id for c in changes))
    if not all(party_service.valid_uuid(p) for p in product_ids):
        raise party_service.not_found("Product")
    found = {str(pid) for (pid,) in db.query(Product.id).filter(Product.id.in_(product_ids)).all()}
    if len(found) != len(product_ids):
        raise party_service.not_found("Product")

    wants_markup = any("markup_pct" in c.given for c in changes)
    party_rows: dict = {}
    if wants_markup:
        if not party_id:
            raise _invalid("A mark-up belongs to a party. Pick a party first.")
        if party_service.get_profile(db, party_id) is None:
            raise _invalid("This party has no costing profile yet.")
        party_rows = {
            str(r.product_id): r
            for r in db.query(CustomerCostingProduct).filter(
                CustomerCostingProduct.customer_id == party_id,
                CustomerCostingProduct.product_id.in_(product_ids),
            )
        }
        for c in changes:
            if "markup_pct" in c.given and c.product_id not in party_rows:
                raise _invalid("A mark-up can only be set on a product that is on the party's list.")

    selected = [c for c in changes if c.cost_method == "selected" and "cost_method" in c.given]
    linked: dict = {}
    if selected:
        for pid, sid in db.query(ProductSupplier.product_id, ProductSupplier.supplier_id).filter(
            ProductSupplier.product_id.in_([c.product_id for c in selected])
        ):
            linked.setdefault(str(pid), set()).add(str(sid))
        for c in selected:
            if c.cost_method_supplier_id not in linked.get(c.product_id, set()):
                raise _invalid("The selected supplier must be one of the product's suppliers.")

    # Valid: write. State per product starts from the stored override and is reconciled once.
    overrides = {
        str(o.product_id): o
        for o in db.query(CostingProductOverride).filter(CostingProductOverride.product_id.in_(product_ids))
    }
    state = {
        pid: {k: (getattr(overrides[pid], k) if pid in overrides else None) for k in _OVERRIDE_KEYS}
        for pid in product_ids
    }
    touched: set = set()
    cells = 0

    for c in changes:
        if "markup_pct" in c.given:
            row = party_rows[c.product_id]
            if not _same(row.markup_pct, c.markup_pct):
                row.markup_pct = c.markup_pct
                cells += 1
        st = state[c.product_id]
        if "transport_mode" in c.given or "transport_value" in c.given:
            if st["transport_mode"] != c.transport_mode or not _same(st["transport_value"], c.transport_value):
                st["transport_mode"], st["transport_value"] = c.transport_mode, c.transport_value
                touched.add(c.product_id)
                cells += 1
        if "cost_method" in c.given:
            supplier = c.cost_method_supplier_id if c.cost_method == "selected" else None
            if st["cost_method"] != c.cost_method or st["cost_method_supplier_id"] != supplier:
                st["cost_method"], st["cost_method_supplier_id"] = c.cost_method, supplier
                touched.add(c.product_id)
                cells += 1

    for pid in touched:
        st = state[pid]
        row = overrides.get(pid)
        empty = st["transport_mode"] is None and st["cost_method"] is None
        if row is None:
            if not empty:
                db.add(CostingProductOverride(product_id=pid, updated_by=actor, **st))
        elif empty:
            db.delete(row)
        else:
            for key in _OVERRIDE_KEYS:
                if getattr(row, key) != st[key]:
                    setattr(row, key, st[key])
            row.updated_by = actor
    db.commit()
    return cells
