"""Synthetic seed for the RESERVE-DIALOG-ON-HAND browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all names invented): an admin login; pool BRW with member BRW-BB; product
ZZT-ONHAND-01 with 171 on hand at BRW; an order inquiry on SO ZZTSO0001 with one open row
(stock location BRW-BB); a second, NON-transferable SO ZZTSO0002 with an open line of 6 at
BRW; an open SPO allocation of 4 at BRW. On hand 171, old "available" 171 - 6 + 4 = 169.
Prints the inquiry id.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from decimal import Decimal

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.database import engine  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.inventory import Stock, Warehouse  # noqa: E402
from app.models.order import Customer, SalesOrder, SalesOrderLine  # noqa: E402
from app.models.procurement import InboundShipment, SPOAllocation  # noqa: E402
from app.models.product import Product, ProductCategory, UnitOfMeasure  # noqa: E402
from app.models.project_so import (  # noqa: E402
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User, UserRoleAssignment  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
ADMIN_EMAIL = "browse.admin@example.com"
ADMIN_PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only


def u() -> str:
    return str(uuid.uuid4())


db = sessionmaker(bind=engine)()
set_company_scope(db, frozenset({COMPANY}))

admin = User(id=u(), email=ADMIN_EMAIL, name="Browse Admin", status="ACTIVE",
             password=bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode())
db.add(admin)
db.flush()
role = db.execute(text("SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') "
                       "OR name ILIKE 'super admin' LIMIT 1")).scalar()
db.add(UserRoleAssignment(user_id=admin.id, role_id=role))
db.add(UserCompany(id=u(), user_id=admin.id, company_id=COMPANY))
db.flush()

brw = Warehouse(id=u(), warehouse_code="BRW", warehouse_name="Test site pool", is_active=True,
                fulfilment_planning=True)
db.add(brw)
db.flush()
brw_bb = Warehouse(id=u(), warehouse_code="BRW-BB", warehouse_name="Test site group BB",
                   is_active=True, fulfilment_planning=True, pool_warehouse_id=brw.id)
db.add(brw_bb)
db.flush()

uom = UnitOfMeasure(id=u(), uom_code="ZZTUNIT", uom_name="Unit")
category = ProductCategory(id=u(), category_code="ZZT-CAT", category_name="Test category")
db.add_all([uom, category])
db.flush()
product = Product(id=u(), product_code="ZZT-ONHAND-01", product_name="Test basin",
                  category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"))
db.add(product)
db.flush()
db.add(Stock(id=u(), product_id=product.id, warehouse_id=brw.id, quantity_on_hand=171,
             quantity_reserved=0))

customer = Customer(id=u(), company_id=COMPANY, customer_code="ZZT-CUST",
                    customer_name="Test Customer Sdn Bhd")
other = Customer(id=u(), company_id=COMPANY, customer_code="ZZT-CUST2",
                 customer_name="Other Test Buyer Sdn Bhd")
db.add_all([customer, other])
db.flush()

# The order the inquiry is about.
core_so = SalesOrder(id=u(), company_id=COMPANY, so_number="ZZTSO0001", customer_id=customer.id,
                     order_date=date(2026, 11, 2), status="open", demand_class="project")
db.add(core_so)
db.flush()
core_line = SalesOrderLine(id=u(), company_id=COMPANY, sales_order_id=core_so.id,
                           product_id=product.id, warehouse_id=brw_bb.id, qty_ordered=Decimal("20"),
                           unit_price=Decimal("10.00"), required_date=date(2026, 12, 1),
                           line_status="open")
db.add(core_line)
db.flush()
pso = ProjectSalesOrder(id=u(), company_id=COMPANY, so_id=core_so.id, provisional_ref="ZZTSO0001",
                        autocount_doc_no="ZZTSO0001", status="adopted")
db.add(pso)
db.flush()
mirror = ProjectSalesOrderLine(id=u(), company_id=COMPANY, project_sales_order_id=pso.id, line_no=1,
                               product_id=product.id, description="Test basin", qty=Decimal("20"),
                               uom="UNIT", unit_price=Decimal("10.00"), amount=Decimal("0"),
                               delivery_date=date(2026, 12, 1),
                               core_sales_order_line_id=core_line.id)
db.add(mirror)
db.flush()
inquiry = OrderInquiry(id=u(), company_id=COMPANY, project_sales_order_id=pso.id,
                       state=INQUIRY_RAISED)
db.add(inquiry)
db.flush()
db.add(OrderInquiryRow(id=u(), company_id=COMPANY, order_inquiry_id=inquiry.id, so_line_id=mirror.id,
                       item_code=product.product_code, qty=Decimal("20"),
                       delivery_date=date(2026, 12, 1), stock_location="BRW-BB", verb=IV_ORDER,
                       state=INQUIRY_RAISED))

# The claim that made the two screens disagree: an open line on a NON-transferable SO at BRW.
held_so = SalesOrder(id=u(), company_id=COMPANY, so_number="ZZTSO0002", customer_id=other.id,
                     order_date=date(2026, 11, 3), status="open", demand_class="project",
                     is_transferable=False)
db.add(held_so)
db.flush()
db.add(SalesOrderLine(id=u(), company_id=COMPANY, sales_order_id=held_so.id, product_id=product.id,
                      warehouse_id=brw.id, qty_ordered=Decimal("6"), unit_price=Decimal("10.00"),
                      required_date=date(2026, 12, 5), line_status="open"))

# And an open SPO allocation arriving at BRW.
shipment = InboundShipment(id=u(), shipment_number="ZZT-SHIP-1", shipment_date=date(2026, 11, 1),
                           estimated_arrival_date=date(2026, 12, 15))
db.add(shipment)
db.flush()
db.add(SPOAllocation(id=u(), spo_number="ZZT-SPO-1", spo_line_number=1,
                     inbound_shipment_id=shipment.id, warehouse_id=brw.id, product_id=product.id,
                     allocated_quantity=4, quantity_received=0, receipt_status="pending"))

db.commit()
print("inquiry", inquiry.id)
