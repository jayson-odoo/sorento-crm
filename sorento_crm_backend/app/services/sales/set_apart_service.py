"""Set-apart customers (SALES-UNIFIED 2.4, owner ruling Q3 (a)): the customers whose sales the
reports put in their own Set apart block, for the months each row covers. The only writer of
`sales.set_apart_customers`; no two rows of one customer overlap (checked here, the
`team_service` rule). Company scope: the ORM listener scopes reads and stamps writes.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.order import Customer
from app.models.sales import SetApartCustomer
from app.services.error_handler import AppException

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")

SORTS = {
    "debtor_code": Customer.customer_code,
    "customer_name": Customer.customer_name,
    "from_month": SetApartCustomer.from_month,
    "to_month": SetApartCustomer.to_month,
}


def _invalid(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def parse_month(value: Optional[str], field: str) -> Optional[date]:
    """`YYYY-MM` -> the month's first day; None stays None."""
    if value in (None, ""):
        return None
    match = _MONTH.match(str(value).strip())
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise _invalid(f"{field} is a month, YYYY-MM", "invalid_month")
    return date(int(match.group(1)), int(match.group(2)), 1)


def _month(value: Optional[date]) -> Optional[str]:
    return value.strftime("%Y-%m") if value else None


def serialize(row: SetApartCustomer, customer: Optional[Customer]) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "customer_id": str(row.customer_id),
        "debtor_code": customer.customer_code if customer else None,
        "customer_name": customer.customer_name if customer else None,
        "from_month": _month(row.from_month),
        "to_month": _month(row.to_month),
    }


def list_rows(
    db: Session, *, query: Optional[str], sort: str, direction: str, page: int, limit: int
) -> Dict[str, Any]:
    if sort not in SORTS:
        raise _invalid(f"Unknown sort '{sort}'", "invalid_sort")
    q = db.query(SetApartCustomer, Customer).join(Customer, Customer.id == SetApartCustomer.customer_id)
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(Customer.customer_code.ilike(like), Customer.customer_name.ilike(like)))
    total = q.count()
    column = SORTS[sort]
    ordered = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_last()
    rows = q.order_by(ordered, SetApartCustomer.id).offset((page - 1) * limit).limit(limit).all()
    return {
        "data": [serialize(r, c) for r, c in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def _get(db: Session, row_id: str) -> SetApartCustomer:
    row = db.query(SetApartCustomer).filter(SetApartCustomer.id == row_id).first()
    if row is None:
        raise AppException(status_code=404, message="Set-apart customer not found", code="NOT_FOUND")
    return row


def _check(db: Session, customer_id: str, start: date, end: Optional[date], exclude: Optional[str]) -> Customer:
    if end is not None and end < start:
        raise _invalid("To month is before from month", "set_apart_months_inverted")
    try:
        uuid.UUID(str(customer_id))
    except ValueError:
        raise _invalid("Customer not found", "customer_not_found")
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise _invalid("Customer not found", "customer_not_found")
    clash = db.query(SetApartCustomer.id).filter(
        SetApartCustomer.customer_id == customer_id,
        or_(SetApartCustomer.to_month.is_(None), SetApartCustomer.to_month >= start),
        *([] if end is None else [SetApartCustomer.from_month <= end]),
        *([] if exclude is None else [SetApartCustomer.id != exclude]),
    ).first()
    if clash is not None:
        raise _invalid("This customer is already set apart for some of those months", "set_apart_overlap")
    return customer


def create(db: Session, *, customer_id: str, from_month: str, to_month: Optional[str]) -> Dict[str, Any]:
    start = parse_month(from_month, "From month")
    if start is None:
        raise _invalid("From month is required", "invalid_month")
    end = parse_month(to_month, "To month")
    customer = _check(db, customer_id, start, end, None)
    row = SetApartCustomer(customer_id=customer_id, from_month=start, to_month=end)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row, customer)


def update(db: Session, row_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    row = _get(db, row_id)
    customer_id = fields.get("customer_id") or str(row.customer_id)
    start = parse_month(fields["from_month"], "From month") if "from_month" in fields else row.from_month
    if start is None:
        raise _invalid("From month is required", "invalid_month")
    end = parse_month(fields["to_month"], "To month") if "to_month" in fields else row.to_month
    customer = _check(db, customer_id, start, end, str(row.id))
    row.customer_id = customer_id
    row.from_month = start
    row.to_month = end
    db.commit()
    db.refresh(row)
    return serialize(row, customer)


def delete(db: Session, row_id: str) -> None:
    db.delete(_get(db, row_id))
    db.commit()


def delete_by_id(db: Session, row_id: str) -> None:
    """The deferred `sales_set_apart.delete` action's handler: flushes, the action runner
    commits. Already gone is not an error (the `sales_team.delete` rule)."""
    row = db.query(SetApartCustomer).filter(SetApartCustomer.id == row_id).first()
    if row is not None:
        db.delete(row)
        db.flush()


def customer_options(db: Session, *, query: Optional[str], limit: int = 20) -> List[Dict[str, str]]:
    """Customers for the screen's searchable picker: debtor code and name, by code."""
    q = db.query(Customer.id, Customer.customer_code, Customer.customer_name)
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(Customer.customer_code.ilike(like), Customer.customer_name.ilike(like)))
    rows = q.order_by(func.coalesce(Customer.customer_code, ""), Customer.customer_name).limit(limit).all()
    return [
        {"value": str(i), "label": f"{code} {name}".strip() if code else str(name)}
        for i, code, name in rows
    ]
