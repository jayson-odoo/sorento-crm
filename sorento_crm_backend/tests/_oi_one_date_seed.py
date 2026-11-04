"""Seeding for the OI-ONE-DELIVERY-DATE suites (`tests/test_oi_one_delivery_date_*.py`).

One chain per call, nothing borrowed from an existing row (CI's database has none):

    core Customer + SalesOrder (+ core SalesOrderLine, which carries `required_date`)
    -> ProjectSalesOrder (adopted, `so_id` = the core order)
    -> ProjectSalesOrderLine (the MIRROR line: `delivery_date`, `core_sales_order_line_id`)
    -> OrderInquiryRow (`so_line_id` = the mirror line, `delivery_date` = the TOLD date)

Terms are the UAC's: SO line date = core `required_date`, else the mirror's `delivery_date`,
else the row's own stored date. Told date = the stored `order_inquiry_rows.delivery_date`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)

MARKER = "zzt-oi-one-date"

#: Pass as `core_date` to add_line to say "this mirror line has NO core line linked".
NO_CORE = object()


def uid() -> str:
    return str(uuid.uuid4())


def digits(n: int = 10) -> str:
    return f"{uuid.uuid4().int % 10**n:0{n}d}"


class Chain:
    """One adopted sales order with its core order, its inquiry header and a product."""

    def __init__(self, db, company_id: str, *, so_number: Optional[str] = None):
        self.db = db
        self.company_id = company_id
        self.so_number = so_number or f"ZZTSO{digits(8)}"
        uom = UnitOfMeasure(id=uid(), uom_code=f"ZZT{digits(6)}", uom_name="Unit")
        category = ProductCategory(
            id=uid(), category_code=f"ZZT-{digits(8)}", category_name=f"{MARKER} cat"
        )
        db.add_all([uom, category])
        db.flush()
        self.product = Product(
            id=uid(),
            product_code=f"ZZT-ONEDATE-{digits(8)}",
            product_name=f"{MARKER} product",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("100.00"),
        )
        customer = Customer(
            id=uid(),
            company_id=company_id,
            customer_code=f"ZZT-{digits(8)}",
            customer_name=f"{MARKER} Customer Sdn Bhd",
        )
        db.add_all([self.product, customer])
        db.flush()
        self.core_so = SalesOrder(
            id=uid(),
            company_id=company_id,
            so_number=self.so_number,
            customer_id=customer.id,
            order_date=date(2026, 1, 8),
        )
        db.add(self.core_so)
        db.flush()
        self.pso = ProjectSalesOrder(
            id=uid(),
            company_id=company_id,
            project_id=None,
            so_id=self.core_so.id,
            provisional_ref=self.so_number,
            autocount_doc_no=self.so_number,
            status="adopted",
        )
        db.add(self.pso)
        db.flush()
        self.inquiry = OrderInquiry(
            id=uid(),
            company_id=company_id,
            project_sales_order_id=self.pso.id,
            state=INQUIRY_RAISED,
        )
        db.add(self.inquiry)
        db.flush()
        self._line_no = 0

    def add_line(
        self,
        *,
        core_date=None,
        mirror_date: Optional[date] = None,
        qty: str = "100",
    ):
        """`(core_line_or_None, mirror_line)`. `core_date=NO_CORE` links no core line."""
        self._line_no += 1
        core = None
        if core_date is not NO_CORE:
            core = SalesOrderLine(
                id=uid(),
                company_id=self.company_id,
                sales_order_id=self.core_so.id,
                product_id=self.product.id,
                qty_ordered=Decimal(qty),
                unit_price=Decimal("10.00"),
                required_date=core_date,
                line_status="open",
            )
            self.db.add(core)
            self.db.flush()
        mirror = ProjectSalesOrderLine(
            id=uid(),
            company_id=self.company_id,
            project_sales_order_id=self.pso.id,
            line_no=self._line_no,
            product_id=self.product.id,
            description=f"{MARKER} line",
            qty=Decimal(qty),
            uom="UNIT",
            unit_price=Decimal("10.00"),
            amount=Decimal("0"),
            delivery_date=mirror_date,
            core_sales_order_line_id=core.id if core is not None else None,
        )
        self.db.add(mirror)
        self.db.flush()
        return core, mirror

    def add_row(
        self,
        mirror_line,
        *,
        told: Optional[date],
        previous: Optional[date] = None,
        inquiry: Optional[OrderInquiry] = None,
        item_code: Optional[str] = None,
        qty: str = "10",
        state: str = INQUIRY_RAISED,
        **fields,
    ) -> OrderInquiryRow:
        row = OrderInquiryRow(
            id=uid(),
            company_id=self.company_id,
            order_inquiry_id=(inquiry or self.inquiry).id,
            so_line_id=mirror_line.id if mirror_line is not None else None,
            item_code=item_code or self.product.product_code,
            qty=Decimal(qty),
            delivery_date=told,
            previous_delivery_date=previous,
            verb=IV_ORDER,
            state=state,
            **fields,
        )
        self.db.add(row)
        self.db.flush()
        return row


def worklist_client(db, company_id: str):
    """`(client, originals)` for GET /api/v1/project-sales/order-inquiries."""
    from .test_order_inquiry_worklist import _client, _user

    user_id = _user(db, f"{MARKER} reader")
    return _client(db, user_id, ["projects.projects.view"])
