"""Cost lists: the price-in-force rule, hand edits and the daily tick (#1288, Lane A).

`price_in_force` is the ONE definition of "which cost list row is live today" (plan section
4.1) - nothing else re-spells the date rule. `product_suppliers.unit_cost`/`currency` are kept
equal to its answer by this module alone, in the SAME transaction as whatever changed the cost
lists (an apply, a hand edit, or the daily tick) - never computed by a reader.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.error_handler import AppException

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
    list rows is never touched (AC-CL-04) - it keeps whatever a non-cost-list writer set."""
    from app.models.cost_price import ProductSupplierCost

    day = day or date.today()
    rows = (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.product_supplier_id == link.id)
        .all()
    )
    if not rows:
        return False

    winner = price_in_force(rows, day)
    new_cost = winner.unit_cost if winner else None
    new_currency = winner.currency if winner else None
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

    day = day or date.today()
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


def _validate_cost_body(unit_cost, start_date: Optional[date], end_date: Optional[date]) -> None:
    if unit_cost is not None and unit_cost < 0:
        raise AppException(422, "The price cannot be negative.", detail={"code": "negative_price"}, code="negative_price")
    if start_date and end_date and end_date < start_date:
        raise AppException(422, "Valid to cannot be before Valid from.", detail={"code": "end_before_start"}, code="end_before_start")


def create_cost(db: Session, link_id: str, body: dict, current_user: dict):
    from app.models.cost_price import ProductSupplierCost
    from app.services.audit_service import log_audit

    link = _get_link_or_404(db, link_id)
    unit_cost = body.get("unit_cost")
    start_date = date.fromisoformat(body["start_date"]) if body.get("start_date") else None
    end_date = date.fromisoformat(body["end_date"]) if body.get("end_date") else None
    _validate_cost_body(unit_cost, start_date, end_date)

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
    return _serialize_cost_row(row, [row], date.today())


def update_cost(db: Session, link_id: str, cost_id: str, body: dict, current_user: dict):
    from app.services.audit_service import log_audit

    link = _get_link_or_404(db, link_id)
    row = _get_cost_or_404(db, link_id, cost_id)
    unit_cost = body.get("unit_cost", row.unit_cost)
    currency = body.get("currency", row.currency)
    start_date = (
        date.fromisoformat(body["start_date"]) if body.get("start_date") else
        (None if "start_date" in body else row.start_date)
    )
    end_date = (
        date.fromisoformat(body["end_date"]) if body.get("end_date") else
        (None if "end_date" in body else row.end_date)
    )
    _validate_cost_body(unit_cost, start_date, end_date)

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
    return _serialize_cost_row(row, rows, date.today())


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


def _serialize_cost_row(row, siblings: Sequence, today: date) -> dict:
    from app.models.cost_price import CostPriceChangeSet

    source = None
    if row.source_change_line_id:
        # No relationship declared between a cost row and its originating line/set - look
        # it up directly through the row's own session rather than adding one just for
        # this display field.
        from sqlalchemy.orm import object_session

        from app.models.cost_price import CostPriceChangeLine

        cs = None
        db_session = object_session(row)
        if db_session is not None:
            line = (
                db_session.query(CostPriceChangeLine)
                .filter(CostPriceChangeLine.id == row.source_change_line_id)
                .first()
            )
            if line is not None:
                cs = (
                    db_session.query(CostPriceChangeSet)
                    .filter(CostPriceChangeSet.id == line.change_set_id)
                    .first()
                )
        if cs is not None:
            source = {"change_set_id": str(cs.id), "code": cs.code}

    return {
        "id": str(row.id),
        "unit_cost": float(row.unit_cost) if row.unit_cost is not None else None,
        "currency": row.currency,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "status": cost_status(row, siblings, today),
        "source": source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def costs_for_link(db: Session, link_id: str, *, today: Optional[date] = None) -> list[dict]:
    from app.models.cost_price import ProductSupplierCost

    today = today or date.today()
    rows = (
        db.query(ProductSupplierCost)
        .filter(ProductSupplierCost.product_supplier_id == link_id)
        .order_by(ProductSupplierCost.start_date.asc().nullsfirst())
        .all()
    )
    return [_serialize_cost_row(r, rows, today) for r in rows]


def list_cost_lists_for_supplier(
    db: Session, supplier_id: str, *, query: Optional[str] = None, status: Optional[str] = None
) -> dict:
    from sqlalchemy import or_

    from app.models.procurement import ProductSupplier
    from app.models.product import Product
    from app.models.scm import SupplierProductCodeAlias

    today = date.today()
    statuses = {s.strip() for s in (status or "").split(",") if s.strip()}

    q = (
        db.query(ProductSupplier)
        .join(Product, Product.id == ProductSupplier.product_id)
        .filter(ProductSupplier.supplier_id == supplier_id)
    )
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(or_(Product.product_code.ilike(like), Product.product_name.ilike(like)))

    data = []
    for link in q.all():
        product = db.query(Product).filter(Product.id == link.product_id).first()
        costs = costs_for_link(db, link.id, today=today)
        if statuses and not any(c["status"] in statuses for c in costs):
            continue
        alias = (
            db.query(SupplierProductCodeAlias)
            .filter(
                SupplierProductCodeAlias.supplier_id == supplier_id,
                SupplierProductCodeAlias.product_id == link.product_id,
            )
            .order_by(SupplierProductCodeAlias.created_at.desc())
            .first()
        )
        data.append({
            "product_supplier_id": str(link.id),
            "product": {
                "id": str(product.id), "product_code": product.product_code,
                "description": product.product_name,
            } if product else None,
            "supplier_code": alias.supplier_code if alias else None,
            "unit_cost": float(link.unit_cost) if link.unit_cost is not None else None,
            "currency": link.currency,
            "costs": costs,
        })
    return {"data": data, "today": today.isoformat()}
