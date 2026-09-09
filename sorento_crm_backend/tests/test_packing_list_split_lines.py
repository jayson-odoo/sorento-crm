"""S4 - our packing list carries the supplier's carton split (`documentation/plans/scm/
scm-supplier-documents-pi-first-acceptance-criteria.md`, section D, ruling A).

TEST-FIRST (Phase 2). Each test below targets one AC-D id from the plan's own test list
(`PLAN-scm-supplier-documents-pi-first.md`, "Slices, order, and the captain's test list",
S4 row): D1, D2b, D2c, D4, D4b, D5, D6, D7. Every one is expected red today, most for the
SAME underlying reason - `uk_inbound_shipment_lines_ship_prod_sup` (migration 374) still
enforces one line per (shipment, product, supplier), so a test that seeds the split
scenario D1 exists to prove out fails at SETUP with a Postgres `IntegrityError` rather than
inside the assertion. That is deliberate and is called out per-test below, not a fixture
bug: D1 has to land before D4/D7's own scenarios are even representable.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PickingHeader,
    PickingLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import register_company_scope_listeners
from app.services.error_handler import AppException
from app.services.procurement_service import InboundShipmentService

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZPLSPLIT"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _world(db):
    """One company, one product, one supplier - everything below shares this chain."""
    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=f"{MARKER}-{company_id[:8]}", code=unique_code("C")[:20]))
    db.flush()
    set_company_scope(db, frozenset({company_id}))

    cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="c")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("U")[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()), product_code=unique_code("P")[:50], product_name="P",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=unique_code("S")[:50], supplier_name="Kailu",
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return company_id, product, supplier


def _shipment(db, *, status="draft") -> InboundShipment:
    s = InboundShipment(
        id=str(uuid.uuid4()), shipment_number=unique_code("SHP")[:50],
        shipping_container_number=unique_code("CTN")[:100],
        shipment_date=date(2026, 7, 30), shipment_status=status,
    )
    db.add(s)
    db.flush()
    return s


def _line(db, shipment, product, supplier, *, qty, created_at=None, cartons=1, pcs_per_carton=None):
    line = InboundShipmentLine(
        id=str(uuid.uuid4()), shipment_id=shipment.id, product_id=product.id,
        supplier_id=supplier.id, quantity_shipped=qty, cartons_count=cartons,
        pcs_per_carton=pcs_per_carton,
    )
    if created_at is not None:
        line.created_at = created_at
    db.add(line)
    return line


# --------------------------------------------------------------------------------- AC-D1


def test_d1_two_lines_of_one_product_from_one_supplier_are_legal():
    """`uk_inbound_shipment_lines_ship_prod_sup` must become non-unique
    (`ix_inbound_shipment_lines_ship_prod_sup`, same three columns). Today it is still a
    UNIQUE index, so this insert raises `IntegrityError` - the assertion below is AC-D1's
    TARGET state (both rows land, no exception), which is why it is red right now rather
    than the exception itself being the thing under test."""
    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db)

        _line(db, shipment, product, supplier, qty=50)
        _line(db, shipment, product, supplier, qty=35)
        db.flush()

        rows = (
            db.query(InboundShipmentLine)
            .filter(
                InboundShipmentLine.shipment_id == shipment.id,
                InboundShipmentLine.product_id == product.id,
                InboundShipmentLine.supplier_id == supplier.id,
            )
            .all()
        )
        assert len(rows) == 2
        assert sorted(int(r.quantity_shipped) for r in rows) == [35, 50]


# --------------------------------------------------------------------------------- AC-D2b


def test_d2b_a_partial_quantity_on_a_rowed_pi_line_is_refused_422():
    """`convert_to_draft_shipment(..., line_quantities={...})` on a PI line that HAS
    packing rows must be refused - placement is whole rows only for such a line
    (`packing_row_ids`), `line_quantities` is for a PI line with NO rows. Depends on S1
    (numbering) and S2 (`ProformaInvoicePackingLine`), so this is expected `ImportError`
    until both land, then a 422 `packing_rows_place_whole` once D2b itself does."""
    from app.services.scm import proforma_invoice_service

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine

        invoice = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-{MARKER}-1",
        )
        db.add(invoice)
        db.flush()
        pi_line = ProformaInvoiceLine(
            id=str(uuid.uuid4()), invoice_id=invoice.id, line_no=1, item_code=product.product_code,
            qty=85, unit_price=36, product_id=product.id,
        )
        db.add(pi_line)
        db.flush()
        db.add(
            ProformaInvoicePackingLine(
                id=str(uuid.uuid4()), proforma_invoice_id=invoice.id,
                proforma_invoice_line_id=pi_line.id, row_no=1, item_code=product.product_code,
                product_id=product.id, qty=50, cartons=1, match_state="matched",
            )
        )
        db.commit()

        with pytest.raises(AppException) as e:
            proforma_invoice_service.convert_to_draft_shipment(
                db, [str(invoice.id)], created_by=str(uuid.uuid4()),
                line_quantities={str(pi_line.id): 40},
            )
        assert e.value.status_code == 422
        assert e.value.detail["code"] == "packing_rows_place_whole"


# --------------------------------------------------------------------------------- AC-D2c


def test_d2c_header_carries_over_when_one_container_agrees_and_is_blank_on_conflict():
    from app.services.scm import proforma_invoice_service

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine

        def _invoice_with_row(container_no, row_container_no):
            inv = ProformaInvoice(
                id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-{uuid.uuid4().hex[:8]}",
                container_ref=container_no, bl_ref="BL-XYZ",
            )
            db.add(inv)
            db.flush()
            line = ProformaInvoiceLine(
                id=str(uuid.uuid4()), invoice_id=inv.id, line_no=1, item_code=product.product_code,
                qty=10, unit_price=1, product_id=product.id,
            )
            db.add(line)
            db.flush()
            db.add(
                ProformaInvoicePackingLine(
                    id=str(uuid.uuid4()), proforma_invoice_id=inv.id,
                    proforma_invoice_line_id=line.id, row_no=1, item_code=product.product_code,
                    product_id=product.id, qty=10, cartons=1, container_no=row_container_no,
                    match_state="matched",
                )
            )
            db.commit()
            return inv

        # Agree: the one PI selected names ONE container throughout its rows.
        agree_inv = _invoice_with_row("WHSU6243088", "WHSU6243088")
        result = proforma_invoice_service.convert_to_draft_shipment(
            db, [str(agree_inv.id)], created_by=str(uuid.uuid4()),
        )
        from app.models.procurement import InboundShipment as _Shp

        shipment = db.query(_Shp).filter(_Shp.id == result["shipment_id"]).one()
        assert shipment.shipping_container_number == "WHSU6243088"
        assert shipment.bill_of_lading_number == "BL-XYZ"
        assert not result.get("header_conflicts")

        # Conflict: two PIs whose rows name DIFFERENT containers.
        conflict_a = _invoice_with_row("CTNA0000001", "CTNA0000001")
        conflict_b = _invoice_with_row("CTNB0000002", "CTNB0000002")
        result2 = proforma_invoice_service.convert_to_draft_shipment(
            db, [str(conflict_a.id), str(conflict_b.id)], created_by=str(uuid.uuid4()),
        )
        shipment2 = db.query(_Shp).filter(_Shp.id == result2["shipment_id"]).one()
        assert shipment2.shipping_container_number is None
        assert "container_number" in (result2.get("header_conflicts") or [])


# --------------------------------------------------------------------------------- AC-D4


def test_d4_editing_by_line_id_updates_each_of_two_same_key_lines_independently():
    """Depends on D1 (the unique index still forbids seeding the scenario) AND on the
    schema/service gaining `id`-first matching - `InboundShipmentLineCreate` carries no
    `id` field at all today, so an `id` in the payload is silently ignored by pydantic and
    the two dicts fall back to being matched by (product, supplier) alone, which cannot
    tell them apart. Both are legitimate reasons for this to be red right now."""
    from app.schemas.procurement import InboundShipmentUpdate

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db)
        now = datetime.utcnow()
        line_a = _line(db, shipment, product, supplier, qty=50, created_at=now)
        line_b = _line(db, shipment, product, supplier, qty=35, created_at=now + timedelta(seconds=1))
        db.commit()

        payload = InboundShipmentUpdate(
            shipment_lines=[
                {"id": str(line_a.id), "product_id": str(product.id), "supplier_id": str(supplier.id), "quantity_shipped": 60},
                {"id": str(line_b.id), "product_id": str(product.id), "supplier_id": str(supplier.id), "quantity_shipped": 12},
            ]
        )
        InboundShipmentService(db).update_shipment(str(shipment.id), payload, updated_by=str(uuid.uuid4()))

        db.expire_all()
        refreshed_a = db.query(InboundShipmentLine).filter(InboundShipmentLine.id == line_a.id).one()
        refreshed_b = db.query(InboundShipmentLine).filter(InboundShipmentLine.id == line_b.id).one()
        assert int(refreshed_a.quantity_shipped) == 60
        assert int(refreshed_b.quantity_shipped) == 12


def test_d4_an_id_less_edit_on_an_ambiguous_pair_is_refused_409():
    from app.schemas.procurement import InboundShipmentUpdate

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db)
        now = datetime.utcnow()
        _line(db, shipment, product, supplier, qty=50, created_at=now)
        _line(db, shipment, product, supplier, qty=35, created_at=now + timedelta(seconds=1))
        db.commit()

        payload = InboundShipmentUpdate(
            shipment_lines=[
                {"product_id": str(product.id), "supplier_id": str(supplier.id), "quantity_shipped": 40},
            ]
        )
        with pytest.raises(AppException) as e:
            InboundShipmentService(db).update_shipment(
                str(shipment.id), payload, updated_by=str(uuid.uuid4())
            )
        assert e.value.status_code == 409
        assert e.value.detail["code"] == "line_id_required"


# --------------------------------------------------------------------------------- AC-D4b


def test_d4b_external_update_on_a_converted_draft_leaves_lines_untouched():
    """A shipment with `proforma_invoice_shipment_link` rows (a converted draft) must have
    its lines left alone by the external n8n route's update-in-place path - header fields
    only. Exercised at the service level (`create_shipment`'s existing update-in-place
    branch), since that is where the plan says the guard belongs."""
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink
    from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db, status="draft")
        line = _line(db, shipment, product, supplier, qty=50)
        db.flush()

        invoice = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-{MARKER}-d4b",
        )
        db.add(invoice)
        db.flush()
        pi_line = ProformaInvoiceLine(
            id=str(uuid.uuid4()), invoice_id=invoice.id, line_no=1,
            item_code=product.product_code, qty=50, unit_price=1, product_id=product.id,
        )
        db.add(pi_line)
        db.flush()
        db.add(
            ProformaInvoiceShipmentLink(
                id=str(uuid.uuid4()), proforma_invoice_id=invoice.id,
                proforma_invoice_line_id=pi_line.id, inbound_shipment_id=shipment.id,
                inbound_shipment_line_id=line.id,
            )
        )
        db.commit()

        other_product = Product(
            id=str(uuid.uuid4()), product_code=unique_code("P2")[:50], product_name="P2",
            category_id=product.category_id, base_uom_id=product.base_uom_id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        db.add(other_product)
        db.flush()

        update = InboundShipmentCreate(
            shipment_number=shipment.shipment_number,
            shipment_date=date(2026, 8, 1),
            shipping_container_number="NEWCTN0000001",
            shipment_lines=[
                InboundShipmentLineCreate(product_id=str(other_product.id), quantity_shipped=999),
            ],
        )
        result = InboundShipmentService(db).create_shipment(update, created_by=str(uuid.uuid4()))

        db.expire_all()
        lines = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == shipment.id)
            .all()
        )
        assert len(lines) == 1
        assert str(lines[0].product_id) == str(product.id), (
            "a converted draft's lines must never be rewritten by the external route"
        )
        assert getattr(result, "lines_skipped_reason", None) == "lines_from_proforma_invoices"


# --------------------------------------------------------------------------------- AC-D5


def _spo_allocation(db, shipment, product, qty, *, received=0):
    warehouse_id = str(uuid.uuid4())
    from app.models.inventory import Warehouse

    db.add(Warehouse(id=warehouse_id, warehouse_code=unique_code("WH")[:50], warehouse_name="WH"))
    db.flush()
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()), spo_number=unique_code("SPO")[:50],
            inbound_shipment_id=shipment.id, warehouse_id=warehouse_id, product_id=product.id,
            allocated_quantity=qty, quantity_received=received,
        )
    )
    db.flush()


@pytest.mark.parametrize(
    "allocated,expected",
    [
        (30, (30, 0)),     # under: line A takes all 30, line B gets none
        (85, (50, 35)),    # exact: both lines fully allocated
        (100, (50, 50)),   # over: the overflow (15) lands on the LAST line
    ],
)
def test_d5_apportion_walks_lines_in_created_order_overflow_on_the_last(allocated, expected):
    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db, status="in_transit")
        now = datetime.utcnow()
        line_a = _line(db, shipment, product, supplier, qty=50, created_at=now)
        line_b = _line(db, shipment, product, supplier, qty=35, created_at=now + timedelta(seconds=1))
        db.flush()
        _spo_allocation(db, shipment, product, allocated)
        db.commit()

        InboundShipmentService(db).refresh_shipment_line_statuses(str(shipment.id))

        db.expire_all()
        refreshed_a = db.query(InboundShipmentLine).filter(InboundShipmentLine.id == line_a.id).one()
        refreshed_b = db.query(InboundShipmentLine).filter(InboundShipmentLine.id == line_b.id).one()
        assert (int(refreshed_a.spo_allocated_quantity or 0), int(refreshed_b.spo_allocated_quantity or 0)) == expected


# --------------------------------------------------------------------------------- AC-D6


def test_d6_incoming_stock_unallocated_quantity_is_correct_per_split_line():
    from app.services.incoming_stock_service import IncomingStockService

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db, status="in_transit")
        now = datetime.utcnow()
        _line(db, shipment, product, supplier, qty=50, created_at=now)
        _line(db, shipment, product, supplier, qty=35, created_at=now + timedelta(seconds=1))
        db.flush()
        _spo_allocation(db, shipment, product, 60)
        db.commit()

        out = IncomingStockService(db).shipment_incoming_products(str(shipment.id))
        products = out["data"]["products"]
        assert len(products) == 2, "one entry per LINE, not one per product"

        by_remaining = sorted(products, key=lambda p: -p["remaining_incoming_quantity"])
        assert by_remaining[0]["remaining_incoming_quantity"] == 50
        assert by_remaining[0]["unallocated_quantity"] in (None, 0)
        assert by_remaining[1]["remaining_incoming_quantity"] == 35
        assert by_remaining[1]["unallocated_quantity"] == 25


def test_d6_the_allocation_planner_proposes_the_outstanding_remainder_for_line_b_only():
    from app.services.scm import allocation_suggestion_service

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db, status="in_transit")
        shipment.supplier_id = supplier.id
        now = datetime.utcnow()
        line_a = _line(db, shipment, product, supplier, qty=50, created_at=now)
        line_b = _line(db, shipment, product, supplier, qty=35, created_at=now + timedelta(seconds=1))
        db.flush()
        _spo_allocation(db, shipment, product, 60)
        db.commit()

        InboundShipmentService(db).refresh_shipment_line_statuses(str(shipment.id))
        db.commit()

        out = allocation_suggestion_service.suggest(db, str(shipment.id))
        by_id = {l["shipment_line_id"]: l for l in out["lines"]}
        assert by_id[str(line_a.id)]["quantity_to_allocate"] == 0
        assert by_id[str(line_b.id)]["quantity_to_allocate"] == 25


# --------------------------------------------------------------------------------- AC-D7


def test_d7_consolidated_export_prints_one_row_per_shipment_line():
    """Depends on D1: seeding the split scenario is what is red here, not `build()`
    itself (already per-line, per the plan's own measured fact)."""
    from app.services.scm.consolidated_packing_list import build

    with blank_session() as db:
        _company_id, product, supplier = _world(db)
        shipment = _shipment(db, status="draft")
        _line(db, shipment, product, supplier, qty=50, cartons=1, pcs_per_carton=50)
        _line(db, shipment, product, supplier, qty=35, cartons=1, pcs_per_carton=35)
        db.commit()

        out = build(db, str(shipment.id))
        rows = out["suppliers"][0]["lines"] if out.get("suppliers") else next(iter(out.values()))
        product_rows = [r for r in rows if r["product_id"] == str(product.id)]
        assert len(product_rows) == 2
        assert sorted(r["qty"] for r in product_rows) == [35, 50]
        assert sorted(r["pcs_per_carton"] for r in product_rows) == [35.0, 50.0]
