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
                if not so_number:
                    continue
                seen = out.get(so_number)
                if seen is None:
                    out[so_number] = party
                elif seen != party:
                    # An so_number is unique per company only. An all-company read (an API key
                    # with no contact) that finds one number naming two different parties cannot
                    # tell which order was meant: it names nobody rather than the first row back.
                    out[so_number] = dict(EMPTY_PARTY)

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


def fill_party(
    row: Dict[str, Any], parties: Dict[str, Dict[str, Optional[str]]], key: Optional[str]
) -> Dict[str, Any]:
    """`row` with a BLANK `customer_name` / `project_label` filled from its order.

    For a row that comes from an order inquiry: whatever half it already names wins, and the
    sales order only fills a half the row does not know, so an order not synced yet, a
    provisional ref, a NULL label or an ambiguous number never erases what the row knew. Each
    caller states what its row knows: the PO line placements carry the OI worklist's own split
    (issuing party; project title with its PRE-ORDER note); the SPO planner coverage and the
    SPO document's project entries carry the project title only, so their customer is the
    order's own (the SO list's Customer)."""
    party = parties.get(str(key), EMPTY_PARTY) if key else EMPTY_PARTY
    for field in ("customer_name", "project_label"):
        if not row.get(field):
            row[field] = party[field]
    return row
