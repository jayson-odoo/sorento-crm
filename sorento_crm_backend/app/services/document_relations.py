"""DOC-RELATIONS: which sales orders, delivery orders and billing documents belong together.

Plan: documentation/plans/order-management/PLAN-doc-relations-27oct.md.

Derived at read time from columns the AutoCount feeds already write, never stored: a stored link
is exactly what went stale on SO427775 (its invoice came from a DO whose lines never resolved a
`sales_order_line_id`, so the invoice line never got one either). Every query is filtered on the
anchor record's own company, so a same-numbered document in another company never links.

  SO -> DO       a DO line naming the SO by `from_doc_no` (type SO or NULL), a DO line whose
                 `sales_order_line_id` is on the SO, or the DO header's `sales_order_id`;
                 deleted and cancelled DOs left out. The line half is the Delivery tab's own
                 predicate (`so_line_history`), so the two cannot disagree.
  SO -> billing  a billing line resolved onto the SO's lines, transferred from the SO by number,
                 or transferred from one of the SO's DOs by number; plus the notes against those.
  DO -> billing  a billing line transferred from the DO by number; plus the notes against those.
  billing -> *   the reverse of the above; a note inherits its invoice's orders.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models.finance import BillingDocument, BillingDocumentLine
from app.models.order import Order, OrderLine, OrderStatus, SalesOrder, SalesOrderLine

SALES_ORDER = "sales_order"
DELIVERY_ORDER = "delivery_order"
BILLING_DOCUMENT = "billing_document"

#: The key each kind's list sits under in a relations dict.
KIND_KEYS = {
    SALES_ORDER: "sales_orders",
    DELIVERY_ORDER: "delivery_orders",
    BILLING_DOCUMENT: "billing_documents",
}

#: The `/related` table's sortable columns (owner rule 27 Oct: every grid column sorts server side).
SORT_KEYS = ("type", "doc_no", "doc_date", "status", "amount")
RELATED_SORT_PATTERN = "^(" + "|".join(SORT_KEYS) + ")$"


def _iso(value: Any) -> Optional[str]:
    return None if value is None else value.isoformat()


def _num(value: Optional[Decimal]) -> Optional[float]:
    return None if value is None else float(value)


# ------------------------------------------------------------------------- predicates
def _so_from_doc(column_type, column_no, so_number: str):
    """A line transferred from the sales order numbered `so_number` (type SO, or untyped)."""
    return and_(column_no == so_number, or_(column_type.is_(None), column_type == "SO"))


def _so_line_ids(so: SalesOrder):
    return select(SalesOrderLine.id).where(SalesOrderLine.sales_order_id == so.id)


def _do_ids_for_so(so: SalesOrder):
    """SELECT of the ids of the live DOs delivering `so`."""
    line_link = exists().where(
        OrderLine.order_id == Order.id,
        or_(
            _so_from_doc(OrderLine.from_doc_type, OrderLine.from_doc_no, so.so_number),
            and_(
                OrderLine.sales_order_line_id.in_(_so_line_ids(so)),
                or_(OrderLine.from_doc_no.is_(None), OrderLine.from_doc_no == so.so_number),
            ),
        ),
    )
    return select(Order.id).where(
        Order.company_id == so.company_id,
        Order.deleted_at.is_(None),
        Order.is_cancelled.is_(False),
        or_(Order.sales_order_id == so.id, line_link),
    )


def _with_notes(direct, company_id: str):
    """`direct` (a SELECT of billing document ids) plus every note against one of them."""
    return select(BillingDocument.id).where(
        BillingDocument.company_id == company_id,
        or_(BillingDocument.id.in_(direct), BillingDocument.against_document_id.in_(direct)),
    )


def billing_ids_for_sales_order(so: SalesOrder):
    """SELECT of the ids of the billing documents of `so` (the Invoices tab's set)."""
    do_numbers = select(Order.order_number).where(Order.id.in_(_do_ids_for_so(so)))
    direct = (
        select(BillingDocumentLine.document_id)
        .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
        .where(
            BillingDocument.company_id == so.company_id,
            or_(
                BillingDocumentLine.sales_order_line_id.in_(_so_line_ids(so)),
                and_(
                    BillingDocumentLine.from_doc_type == "SO",
                    BillingDocumentLine.from_doc_no == so.so_number,
                ),
                and_(
                    BillingDocumentLine.from_doc_type == "DO",
                    BillingDocumentLine.from_doc_no.in_(do_numbers),
                ),
            ),
        )
    )
    return _with_notes(direct, so.company_id)


def billing_ids_for_delivery_order(order: Order):
    """SELECT of the ids of the billing documents of the DO `order` (its Invoices tab's set)."""
    direct = (
        select(BillingDocumentLine.document_id)
        .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
        .where(
            BillingDocument.company_id == order.company_id,
            BillingDocumentLine.from_doc_type == "DO",
            BillingDocumentLine.from_doc_no == order.order_number,
        )
    )
    return _with_notes(direct, order.company_id)


# ------------------------------------------------------------------------------- items
def _so_amount(db: Session, so_ids: list[str]) -> dict[str, Optional[Decimal]]:
    from app.services.scm.sales_order_service import _order_amount

    if not so_ids:
        return {}
    by_so: dict[str, list[SalesOrderLine]] = {sid: [] for sid in so_ids}
    for line in db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id.in_(so_ids)):
        by_so[str(line.sales_order_id)].append(line)
    return {sid: _order_amount(lines) for sid, lines in by_so.items()}


def _sales_order_items(db: Session, company_id: str, ids) -> list[dict[str, Any]]:
    rows = (
        db.query(SalesOrder)
        .filter(SalesOrder.company_id == company_id, SalesOrder.id.in_(ids))
        .all()
    )
    amounts = _so_amount(db, [str(r.id) for r in rows])
    return [
        {
            "id": str(r.id),
            "doc_no": r.so_number,
            "doc_date": _iso(r.order_date),
            "status": r.status,
            "amount": _num(amounts.get(str(r.id))),
            "currency_code": None,
        }
        for r in rows
    ]


def _delivery_order_items(db: Session, company_id: str, ids) -> list[dict[str, Any]]:
    rows = (
        db.query(Order, OrderStatus.status_name)
        .outerjoin(OrderStatus, OrderStatus.id == Order.order_status_id)
        .filter(Order.company_id == company_id, Order.id.in_(ids))
        .all()
    )
    return [
        {
            "id": str(o.id),
            "doc_no": o.order_number,
            "doc_date": _iso(o.order_date),
            "status": "Cancelled" if o.is_cancelled else status_name,
            "amount": _num(o.total_amount),
            "currency_code": o.currency_code,
        }
        for o, status_name in rows
    ]


def _billing_items(db: Session, company_id: str, ids) -> list[dict[str, Any]]:
    rows = (
        db.query(BillingDocument)
        .filter(BillingDocument.company_id == company_id, BillingDocument.id.in_(ids))
        .all()
    )
    return [
        {
            "id": str(d.id),
            "document_type": d.document_type,
            "doc_no": d.doc_no,
            "doc_date": _iso(d.doc_date),
            "status": d.status,
            "amount": _num(d.total),
            "currency_code": d.currency_code,
        }
        for d in rows
    ]


def _by_date(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda i: (i["doc_date"] or "9999", i["doc_no"]))


# --------------------------------------------------------------------------- per record
def relations_for_sales_order(db: Session, so: SalesOrder) -> dict[str, list[dict[str, Any]]]:
    return {
        "sales_orders": [],
        "delivery_orders": _by_date(_delivery_order_items(db, so.company_id, _do_ids_for_so(so))),
        "billing_documents": _by_date(
            _billing_items(db, so.company_id, billing_ids_for_sales_order(so))
        ),
    }


def _so_ids_for_do_ids(company_id: str, do_ids):
    """SELECT of the ids of the sales orders the DOs `do_ids` deliver."""
    via_line = (
        select(SalesOrderLine.sales_order_id)
        .join(OrderLine, OrderLine.sales_order_line_id == SalesOrderLine.id)
        .where(OrderLine.order_id.in_(do_ids))
    )
    via_number = (
        select(SalesOrder.id)
        .join(
            OrderLine,
            _so_from_doc(OrderLine.from_doc_type, OrderLine.from_doc_no, SalesOrder.so_number),
        )
        .where(OrderLine.order_id.in_(do_ids), SalesOrder.company_id == company_id)
    )
    via_header = select(Order.sales_order_id).where(
        Order.id.in_(do_ids), Order.sales_order_id.isnot(None)
    )
    return select(SalesOrder.id).where(
        SalesOrder.company_id == company_id,
        or_(
            SalesOrder.id.in_(via_line),
            SalesOrder.id.in_(via_number),
            SalesOrder.id.in_(via_header),
        ),
    )


def relations_for_delivery_order(db: Session, order: Order) -> dict[str, list[dict[str, Any]]]:
    return {
        "sales_orders": _by_date(
            _sales_order_items(db, order.company_id, _so_ids_for_do_ids(order.company_id, [order.id]))
        ),
        "delivery_orders": [],
        "billing_documents": _by_date(
            _billing_items(db, order.company_id, billing_ids_for_delivery_order(order))
        ),
    }


def relations_for_billing_document(
    db: Session, doc: BillingDocument
) -> dict[str, list[dict[str, Any]]]:
    company_id = doc.company_id
    # A note inherits its invoice's orders: its own lines rarely carry a from-document.
    sources = [doc.id] + ([doc.against_document_id] if doc.against_document_id else [])
    lines = (
        db.query(
            BillingDocumentLine.from_doc_type,
            BillingDocumentLine.from_doc_no,
            BillingDocumentLine.sales_order_line_id,
        )
        .filter(BillingDocumentLine.document_id.in_(sources))
        .all()
    )
    do_numbers = sorted({no for typ, no, _ in lines if typ == "DO" and no})
    so_numbers = {no for typ, no, _ in lines if typ == "SO" and no}
    so_line_ids = {lid for _, _, lid in lines if lid}

    found = {
        o.order_number: o
        for o in db.query(Order).filter(
            Order.company_id == company_id,
            Order.deleted_at.is_(None),
            Order.order_number.in_(do_numbers),
        )
    } if do_numbers else {}
    delivery_orders = _delivery_order_items(db, company_id, [str(o.id) for o in found.values()])
    # A DO number the CRM does not hold is still named, without a link.
    delivery_orders += [
        {"id": None, "doc_no": no, "doc_date": None, "status": None, "amount": None,
         "currency_code": None}
        for no in do_numbers
        if no not in found
    ]

    so_ids = select(SalesOrder.id).where(
        SalesOrder.company_id == company_id,
        or_(
            SalesOrder.so_number.in_(so_numbers),
            SalesOrder.id.in_(
                select(SalesOrderLine.sales_order_id).where(SalesOrderLine.id.in_(so_line_ids))
            ),
            SalesOrder.id.in_(_so_ids_for_do_ids(company_id, [str(o.id) for o in found.values()])),
        ),
    )

    related_billing = select(BillingDocument.id).where(
        BillingDocument.company_id == company_id,
        BillingDocument.id != doc.id,
        or_(
            BillingDocument.against_document_id == doc.id,
            BillingDocument.id == doc.against_document_id,
        ),
    )
    return {
        "sales_orders": _by_date(_sales_order_items(db, company_id, so_ids)),
        "delivery_orders": _by_date(delivery_orders),
        "billing_documents": _by_date(_billing_items(db, company_id, related_billing)),
    }


# ------------------------------------------------------------------------------ the table
def related_table(
    relations: dict[str, Optional[list[dict[str, Any]]]],
    *,
    sort: str = "doc_date",
    dir: str = "asc",
) -> list[dict[str, Any]]:
    """One row per related record across the visible kinds, sorted by `sort` (server side)."""
    rows: list[dict[str, Any]] = []
    for kind, key in KIND_KEYS.items():
        for item in relations.get(key) or []:
            rows.append(
                {
                    "kind": kind,
                    "type": item.get("document_type") or kind,
                    "id": item["id"],
                    "doc_no": item["doc_no"],
                    "doc_date": item["doc_date"],
                    "status": item.get("status"),
                    "amount": item.get("amount"),
                    "currency_code": item.get("currency_code"),
                }
            )
    rows.sort(key=lambda r: r["doc_no"])  # stable tiebreak under the chosen column
    present = [r for r in rows if r.get(sort) is not None]
    blank = [r for r in rows if r.get(sort) is None]
    present.sort(key=lambda r: r[sort], reverse=dir == "desc")
    return present + blank


#: The view slug that opens each kind's own record; a kind the viewer cannot open is masked.
VIEW_SLUGS = {
    SALES_ORDER: "scm.dashboard.view",
    DELIVERY_ORDER: "order_management.orders.view",
    BILLING_DOCUMENT: "finance.billing_documents.view",
}


def can_view(db: Session, user_id: str, kind: str) -> bool:
    """Whether the viewer may open records of `kind`: its view slug, and (under the strict
    module guard) its module enabled, the same two checks `require_permission` makes."""
    from app.config import settings
    from app.services.user_service import UserPermissionService

    perms = UserPermissionService(db)
    slug = VIEW_SLUGS[kind]
    if not perms.check_user_has_permission(user_id, slug):
        return False
    if not getattr(settings, "module_guard_strict", False):
        return True
    if perms.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return True
    from app.modules.runtime.installer import (
        DEFAULT_TENANT_ID,
        is_module_enabled,
        tenant_has_any_module_row,
    )
    from app.modules.runtime.permission_module_map import module_for_permission

    module = module_for_permission(slug)
    if module and tenant_has_any_module_row(db, DEFAULT_TENANT_ID):
        return is_module_enabled(db, DEFAULT_TENANT_ID, module)
    return True


def related_response(
    db: Session,
    user_id: str,
    relations: dict[str, list[dict[str, Any]]],
    *,
    sort: str = "doc_date",
    dir: str = "asc",
) -> dict[str, Any]:
    """The `/related` body: each kind nulled when the viewer lacks its view slug, plus the
    visible rows as one table sorted server side."""
    masked = {
        key: (relations[key] if can_view(db, user_id, kind) else None)
        for kind, key in KIND_KEYS.items()
    }
    return {**masked, "rows": related_table(masked, sort=sort, dir=dir)}
