"""S7b - what goes on the container, what does not, and whether the plan says why.

Every purchase order, product, supplier and stock row is seeded by this file under codes it
generates. Container sizes are seeded by calling migration 336's own seeder rather than
assuming somebody ran the migration, because a CI database is built with `create_all` and
runs no migration body.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import LoadingPlanLine, SupplierInventory
from app.services.scm import loading_plan_service as svc
from tests._pg_fixture import pg_session

MARKER = "ZZLP"


def _seed_container_sizes(db) -> None:
    spec = importlib.util.spec_from_file_location(
        "m336", "alembic/versions/336_scm_supplier_inventory_loading_plan.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.seed_container_sizes(db.connection())


class World:
    """One supplier, three products, and whatever purchase orders a test asks for."""

    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        cat = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=f"{MARKER}-CAT-{tag}",
            category_name=f"{MARKER} category",
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs"
        )
        db.add_all([cat, uom])
        db.flush()
        self.cat, self.uom = cat, uom
        self.supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"{MARKER}-CR-{tag}",
            supplier_name=f"{MARKER} supplier",
            is_active=True,
        )
        db.add(self.supplier)
        db.flush()
        self.products: dict[str, Product] = {}

    def product(self, key: str, *, dims: tuple[int, int, int] | None = None) -> Product:
        if key in self.products:
            return self.products[key]
        p = Product(
            id=str(uuid.uuid4()),
            product_code=f"{MARKER}-{key}-{self.tag}",
            product_name=key,
            category_id=self.cat.id,
            base_uom_id=self.uom.id,
            list_price=0,
            is_active=True,
            is_discontinued=False,
            dimensions_length=dims[0] if dims else None,
            dimensions_width=dims[1] if dims else None,
            dimensions_height=dims[2] if dims else None,
        )
        self.db.add(p)
        self.db.flush()
        self.products[key] = p
        return p

    def po(self, number_suffix: str, lines, *, issue_date: date | None = None) -> PurchaseOrder:
        po = PurchaseOrder(
            id=str(uuid.uuid4()),
            po_number=f"{MARKER}-PO{number_suffix}-{self.tag}",
            supplier_id=self.supplier.id,
            issue_date=issue_date or date(2026, 1, 1),
            status="active",
        )
        self.db.add(po)
        self.db.flush()
        for key, qty, received in lines:
            self.db.add(
                PurchaseOrderLine(
                    id=str(uuid.uuid4()),
                    purchase_order_id=po.id,
                    product_id=self.product(key).id,
                    qty_ordered=qty,
                    qty_received=received,
                    line_status="open",
                )
            )
        self.db.flush()
        return po

    def stock(self, key: str, *, packed: float, unfinished: float = 0, cbm=None) -> None:
        self.db.add(
            SupplierInventory(
                id=str(uuid.uuid4()),
                supplier_id=self.supplier.id,
                item_code=self.product(key).product_code,
                product_id=self.product(key).id,
                qty_packed=packed,
                qty_unfinished=unfinished,
                cbm_per_unit=cbm,
                as_of=date(2026, 7, 31),
            )
        )
        self.db.flush()


def lines_of(db, plan) -> dict[str, LoadingPlanLine]:
    rows = db.query(LoadingPlanLine).filter(LoadingPlanLine.plan_id == plan.id).all()
    return {str(r.item_code): r for r in rows}


def test_the_container_fills_by_rank_and_the_rest_is_deferred_over_capacity():
    # AC-E4/E5. Capacity 10 cbm, two lines wanting 10 each: the older document wins whole and
    # the younger one is told why it lost.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        w.po("2", [("B", 10, 0)], issue_date=date(2026, 6, 1))
        w.stock("A", packed=10, cbm=1.0)
        w.stock("B", packed=10, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        by_code = lines_of(db, plan)
        a = by_code[w.product("A").product_code]
        b = by_code[w.product("B").product_code]
        assert a.status == "allocated" and float(a.qty_planned) == 10
        assert b.status == "deferred" and b.deferral_reason == "over_capacity"
        assert float(plan.planned_cbm) == 10.0


def test_a_line_is_part_loaded_rather_than_dropped_when_it_almost_fits():
    # AC-E4 allows partial fill: half a line on the container beats an empty 4 cbm.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        w.stock("A", packed=10, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=6)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.status == "partial"
        assert float(line.qty_planned) == 6


def test_a_part_load_is_whole_units():
    # A container is loaded with boxes. 3.7 of a toilet is not a thing anybody can pick.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)])
        w.stock("A", packed=10, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=3.7)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert float(line.qty_planned) == 3
        assert float(line.cbm_planned) == 3.0


def test_only_packed_stock_is_loadable_and_the_shortfall_says_so():
    # AC-E2. The supplier holds 40 unfinished bodies; they are not freight.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 50, 0)])
        w.stock("A", packed=10, unfinished=40, cbm=0.5)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=100)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert float(line.qty_planned) == 10
        assert line.status == "partial"
        assert line.deferral_reason == "no_packed_stock"


def test_a_line_the_supplier_has_nothing_packed_of_is_deferred_with_that_reason():
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 5, 0)])
        w.stock("A", packed=0, unfinished=80, cbm=0.5)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=100)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.status == "deferred"
        assert line.deferral_reason == "no_packed_stock"
        assert float(line.qty_planned) == 0


def test_a_line_the_stock_list_never_mentions_is_distinguished_from_one_that_is_out():
    # "The supplier did not list it" and "the supplier has none packed" are different
    # conversations with the supplier.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 5, 0)])

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=100)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.deferral_reason == "not_in_stock_list"


def test_a_line_with_no_volume_anywhere_is_unmeasured_and_never_silently_free():
    # Zero volume would let it load ahead of everything real, at no cost.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 5, 0)])
        w.stock("A", packed=5, cbm=None)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=100)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.status == "unmeasured"
        assert line.deferral_reason == "no_volume_on_file"
        assert float(line.qty_planned) == 0
        assert plan.unmeasured_count == 1


def test_the_catalogue_supplies_the_volume_when_the_supplier_does_not():
    # Product dimensions are in mm; 1000 x 1000 x 1000 is one cubic metre.
    with pg_session() as db:
        w = World(db)
        w.product("A", dims=(1000, 1000, 1000))
        w.po("1", [("A", 4, 0)])
        w.stock("A", packed=4, cbm=None)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.volume_basis == "catalogue"
        assert float(line.cbm_per_unit) == 1.0
        assert float(line.qty_planned) == 4


def test_the_supplier_figure_beats_the_catalogue_figure():
    with pg_session() as db:
        w = World(db)
        w.product("A", dims=(1000, 1000, 1000))
        w.po("1", [("A", 1, 0)])
        w.stock("A", packed=1, cbm=0.25)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert line.volume_basis == "supplier"
        assert float(line.cbm_per_unit) == 0.25


def test_only_the_outstanding_half_of_a_part_received_line_is_planned():
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 7)])
        w.stock("A", packed=100, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=100)

        line = lines_of(db, plan)[w.product("A").product_code]
        assert float(line.qty_outstanding) == 3
        assert float(line.qty_planned) == 3


def test_changing_the_container_count_re_runs_the_plan_in_place():
    # AC-E6: no re-upload, and no second plan left behind for one decision.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        w.po("2", [("B", 10, 0)], issue_date=date(2026, 6, 1))
        w.stock("A", packed=10, cbm=1.0)
        w.stock("B", packed=10, cbm=1.0)
        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)
        assert plan.deferred_count == 1

        again = svc.build(
            db,
            supplier_id=str(w.supplier.id),
            container_count=2,
            container_cbm=10,
            plan=plan,
        )

        assert str(again.id) == str(plan.id)
        assert again.deferred_count == 0
        assert float(again.capacity_cbm) == 20
        assert db.query(LoadingPlanLine).filter(LoadingPlanLine.plan_id == plan.id).count() == 2


def test_every_line_carries_the_factors_its_rank_was_built_from():
    # AC-E7. A rank a planner cannot decompose is one they stop trusting.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 1, 0)])
        w.stock("A", packed=1, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        line = lines_of(db, plan)[w.product("A").product_code]
        keys = {f["key"] for f in line.factors_json}
        assert "po_document_sequence" in keys
        assert all({"key", "weight", "value", "present"} <= set(f) for f in line.factors_json)


def test_a_named_container_size_resolves_to_its_configured_volume():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        w.po("1", [("A", 1, 0)])
        w.stock("A", packed=1, cbm=1.0)

        plan = svc.build(
            db, supplier_id=str(w.supplier.id), container_count=2, container_type="40HQ"
        )

        assert plan.container_type == "40HQ"
        assert float(plan.capacity_cbm) == float(plan.container_cbm) * 2


def test_a_container_size_nobody_configured_is_refused_rather_than_defaulted():
    # Planning a 40HQ as a 20GP silently loses half a container.
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)

        with pytest.raises(ValueError):
            svc.build(db, supplier_id=str(w.supplier.id), container_type="45ZZ")


def test_a_plan_needs_at_least_one_container():
    with pg_session() as db:
        w = World(db)

        with pytest.raises(ValueError):
            svc.build(db, supplier_id=str(w.supplier.id), container_count=0, container_cbm=10)


def test_unfinished_stock_is_listed_separately_with_its_quantity():
    # AC-E2: Ms Tee has to be able to ask the supplier to produce it.
    with pg_session() as db:
        w = World(db)
        w.stock("A", packed=2, unfinished=140, cbm=0.5)
        w.stock("B", packed=9, unfinished=0, cbm=0.5)

        rows = svc.unfinished_at_supplier(db, str(w.supplier.id))

        assert [r["item_code"] for r in rows] == [w.product("A").product_code]
        assert rows[0]["qty_unfinished"] == 140


def test_the_plan_serializes_with_its_fill_rate_and_lines():
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 5, 0)])
        w.stock("A", packed=5, cbm=1.0)
        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        out = svc.serialize(db, plan)

        assert out["capacity_cbm"] == 10
        assert out["planned_cbm"] == 5
        assert out["fill_rate"] == 0.5
        assert len(out["lines"]) == 1
        assert out["lines"][0]["status"] == "allocated"


def test_a_closed_purchase_order_line_is_not_a_candidate():
    with pg_session() as db:
        w = World(db)
        po = w.po("1", [("A", 5, 0)])
        db.execute(
            text("UPDATE purchase_order_lines SET line_status = 'closed' "
                 "WHERE purchase_order_id = :p"),
            {"p": po.id},
        )
        w.stock("A", packed=5, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        assert plan.line_count == 0


def test_another_suppliers_orders_never_appear_on_this_plan():
    with pg_session() as db:
        w, other = World(db), World(db)
        other.po("9", [("A", 5, 0)])
        other.stock("A", packed=5, cbm=1.0)
        w.po("1", [("A", 5, 0)])
        w.stock("A", packed=5, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        assert plan.line_count == 1
        assert list(lines_of(db, plan)) == [w.product("A").product_code]


def _policy(db, factors: dict, class_weights: dict | None = None) -> str:
    """An active priority policy owned by this test, replacing whatever is active.

    Deactivating rather than deleting: the seeded policy is reference data, and the whole
    thing is inside a transaction that rolls back.
    """
    from app.models.scm import PriorityPolicy

    db.query(PriorityPolicy).filter(PriorityPolicy.is_active.is_(True)).update(
        {"is_active": False}, synchronize_session=False
    )
    p = PriorityPolicy(
        id=str(uuid.uuid4()),
        name=f"{MARKER}-policy-{uuid.uuid4().hex[:6]}",
        is_active=True,
        factors=factors,
        demand_class_weights=class_weights or {},
    )
    db.add(p)
    db.flush()
    return str(p.id)


def test_the_policy_decides_the_order_not_the_document_sequence():
    # The seeded rule is document sequence, which agrees with row order and so cannot prove
    # the policy is read at all. Switch the weight to need-by and the YOUNGER document with
    # the sooner ETA has to win the only container slot.
    with pg_session() as db:
        w = World(db)
        old = w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        young = w.po("2", [("B", 10, 0)], issue_date=date(2026, 6, 1))
        db.execute(
            text("UPDATE purchase_order_lines SET expected_date = :d "
                 "WHERE purchase_order_id = :p"),
            {"d": date(2026, 12, 1), "p": old.id},
        )
        db.execute(
            text("UPDATE purchase_order_lines SET expected_date = :d "
                 "WHERE purchase_order_id = :p"),
            {"d": date(2026, 9, 1), "p": young.id},
        )
        w.stock("A", packed=10, cbm=1.0)
        w.stock("B", packed=10, cbm=1.0)
        policy_id = _policy(db, {"need_by_date": 1.0, "po_document_sequence": 0.0})

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        by_code = lines_of(db, plan)
        assert by_code[w.product("B").product_code].rank == 1
        assert by_code[w.product("A").product_code].status == "deferred"
        assert str(plan.policy_id) == policy_id


def test_an_unmeasured_line_does_not_eat_capacity_from_the_measured_ones():
    # The failure this guards is the silent one: an unmeasured line treated as zero volume
    # would sit at rank 1 and load for free, and the plan would still look full.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 5, 0)], issue_date=date(2026, 1, 1))
        w.po("2", [("B", 5, 0)], issue_date=date(2026, 6, 1))
        w.stock("A", packed=5, cbm=None)
        w.stock("B", packed=5, cbm=1.0)

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=5)

        by_code = lines_of(db, plan)
        assert by_code[w.product("A").product_code].status == "unmeasured"
        assert float(by_code[w.product("B").product_code].qty_planned) == 5
        assert float(plan.planned_cbm) == 5.0


def test_the_demand_class_factor_reads_through_the_so_to_po_linkage():
    # The claim table is what tells a purchase order which sales orders it feeds, so a
    # project-weighted policy has to reach it. Without the join the factor is absent and both
    # lines score the same.
    with pg_session() as db:
        from app.models.order import SalesOrder
        from app.models.scm import OrderLinkClaim

        w = World(db)
        retail_po = w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        project_po = w.po("2", [("B", 10, 0)], issue_date=date(2026, 6, 1))
        w.stock("A", packed=10, cbm=1.0)
        w.stock("B", packed=10, cbm=1.0)
        for suffix, po, klass in (("R", retail_po, "retail"), ("P", project_po, "project")):
            so = SalesOrder(
                id=str(uuid.uuid4()),
                so_number=f"{MARKER}-SO{suffix}-{w.tag}",
                order_date=date(2026, 1, 1),
                status="open",
                demand_class=klass,
            )
            db.add(so)
            db.flush()
            db.add(
                OrderLinkClaim(
                    id=str(uuid.uuid4()),
                    so_number=so.so_number,
                    po_number=po.po_number,
                    source="manual",
                )
            )
        db.flush()
        _policy(db, {"demand_class": 1.0, "po_document_sequence": 0.0},
                {"project": 1.0, "retail": 0.4})

        plan = svc.build(db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10)

        by_code = lines_of(db, plan)
        # The project order is younger and would lose on document sequence; it wins here only
        # because its demand class was resolved.
        assert by_code[w.product("B").product_code].rank == 1
        assert by_code[w.product("A").product_code].status == "deferred"
