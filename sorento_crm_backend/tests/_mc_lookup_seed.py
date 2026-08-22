"""Shared minimal seed helpers for the multi-company reply-clarity test suite
(UAC `documentation/plans/multi-company/multi-company-reply-clarity-acceptance-criteria.md`).

Not a test module itself - the leading underscore keeps pytest from collecting
it, matching `_pg_fixture.py`'s own convention.

Every owned (`CompanyScopedMixin`) row below is created with an EXPLICIT
`company_id`. That is deliberate, not just tidy: several tests in this suite
pin a two-company `company_scope` BEFORE seeding (they need it in place while
they build the "spans two companies" fixture), and the `before_insert`
auto-stamp hook (`app/services/company_scope.py::_stamp_company_id`) RAISES on
an ambiguous multi-company scope for any owned insert that has no company_id
of its own. Passing it explicitly sidesteps that ordering trap entirely, so
seed order never has to be reasoned about against scope state.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.certificate import Certificate, CertificateProduct
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.order import Customer, Order, OrderLine
from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


def seed_mocha(db) -> Company:
    """Register the second company. Sorento (`DEFAULT_COMPANY_ID`) is already
    seeded into every `blank_session` schema by `conftest.py`."""
    row = Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20])
    db.add(row)
    db.flush()
    return row


def product(db, *, company_id: str, code: str | None = None) -> Product:
    code = code or unique_code("SKU")
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("CAT")[:50],
        category_name="Category",
        company_id=company_id,
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=unique_code("UOM")[:50],
        uom_name="Each",
        company_id=company_id,
    )
    db.add_all([category, uom])
    db.flush()
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def warehouse(db, *, company_id: str, code: str | None = None) -> Warehouse:
    row = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=code or unique_code("WH")[:50],
        warehouse_name="Warehouse",
        is_active=True,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def stock(
    db, *, company_id: str, product_id: str, warehouse_id: str, on_hand: int = 10
) -> Stock:
    row = Stock(
        id=str(uuid.uuid4()),
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity_on_hand=on_hand,
        quantity_reserved=0,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def inbound_shipment(
    db, *, company_id: str, number: str | None = None, eta: date | None = None
) -> InboundShipment:
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=number or unique_code("SHP")[:50],
        shipment_date=date(2026, 1, 1),
        estimated_arrival_date=eta,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def inbound_shipment_line(
    db, *, company_id: str, shipment_id: str, product_id: str, shipped: int = 10, received: int = 0
) -> InboundShipmentLine:
    row = InboundShipmentLine(
        id=str(uuid.uuid4()),
        shipment_id=shipment_id,
        product_id=product_id,
        quantity_shipped=shipped,
        quantity_received=received,
        line_status="in_transit",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def attachment_type(db, *, name: str | None = None) -> AttachmentType:
    """Reference data - not company-scoped, safely shared across companies."""
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=name or unique_code("Type")[:50],
        allowed_extensions="pdf",
    )
    db.add(row)
    db.flush()
    return row


def attachment(db, *, type_id: str, filename: str = "ZZT-doc.pdf") -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"https://cdn.test/{filename}",
        attachment_type_id=type_id,
        is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def product_attachment(
    db, *, company_id: str, product_id: str, attachment_id: str
) -> ProductAttachment:
    row = ProductAttachment(
        id=str(uuid.uuid4()),
        product_id=product_id,
        attachment_id=attachment_id,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def certificate(
    db,
    *,
    company_id: str,
    attachment_type_id: str,
    number: str | None = None,
) -> Certificate:
    row = Certificate(
        id=str(uuid.uuid4()),
        attachment_type_id=attachment_type_id,
        scheme=unique_code("SCHEME")[:60],
        certificate_number=number or unique_code("CERT")[:120],
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def certificate_product(db, *, certificate_id: str, product_id: str) -> CertificateProduct:
    row = CertificateProduct(
        id=str(uuid.uuid4()),
        certificate_id=certificate_id,
        product_id=product_id,
    )
    db.add(row)
    db.flush()
    return row


def promotion(
    db, *, company_id: str, description: str | None = None, active: bool = True
) -> Promotion:
    row = Promotion(
        id=str(uuid.uuid4()),
        description=description or unique_code("PROMO"),
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        is_active=active,
        access_levels=["dealer"],
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def promotion_group(db, *, company_id: str, promotion_id: str) -> PromotionGroup:
    row = PromotionGroup(
        id=uuid.uuid4(),
        promotion_id=promotion_id,
        group_name=unique_code("GROUP")[:255],
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def promotion_product(
    db, *, company_id: str, promotion_id: str, promotion_group_id, product_id: str
) -> PromotionProduct:
    row = PromotionProduct(
        id=str(uuid.uuid4()),
        promotion_id=promotion_id,
        promotion_group_id=promotion_group_id,
        product_id=product_id,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def customer(db, *, company_id: str, name: str | None = None) -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=unique_code("CUST")[:50],
        customer_name=name or unique_code("Customer"),
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def order(
    db, *, company_id: str, customer_id: str | None = None, number: str | None = None
) -> Order:
    row = Order(
        id=str(uuid.uuid4()),
        order_number=number or unique_code("ORD")[:100],
        customer_id=customer_id,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def order_line(
    db, *, company_id: str, order_id: str, product_id: str, warehouse_id: str, quantity: int = 1
) -> OrderLine:
    row = OrderLine(
        id=str(uuid.uuid4()),
        order_id=order_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity=quantity,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row
