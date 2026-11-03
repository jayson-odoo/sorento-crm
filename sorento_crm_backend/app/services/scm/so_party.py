"""Customer and project of sales orders, for any screen that names an order.

OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 2026): wherever a sales order is named, its customer and
project are named with it. The two values are the SO list's own (`SalesOrderService`'s
`customer_name` and `SalesOrder.project_label`): the debtor name the order was issued under,
else the customer master's name; and the order's resolved project label.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder

_CHUNK = 1000

#: What an order nobody could name answers: nulls, never an id.
EMPTY_PARTY: Dict[str, Optional[str]] = {"customer_name": None, "project_label": None}


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def so_parties(
    db: Session, *, ids: Iterable[Optional[str]] = (), numbers: Iterable[Optional[str]] = ()
) -> Dict[str, Dict[str, Optional[str]]]:
    """`{sales order id or so_number: {"customer_name", "project_label"}}` for the orders
    named by id and/or by number (both keys are filled for every order found)."""
    id_list = sorted({str(i) for i in ids if i})
    number_list = sorted({n for n in numbers if n})
    out: Dict[str, Dict[str, Optional[str]]] = {}

    def _read(column, values: List[str]) -> None:
        for start in range(0, len(values), _CHUNK):
            chunk = values[start:start + _CHUNK]
            rows = (
                db.query(
                    SalesOrder.id,
                    SalesOrder.so_number,
                    func.coalesce(
                        func.nullif(func.trim(SalesOrder.debtor_name), ""),
                        Customer.customer_name,
                    ),
                    SalesOrder.project_label,
                )
                .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
                .filter(column.in_(chunk))
                .all()
            )
            for order_id, so_number, customer_name, project_label in rows:
                party = {
                    "customer_name": _blank_to_none(customer_name),
                    "project_label": _blank_to_none(project_label),
                }
                out[str(order_id)] = party
                if so_number:
                    out.setdefault(so_number, party)

    if id_list:
        _read(SalesOrder.id, id_list)
    missing_numbers = [n for n in number_list if n not in out]
    if missing_numbers:
        _read(SalesOrder.so_number, missing_numbers)
    return out


def with_party(row: Dict[str, Any], parties: Dict[str, Dict[str, Optional[str]]], key: Optional[str]) -> Dict[str, Any]:
    """`row` plus its order's `customer_name` / `project_label` (nulls when unknown)."""
    row.update(parties.get(str(key), EMPTY_PARTY) if key else EMPTY_PARTY)
    return row
