"""Shared seeds and runners for the SALES-UNIFIED red tests (not a test module).

Contract: `documentation/plans/sales/CONTRACT-sales-unified-27oct.md`. Every row is seeded by the
caller's test (CI's database is empty); codes are fictional (`ZZT` prefix via `unique_code`).

A billing document with lines is how the SO chain (contract section 3) is exercised: a line can
carry `so_line` (resolved onto an SO line), or `from_type` / `from_no` (transferred from an SO or
DO by number).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
from app.models.finance import BillingDocument, BillingDocumentLine
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import product, warehouse
from tests._pg_fixture import unique_code

D = Decimal
SALES_TYPE_LABELS = {
    "dealer": "Dealer",
    "project": "Project team",
    "set_apart": "Set apart",
    "mixed": "Mixed sales order types",
    "type_not_set": "Sales order type not set",
    "no_sales_order": "No sales order",
}
ALL_TYPES = list(SALES_TYPE_LABELS)


def six(values):
    """The contract's six sales types, in order. Plan round 3 (Q7) adds a seventh, `other`
    ("Other"), the contract file does not yet; it is tolerated anywhere and ignored here."""
    return [v for v in values if (v[0] if isinstance(v, tuple) else v) != "other"]


JAN = {"kind": "custom", "from": "2026-01-01", "to": "2026-01-31"}


def agent(db, code: Optional[str] = None, *, demand_class: Optional[str] = None) -> SalesAgent:
    """A shared agent master row (company NULL), as production holds them."""
    row = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=code or unique_code("AG"),
        demand_class=demand_class,
        company_id=None,
    )
    db.add(row)
    db.flush()
    return row


def cust(
    db,
    *,
    debtor_type: Optional[str] = None,
    agent_row: Optional[SalesAgent] = None,
    company_id: str = DEFAULT_COMPANY_ID,
    name: Optional[str] = None,
    code: Optional[str] = None,
) -> Customer:
    extra: dict[str, Any] = {}
    if debtor_type is not None:
        extra["autocount_debtor_type"] = debtor_type
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=code or unique_code("CUST")[:50],
        customer_name=name or unique_code("Customer"),
        company_id=company_id,
        sales_agent_id=agent_row.id if agent_row is not None else None,
        **extra,
    )
    db.add(row)
    db.flush()
    return row


def so(
    db,
    *,
    demand_class: Optional[str] = "retail",
    customer: Optional[Customer] = None,
    company_id: str = DEFAULT_COMPANY_ID,
    number: Optional[str] = None,
    lines: int = 1,
):
    """A sales order with `lines` lines. Returns (order, [lines])."""
    header = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=number or unique_code("SO"),
        customer_id=customer.id if customer is not None else None,
        status="open",
        demand_class=demand_class,
        company_id=company_id,
    )
    db.add(header)
    db.flush()
    made = []
    for _ in range(lines):
        line = SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=header.id,
            product_id=product(db, company_id=company_id).id,
            qty_ordered=1,
            qty_delivered=1,
            line_total=D("100.00"),
            line_status="open",
            company_id=company_id,
        )
        db.add(line)
        made.append(line)
    db.flush()
    return header, made


def delivery(
    db,
    *,
    so_line: Optional[SalesOrderLine] = None,
    from_so_no: Optional[str] = None,
    from_type: Optional[str] = "SO",
    header_so: Optional[SalesOrder] = None,
    deleted: bool = False,
    company_id: str = DEFAULT_COMPANY_ID,
) -> Order:
    """A delivery order with one line. It delivers an SO by its line link (`so_line`), by the
    line's from-document number (`from_so_no`), or by the header link (`header_so`)."""
    order = Order(
        id=str(uuid.uuid4()),
        order_number=unique_code("DO"),
        company_id=company_id,
        sales_order_id=header_so.id if header_so is not None else None,
        deleted_at=datetime(2026, 1, 2) if deleted else None,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderLine(
            id=str(uuid.uuid4()),
            order_id=order.id,
            line_sequence=1,
            product_id=product(db, company_id=company_id).id,
            warehouse_id=warehouse(db, company_id=company_id).id,
            quantity=1,
            sales_order_line_id=so_line.id if so_line is not None else None,
            from_doc_type=from_type if from_so_no else None,
            from_doc_no=from_so_no,
            company_id=company_id,
        )
    )
    db.flush()
    return order


def line(
    *,
    net: Optional[str] = None,
    qty: str = "1",
    item_code: Optional[str] = None,
    prod=None,
    description: Optional[str] = None,
    so_line: Optional[SalesOrderLine] = None,
    from_type: Optional[str] = None,
    from_no: Optional[str] = None,
) -> dict:
    return {
        "net": net, "qty": qty, "item_code": item_code, "prod": prod, "description": description,
        "so_line": so_line, "from_type": from_type, "from_no": from_no,
    }


def doc(
    db,
    kind: str,
    net: str,
    when: date,
    *,
    customer: Optional[Customer] = None,
    agent_row: Optional[SalesAgent] = None,
    agent_code: Optional[str] = None,
    status: str = "posted",
    tax: str = "0",
    against: Optional[BillingDocument] = None,
    company_id: str = DEFAULT_COMPANY_ID,
    demand_class: Optional[str] = None,
    rate: str = "1",
    lines: Optional[list[dict]] = None,
) -> BillingDocument:
    """One billing document. `net` is `local_net_total` (MYR, net of tax, stored positive; a
    credit note is stored positive as AutoCount prints it). `lines`: dicts from `line()`;
    a line with no `net` takes the header net."""
    amount = D(net)
    header = BillingDocument(
        id=str(uuid.uuid4()),
        company_id=company_id,
        document_type=kind,
        doc_no=unique_code({"invoice": "IV", "cash_sale": "CS", "debit_note": "DN", "credit_note": "CN"}[kind]),
        doc_date=when,
        customer_id=customer.id if customer is not None else None,
        sales_agent_id=agent_row.id if agent_row is not None else None,
        agent_code=agent_code,
        status=status,
        currency_rate=D(rate),
        net_total=amount,
        tax_total=D(tax),
        total=amount + D(tax),
        local_net_total=amount,
        against_document_id=against.id if against is not None else None,
        demand_class=demand_class,
        source_ref=f"SRT_DB:{uuid.uuid4().hex}",
    )
    db.add(header)
    db.flush()
    for number, spec in enumerate(lines or [], start=1):
        prod = spec["prod"]
        db.add(
            BillingDocumentLine(
                id=str(uuid.uuid4()),
                document_id=header.id,
                company_id=company_id,
                line_no=number,
                product_id=prod.id if prod is not None else None,
                item_code=spec["item_code"] or (prod.product_code if prod is not None else None),
                description=spec["description"],
                quantity=D(spec["qty"]),
                net_amount=D(spec["net"]) if spec["net"] is not None else amount,
                sales_order_line_id=spec["so_line"].id if spec["so_line"] is not None else None,
                from_doc_type=spec["from_type"],
                from_doc_no=spec["from_no"],
                source_ref=f"D{number}",
            )
        )
    db.flush()
    return header


# ------------------------------------------------------------------------------ runners


def params(period: Optional[dict] = None, **over) -> dict:
    """Params for the new definitions. No `date_basis` key: the contract's param list for
    `sales_by_debtor_type` / `top_selling_items` does not name one (the engine default applies)."""
    out = {"company": [DEFAULT_COMPANY_ID], "period": period or JAN}
    out.update(over)
    return out


def view(rows: str = "sales_agent", cols: str = "debtor_type", measures=("sales_value",),
         pivot_sort: Optional[dict] = None, detail_sort: Optional[dict] = None,
         columns=(), **p):
    from app.schemas.report import ReportViewConfig

    pivot: dict[str, Any] = {"rows": rows, "cols": cols, "measures": list(measures)}
    if pivot_sort is not None:
        pivot["sort"] = pivot_sort
    detail: dict[str, Any] = {"columns": list(columns), "order": list(columns)}
    if detail_sort is not None:
        detail["sort"] = detail_sort
    return ReportViewConfig.model_validate({"params": params(**p), "detail": detail, "pivot": pivot})


def definition_of(key: str):
    from app.services.reports import registry as reg

    found = reg.get(key)
    assert found is not None, f"{key} is not registered"
    return found


def run(db, key: str, *, grants=frozenset({DEFAULT_COMPANY_ID}), **kw):
    from app.services.reports import engine

    v = view(**kw)
    return engine.run(db, definition_of(key), v.params, v, company_grants=grants)


def by_type(db, period: Optional[dict] = None, **kw) -> dict[str, Decimal]:
    """RM per sales type label (rows = channel), over the `billing_documents` dataset through
    `sales_by_debtor_type`; every type ticked unless `channel=` says otherwise."""
    result = run(db, "sales_by_debtor_type", rows="channel", cols="year",
                 **({"period": period} if period else {}), **kw)
    return {label: D(cells["sales_value"]) for label, cells in result.layouts.summary.row_totals.items()}


def by_agent(db, period: Optional[dict] = None, **kw) -> dict[str, Decimal]:
    result = run(db, "sales_by_debtor_type", **({"period": period} if period else {}), **kw)
    return {label: D(cells["sales_value"]) for label, cells in result.layouts.summary.row_totals.items()}


def grand(result) -> Decimal:
    return D(result.layouts.summary.grand_total["sales_value"])
