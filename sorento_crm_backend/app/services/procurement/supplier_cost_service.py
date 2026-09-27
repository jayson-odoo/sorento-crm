"""Cost lists: the price-in-force rule, hand edits and the daily tick (#1288, Lane A).

`price_in_force` is the ONE definition of "which cost list row is live today" (plan section
4.1) - nothing else re-spells the date rule. `product_suppliers.unit_cost`/`currency` are kept
equal to its answer by this module alone, in the SAME transaction as whatever changed the cost
lists (an apply, a hand edit, or the daily tick) - never computed by a reader.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session, object_session

from app.services.error_handler import AppException
from app.services.pdf_render import today_in_malaysia

STATUS_ALWAYS = "always"
STATUS_IN_FORCE = "in_force"
STATUS_SCHEDULED = "scheduled"
STATUS_ENDED = "ended"
STATUS_OVERRIDDEN = "overridden"


def price_in_force(rows: Sequence, day: date):
    """Among `rows` covering `day` (`start_date` null or <= day, `end_date` null or >= day),
    the one with the latest `start_date` (null counts as earliest); a tie goes to the newest
    `created_at`. `None` when nothing covers the day (AC-CL-01)."""
    covering = [
        r for r in rows
        if (r.start_date is None or r.start_date <= day)
        and (r.end_date is None or r.end_date >= day)
    ]
    if not covering:
        return None

    def _key(r):
        # `date.min` so a null start sorts as "earliest" against a real date.
        return (r.start_date or date.min, r.created_at or datetime.min)

    return max(covering, key=_key)


def cost_status(row, rows: Sequence, day: date) -> str:
    """Which of the five statuses one row shows, given its siblings (contract section 2.1)."""
    if row.start_date is None and row.end_date is None:
        winner = price_in_force(rows, day)
        return STATUS_ALWAYS if winner is row else STATUS_OVERRIDDEN
    if row.start_date is not None and row.start_date > day:
        return STATUS_SCHEDULED
    if row.end_date is not None and row.end_date < day:
        return STATUS_ENDED
    winner = price_in_force(rows, day)
    return STATUS_IN_FORCE if winner is row else STATUS_OVERRIDDEN


def refresh_link(db: Session, link, day: Optional[date] = None) -> bool:
    """Recompute one `ProductSupplier` link's `unit_cost`/`currency` from its own cost list
    rows. Returns True when the link's stored price actually changed. A link with NO cost
    list rows is never touched (AC-CL-04) - it keeps whatever a non-cost-list writer set.
    Nor is a link none of whose rows covers `day`: it keeps its current price until a row
    is in force, never null (like an ERP price list, a future rule never erases the base
    price; Blocking 2 of the review at 232e5706)."""
    from app.models.cost_price import ProductSupplierCost

    day = day or today_in_malaysia()
    rows = (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.product_supplier_id == link.id)
        .all()
    )
    if not rows:
        return False

    winner = price_in_force(rows, day)
    if winner is None:
        return False
    new_cost = winner.unit_cost
    new_currency = winner.currency
    changed = (link.unit_cost != new_cost) or (link.currency != new_currency)
    if changed:
        link.unit_cost = new_cost
        link.currency = new_currency
    return changed


def refresh_prices_in_force(db: Session, day: Optional[date] = None) -> int:
    """The daily tick (AC-CL-05): every link with cost list rows whose price in force
    differs from its stored `unit_cost` is updated through the ORM (so the audit listener
    records old/new), and one `SUPPLIER_COST_TICK` row lists them. Idempotent: a second run
    the same day changes nothing and writes no second audit row."""
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier
    from app.services.audit_service import log_audit

    day = day or today_in_malaysia()
    link_ids = {
        row[0]
        for row in db.query(ProductSupplierCost.product_supplier_id).distinct().all()
    }
    if not link_ids:
        return 0

    changed_summary: list[dict] = []
    for link in db.query(ProductSupplier).filter(ProductSupplier.id.in_(link_ids)).all():
        before_cost, before_currency = link.unit_cost, link.currency
        if refresh_link(db, link, day):
            changed_summary.append({
                "product_supplier_id": str(link.id),
                "before_unit_cost": float(before_cost) if before_cost is not None else None,
                "before_currency": before_currency,
                "after_unit_cost": float(link.unit_cost) if link.unit_cost is not None else None,
                "after_currency": link.currency,
            })

    if changed_summary:
        log_audit(
            db, "product_suppliers", "tick", "SUPPLIER_COST_TICK",
            new_values={"day": day.isoformat(), "changes": changed_summary},
        )
        db.commit()
    return len(changed_summary)


# --------------------------------------------------------------------------- hand edits


def _get_link_or_404(db: Session, link_id: str):
    from app.models.procurement import ProductSupplier

    link = db.query(ProductSupplier).filter(ProductSupplier.id == link_id).first()
    if link is None:
        raise AppException(404, "Supplier link not found.", code="NOT_FOUND")
    return link


def _get_cost_or_404(db: Session, link_id: str, cost_id: str):
    from app.models.cost_price import ProductSupplierCost

    row = (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.id == cost_id, ProductSupplierCost.product_supplier_id == link_id)
        .first()
    )
    if row is None:
        raise AppException(404, "Cost row not found.", code="NOT_FOUND")
    return row


def _parse_date_or_422(value, *, field: str) -> Optional[date]:
    if not value:
        return None
    if not isinstance(value, str):
        return value  # already a `date`, parsed by the route's body model
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise AppException(
            422, f"Enter a valid {field}.", detail={"code": "invalid_date"}, code="invalid_date",
        )


def _validate_cost_body(
    unit_cost, currency: Optional[str], start_date: Optional[date], end_date: Optional[date]
) -> None:
    if unit_cost is not None and unit_cost < 0:
        raise AppException(422, "The price cannot be negative.", detail={"code": "negative_price"}, code="negative_price")
    if currency and len(currency) > 3:
        raise AppException(
            422, "Currency must be a 3-letter code.",
            detail={"code": "invalid_currency"}, code="invalid_currency",
        )
    if start_date and end_date and end_date < start_date:
        raise AppException(422, "Valid to cannot be before Valid from.", detail={"code": "end_before_start"}, code="end_before_start")


def create_cost(db: Session, link_id: str, body: dict, current_user: dict):
    from app.models.cost_price import ProductSupplierCost
    from app.services.audit_service import log_audit

    link = _get_link_or_404(db, link_id)
    unit_cost = body.get("unit_cost")
    start_date = _parse_date_or_422(body.get("start_date"), field="start date")
    end_date = _parse_date_or_422(body.get("end_date"), field="end date")
    _validate_cost_body(unit_cost, body.get("currency"), start_date, end_date)

    row = ProductSupplierCost(
        product_supplier_id=link.id, unit_cost=unit_cost, currency=body.get("currency"),
        start_date=start_date, end_date=end_date, created_by_user_id=current_user.get("id"),
    )
    db.add(row)
    db.flush()
    refresh_link(db, link)
    log_audit(
        db, "product_supplier_costs", str(row.id), "SUPPLIER_COST_LIST_EDIT",
        new_values={"unit_cost": float(unit_cost) if unit_cost is not None else None, "currency": row.currency},
        user_id=current_user.get("id"),
    )
    db.commit()
    return _serialize_cost_row(row, [row], today_in_malaysia())


def update_cost(db: Session, link_id: str, cost_id: str, body: dict, current_user: dict):
    from app.services.audit_service import log_audit

    link = _get_link_or_404(db, link_id)
    row = _get_cost_or_404(db, link_id, cost_id)
    unit_cost = body.get("unit_cost", row.unit_cost)
    currency = body.get("currency", row.currency)
    start_date = (
        _parse_date_or_422(body["start_date"], field="start date") if body.get("start_date") else
        (None if "start_date" in body else row.start_date)
    )
    end_date = (
        _parse_date_or_422(body["end_date"], field="end date") if body.get("end_date") else
        (None if "end_date" in body else row.end_date)
    )
    _validate_cost_body(unit_cost, currency, start_date, end_date)

    row.unit_cost = unit_cost
    row.currency = currency
    row.start_date = start_date
    row.end_date = end_date
    db.flush()
    refresh_link(db, link)
    log_audit(
        db, "product_supplier_costs", str(row.id), "SUPPLIER_COST_LIST_EDIT",
        new_values={"unit_cost": float(unit_cost) if unit_cost is not None else None, "currency": currency},
        user_id=current_user.get("id"),
    )
    db.commit()
    rows = db.query(type(row)).filter(type(row).product_supplier_id == link_id).all()
    return _serialize_cost_row(row, rows, today_in_malaysia())


def delete_cost(db: Session, link_id: str, cost_id: str, current_user: dict) -> None:
    from app.services.audit_service import log_audit

    link = _get_link_or_404(db, link_id)
    row = _get_cost_or_404(db, link_id, cost_id)
    db.delete(row)
    db.flush()
    refresh_link(db, link)
    log_audit(
        db, "product_supplier_costs", cost_id, "SUPPLIER_COST_LIST_EDIT",
        new_values={"deleted": True}, user_id=current_user.get("id"),
    )
    db.commit()


def _serialize_cost_row(row, siblings: Sequence, today: date, sources: Optional[dict] = None) -> dict:
    """`sources` maps `source_change_line_id` to `{change_set_id, code}` when the caller
    batched that lookup; without it the row looks its own source up."""
    if sources is None:
        sources = _sources_for(object_session(row), [row])
    return {
        "id": str(row.id),
        "unit_cost": float(row.unit_cost) if row.unit_cost is not None else None,
        "currency": row.currency,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "status": cost_status(row, siblings, today),
        "source": sources.get(str(row.source_change_line_id)) if row.source_change_line_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _sources_for(db: Optional[Session], rows: Iterable) -> dict:
    """`{source_change_line_id: {change_set_id, code}}` for `rows`, in one query. There is
    no relationship declared between a cost row and its originating line/set, so join
    through the line table directly rather than adding one just for this display field."""
    from app.models.cost_price import CostPriceChangeLine, CostPriceChangeSet

    line_ids = {str(r.source_change_line_id) for r in rows if r.source_change_line_id}
    if db is None or not line_ids:
        return {}
    return {
        str(line_id): {"change_set_id": str(set_id), "code": code}
        for line_id, set_id, code in (
            db.query(CostPriceChangeLine.id, CostPriceChangeSet.id, CostPriceChangeSet.code)
            .join(CostPriceChangeSet, CostPriceChangeSet.id == CostPriceChangeLine.change_set_id)
            .filter(CostPriceChangeLine.id.in_(line_ids))
            .all()
        )
    }


def costs_for_link(db: Session, link_id: str, *, today: Optional[date] = None) -> list[dict]:
    from app.models.cost_price import ProductSupplierCost

    today = today or today_in_malaysia()
    rows = (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.product_supplier_id == link_id)
        .order_by(ProductSupplierCost.start_date.asc().nullsfirst())
        .all()
    )
    sources = _sources_for(db, rows)
    return [_serialize_cost_row(r, rows, today, sources) for r in rows]


def list_cost_lists_for_supplier(
    db: Session, supplier_id: str, *, query: Optional[str] = None, status: Optional[str] = None
) -> dict:
    """The supplier's Prices tab. A fixed handful of queries whatever the link count (Nit 3
    of the review at 232e5706: it used to run three per link). `query` matches the product
    code, the description or this supplier's own code for the product (AC-CL-07)."""
    from sqlalchemy import or_

    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier
    from app.models.product import Product
    from app.models.scm import SupplierProductCodeAlias

    today = today_in_malaysia()
    statuses = {s.strip() for s in (status or "").split(",") if s.strip()}

    q = (
        db.query(ProductSupplier, Product)
        .join(Product, Product.id == ProductSupplier.product_id)
        .filter(ProductSupplier.supplier_id == supplier_id)
    )
    if query:
        like = f"%{query.strip()}%"
        aliased_products = (
            db.query(SupplierProductCodeAlias.product_id)
            .filter(
                SupplierProductCodeAlias.supplier_id == supplier_id,
                SupplierProductCodeAlias.supplier_code.ilike(like),
            )
        )
        q = q.filter(or_(
            Product.product_code.ilike(like),
            Product.product_name.ilike(like),
            Product.id.in_(aliased_products),
        ))
    pairs = q.all()
    if not pairs:
        return {"data": [], "today": today.isoformat()}

    link_ids = [link.id for link, _ in pairs]
    rows_by_link: dict[str, list] = {}
    for row in (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.product_supplier_id.in_(link_ids))
        .order_by(ProductSupplierCost.start_date.asc().nullsfirst())
        .all()
    ):
        rows_by_link.setdefault(str(row.product_supplier_id), []).append(row)
    sources = _sources_for(db, [r for rows in rows_by_link.values() for r in rows])

    alias_by_product: dict[str, str] = {}
    for product_id, code in (
        db.query(SupplierProductCodeAlias.product_id, SupplierProductCodeAlias.supplier_code)
        .filter(
            SupplierProductCodeAlias.supplier_id == supplier_id,
            SupplierProductCodeAlias.product_id.in_([p.id for _, p in pairs]),
        )
        .order_by(SupplierProductCodeAlias.created_at.desc())
        .all()
    ):
        alias_by_product.setdefault(str(product_id), code)  # newest first wins

    data = []
    for link, product in pairs:
        rows = rows_by_link.get(str(link.id), [])
        costs = [_serialize_cost_row(r, rows, today, sources) for r in rows]
        if statuses and not any(c["status"] in statuses for c in costs):
            continue
        data.append({
            "product_supplier_id": str(link.id),
            "product": {
                "id": str(product.id), "product_code": product.product_code,
                "description": product.product_name,
            },
            "supplier_code": alias_by_product.get(str(product.id)),
            "unit_cost": float(link.unit_cost) if link.unit_cost is not None else None,
            "currency": link.currency,
            "costs": costs,
        })
    return {"data": data, "today": today.isoformat()}
