"""S9 AC-G4/G6/G6a/G7 - which order a container draws down, and what approving it moves.

The suggestion has to be checkable, so what is asserted is the reason and the alternatives as
much as the winner. Approving has to be honest about arithmetic, so the split rules are pinned
in both directions: allocating less than shipped loses stock nobody will ever look for, and
allocating more receives stock that does not exist.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import allocation_suggestion_service as svc
from tests._pg_fixture import pg_session

MARKER = "ZZAS"


class World:
    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"{MARKER}-C-{tag}",
            category_name=f"{MARKER} cat",
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs"
        )
        db.add_all([cat, uom])
        db.flush()
        self.cat, self.uom = cat, uom
        self.supplier = Supplier(
            id=str(uuid.uuid4()), supplier_code=f"{MARKER}-S-{tag}",
            supplier_name=f"{MARKER} supplier", is_active=True,
        )
        db.add(self.supplier)
        db.flush()
        self.products: dict[str, Product] = {}
        self.warehouses: dict[str, Warehouse] = {}

    def product(self, key: str) -> Product:
        if key not in self.products:
            p = Product(
                id=str(uuid.uuid4()), product_code=f"{MARKER}-{key}-{self.tag}",
                product_name=key, category_id=self.cat.id, base_uom_id=self.uom.id,
                list_price=0, is_active=True, is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[key] = p
        return self.products[key]

    def warehouse(self, key: str, *, available: bool = True) -> Warehouse:
        if key not in self.warehouses:
            w = Warehouse(
                id=str(uuid.uuid4()), warehouse_code=f"{MARKER}-{key}-{self.tag}"[:50],
                warehouse_name=key, is_active=True, counts_as_available=available,
            )
            self.db.add(w)
            self.db.flush()
            self.warehouses[key] = w
        return self.warehouses[key]

    def po(
        self, suffix: str, lines, *, issue_date: date, status: str = "active"
    ) -> PurchaseOrder:
        po = PurchaseOrder(
            id=str(uuid.uuid4()), po_number=f"{MARKER}-PO{suffix}-{self.tag}",
            supplier_id=self.supplier.id, issue_date=issue_date, status=status,
        )
        self.db.add(po)
        self.db.flush()
        for key, qty, received, wh in lines:
            self.db.add(
                PurchaseOrderLine(
                    id=str(uuid.uuid4()), purchase_order_id=po.id,
                    product_id=self.product(key).id,
                    warehouse_id=self.warehouse(wh).id if wh else None,
                    qty_ordered=qty, qty_received=received, line_status="open",
                )
            )
        self.db.flush()
        return po

    def shipment(self, lines) -> InboundShipment:
        s = InboundShipment(
            id=str(uuid.uuid4()), shipment_number=f"{MARKER}-SH-{self.tag}",
            supplier_id=self.supplier.id, shipment_date=date(2026, 8, 1),
            shipment_status="in_transit",
        )
        self.db.add(s)
        self.db.flush()
        for key, qty in lines:
            self.db.add(
                InboundShipmentLine(
                    id=str(uuid.uuid4()), shipment_id=s.id,
                    product_id=self.product(key).id, quantity_shipped=qty,
                )
            )
        self.db.flush()
        return s


def _po_line(db, po: PurchaseOrder) -> PurchaseOrderLine:
    return db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.purchase_order_id == po.id
    ).first()


def test_the_oldest_open_order_is_proposed_with_its_alternatives_beside_it():
    # AC-G4. Ranked by the same policy the Loading Plan uses, and the loser is shown so
    # accepting is a decision rather than a shrug.
    with pg_session() as db:
        w = World(db)
        old = w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        new = w.po("2", [("A", 10, 0, "BRW")], issue_date=date(2026, 6, 1))
        shipment = w.shipment([("A", 10)])

        out = svc.suggest(db, str(shipment.id))

        line = out["lines"][0]
        assert line["suggestion"]["po_number"] == old.po_number
        assert line["reason"] == "highest_priority"
        assert [a["po_number"] for a in line["alternatives"]] == [new.po_number]


def test_a_single_open_order_says_so_rather_than_claiming_it_won_a_comparison():
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["reason"] == "only_open_order"
        assert line["alternatives"] == []


def test_a_product_with_no_open_order_proposes_nothing_and_says_why():
    # Stock does arrive against no purchase order. Inventing one to fill the field would be a
    # link nobody can undo.
    with pg_session() as db:
        w = World(db)
        shipment = w.shipment([("A", 4)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["suggestion"] is None
        assert line["reason"] == "no_open_order"


def test_another_supplier_s_order_is_not_a_candidate_at_all():
    with pg_session() as db:
        w = World(db)
        other = Supplier(
            id=str(uuid.uuid4()), supplier_code=f"{MARKER}-O-{w.tag}",
            supplier_name=f"{MARKER} other", is_active=True,
        )
        db.add(other)
        db.flush()
        po = PurchaseOrder(
            id=str(uuid.uuid4()), po_number=f"{MARKER}-OTHER-{w.tag}",
            supplier_id=other.id, issue_date=date(2026, 1, 1), status="active",
        )
        db.add(po)
        db.flush()
        db.add(PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=w.product("A").id,
            qty_ordered=10, qty_received=0, line_status="open",
        ))
        db.flush()
        shipment = w.shipment([("A", 10)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["suggestion"] is None


def test_a_draft_purchase_order_is_not_a_candidate_either():
    # G1b. A draft the supplier has never seen cannot be what a container shipped against, so
    # offering it as the suggestion would invite a link to an order that was never placed.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1),
             status="draft_recommendation")
        w.po("2", [("A", 10, 0, "BRW")], issue_date=date(2026, 2, 1), status="draft")
        placed = w.po("3", [("A", 10, 0, "BRW")], issue_date=date(2026, 6, 1))
        shipment = w.shipment([("A", 10)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["suggestion"]["po_number"] == placed.po_number
        assert line["reason"] == "only_open_order"
        assert line["alternatives"] == []


def test_the_proposal_never_exceeds_what_the_order_still_has_outstanding():
    # Proposing more than a purchase order asked for is how a receipt goes over.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 6, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["quantity_to_allocate"] == 10
        assert line["suggestion"]["qty"] == 6


def test_a_line_already_part_allocated_is_only_proposed_for_the_remainder():
    # Re-opening the screen after a partial allocation must not propose the same units twice.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        line_row = db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one()
        line_row.spo_allocated_quantity = 4
        db.flush()

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["quantity_to_allocate"] == 6
        assert line["suggestion"]["qty"] == 6


def test_a_line_with_no_purchase_order_location_lands_somewhere_sellable():
    # AC-G8's whole point is that salespeople can see it. A location whose stock is not
    # available would make the arrival invisible to exactly those people.
    with pg_session() as db:
        w = World(db)
        # `_default_warehouse` picks ANY sellable warehouse in scope, company-scoped - a
        # from-zero database has none at all (a real one always happens to hold one), so
        # this world seeds its own rather than borrowing whatever the environment has.
        w.warehouse("SELLABLE")
        w.po("1", [("A", 10, 0, None)], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])

        line = svc.suggest(db, str(shipment.id))["lines"][0]

        assert line["suggestion"]["warehouse_id"] is not None


def test_approving_writes_the_allocation_and_advances_the_purchase_order():
    # AC-G6, both halves of the one action.
    with pg_session() as db:
        w = World(db)
        po = w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        suggestion = svc.suggest(db, str(shipment.id))["lines"][0]

        out = svc.approve(db, str(shipment.id), [
            {
                "shipment_line_id": suggestion["shipment_line_id"],
                "splits": [{
                    "po_line_id": suggestion["suggestion"]["po_line_id"],
                    "warehouse_id": suggestion["suggestion"]["warehouse_id"],
                    "qty": 10,
                }],
            }
        ])

        assert out["allocations_written"] == 1
        assert float(_po_line(db, po).qty_received) == 10
        alloc = db.query(SPOAllocation).filter(
            SPOAllocation.inbound_shipment_id == shipment.id
        ).one()
        assert float(alloc.allocated_quantity) == 10
        assert str(alloc.po_line_id) == suggestion["suggestion"]["po_line_id"]


def test_a_split_across_two_orders_and_two_locations_is_allowed():
    # AC-G7. One container often draws down more than one order.
    with pg_session() as db:
        w = World(db)
        a = w.po("1", [("A", 6, 0, "BRW")], issue_date=date(2026, 1, 1))
        b = w.po("2", [("A", 6, 0, "KLW")], issue_date=date(2026, 2, 1))
        shipment = w.shipment([("A", 10)])
        line_id = str(db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one().id)

        svc.approve(db, str(shipment.id), [
            {
                "shipment_line_id": line_id,
                "splits": [
                    {"po_line_id": str(_po_line(db, a).id),
                     "warehouse_id": str(w.warehouse("BRW").id), "qty": 6},
                    {"po_line_id": str(_po_line(db, b).id),
                     "warehouse_id": str(w.warehouse("KLW").id), "qty": 4},
                ],
            }
        ])

        assert float(_po_line(db, a).qty_received) == 6
        assert float(_po_line(db, b).qty_received) == 4


def test_a_split_that_does_not_add_up_to_what_shipped_is_refused():
    # Allocating less is a quantity that has silently disappeared. Nothing downstream would
    # ever report it, which is why this is refused rather than warned about.
    with pg_session() as db:
        w = World(db)
        po = w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        line_id = str(db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one().id)

        with pytest.raises(AppException) as e:
            svc.approve(db, str(shipment.id), [
                {"shipment_line_id": line_id, "splits": [
                    {"po_line_id": str(_po_line(db, po).id),
                     "warehouse_id": str(w.warehouse("BRW").id), "qty": 7},
                ]}
            ])
        assert "add up to what shipped" in str(e.value.detail).lower()


def test_allocating_more_to_an_order_than_it_has_outstanding_is_refused():
    with pg_session() as db:
        w = World(db)
        po = w.po("1", [("A", 6, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        line_id = str(db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one().id)

        with pytest.raises(AppException) as e:
            svc.approve(db, str(shipment.id), [
                {"shipment_line_id": line_id, "splits": [
                    {"po_line_id": str(_po_line(db, po).id),
                     "warehouse_id": str(w.warehouse("BRW").id), "qty": 10},
                ]}
            ])
        assert "outstanding" in str(e.value.detail).lower()


def test_an_allocation_against_no_purchase_order_is_allowed_and_advances_nothing():
    # AC-G6a. Stock arrives against no order, and the unlinked row leaves the ordered figure
    # overstated - the stated cost of the 6 August decision, visible rather than hidden.
    with pg_session() as db:
        w = World(db)
        shipment = w.shipment([("A", 4)])
        line_id = str(db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one().id)

        out = svc.approve(db, str(shipment.id), [
            {"shipment_line_id": line_id, "splits": [
                {"po_line_id": None, "warehouse_id": str(w.warehouse("BRW").id), "qty": 4},
            ]}
        ])

        assert out["allocations_written"] == 1
        assert out["purchase_order_lines_advanced"] == 0


def test_an_allocation_with_no_location_is_refused():
    with pg_session() as db:
        w = World(db)
        shipment = w.shipment([("A", 4)])
        line_id = str(db.query(InboundShipmentLine).filter(
            InboundShipmentLine.shipment_id == shipment.id
        ).one().id)

        with pytest.raises(AppException) as e:
            svc.approve(db, str(shipment.id), [
                {"shipment_line_id": line_id,
                 "splits": [{"po_line_id": None, "warehouse_id": None, "qty": 4}]}
            ])
        assert "location" in str(e.value.detail).lower()


def test_a_line_from_another_shipment_is_refused():
    with pg_session() as db:
        w = World(db)
        mine = w.shipment([("A", 4)])
        with pytest.raises(AppException) as e:
            svc.approve(db, str(mine.id), [
                {"shipment_line_id": str(uuid.uuid4()),
                 "splits": [{"warehouse_id": str(w.warehouse("BRW").id), "qty": 4}]}
            ])
        assert "does not belong" in str(e.value.detail).lower()


def test_an_unknown_shipment_is_a_404():
    with pg_session() as db:
        with pytest.raises(AppException) as e:
            svc.suggest(db, str(uuid.uuid4()))
        assert e.value.status_code == 404
